#!/usr/bin/env python3
"""
scheduler.py — auto-discover scheduled-job prompts and fire due ones.

Runs once per minute under a launchd LaunchAgent. On each tick:
  1. Scans ~/.claude/scheduled-jobs/*.md for job prompts.
  2. Parses YAML frontmatter from each: cron, max_turns, max_budget_usd,
     cwd, effort, name, description, semantic_hooks.
  3. Writes a manifest.json listing all discovered jobs (for agent
     nodes to scan semantic hooks and ad-hoc trigger them).
  4. For each job whose cron pattern matches the current minute AND
     whose last-run state is older than the current minute, invokes
     run-job.sh in a detached subprocess (non-blocking).

Ad-hoc: `scheduler.py --trigger <name>` fires a single job immediately,
bypassing cron evaluation. Intended for agent nodes that match a
semantic hook and want to execute the corresponding job.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("HOME", str(Path.home())))
JOBS_DIR = HOME / ".claude" / "scheduled-jobs"
STATE_DIR = JOBS_DIR / ".state"
GLOBAL_PROMPT = HOME / ".claude" / "scheduled-jobs-prompt.md"
MANIFEST_PATH = JOBS_DIR / ".manifest.json"
RUN_JOB = JOBS_DIR / "run-job.sh"
UPDATE_CHECK = JOBS_DIR / "update-check.sh"
CONFIG_PATH = JOBS_DIR / ".open-claude-cron.config.json"
UPDATE_LAST_CHECK = STATE_DIR / ".update-last-check"

# Files with these stems are skipped even if they live in jobs dir.
RESERVED_STEMS = {"scheduler", "run-job", "trigger-job", "update-check"}


# ---------- frontmatter ----------

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    return _parse_yaml_subset(m.group(1)), m.group(2)


def _parse_yaml_subset(block: str) -> dict:
    """Minimal YAML supporting:
      - flat scalars: `key: value`
      - simple string lists: `- value`
      - list-of-objects in flow style: `- {key: value, key: value}`
    No nested block-style maps.
    """
    data: dict = {}
    current_list_key: str | None = None
    for raw in block.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key is not None:
            item = stripped[2:].strip()
            if item.startswith("{") and item.endswith("}"):
                data[current_list_key].append(_parse_flow_object(item))
            else:
                data[current_list_key].append(_strip_quotes(item))
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                data[key] = []
                current_list_key = key
            else:
                data[key] = _coerce(_strip_quotes(val))
                current_list_key = None
    return data


def _parse_flow_object(text: str) -> dict:
    """Parse flow-style YAML object: `{key: value, key: value, ...}`.
    Quoted strings may contain colons and commas; we split respecting quotes.
    """
    text = text.strip()
    if text.startswith("{"):
        text = text[1:]
    if text.endswith("}"):
        text = text[:-1]
    result: dict = {}
    for part in _smart_split(text, ","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        k, _, v = part.partition(":")
        result[k.strip()] = _coerce(_strip_quotes(v.strip()))
    return result


def _smart_split(text: str, sep: str) -> list[str]:
    """Split `text` on `sep` while respecting single/double-quoted regions."""
    parts: list[str] = []
    current = ""
    in_quote: str | None = None
    for c in text:
        if in_quote:
            current += c
            if c == in_quote:
                in_quote = None
        elif c in ('"', "'"):
            in_quote = c
            current += c
        elif c == sep:
            parts.append(current)
            current = ""
        else:
            current += c
    if current:
        parts.append(current)
    return parts


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def _coerce(s: str):
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    lower = s.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    return s


# ---------- cron ----------


def cron_matches(expr: str, dt: datetime) -> bool:
    """Standard 5-field cron: minute hour day-of-month month day-of-week."""
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"cron expr must have 5 fields, got {expr!r}")
    minute, hour, dom, month, dow = fields
    # Python isoweekday: Mon=1..Sun=7; cron: Sun=0..Sat=6 (and 7=Sun tolerated).
    wd = dt.isoweekday() % 7
    return (
        _match_field(minute, dt.minute, 0, 59)
        and _match_field(hour, dt.hour, 0, 23)
        and _match_field(dom, dt.day, 1, 31)
        and _match_field(month, dt.month, 1, 12)
        and _match_field(dow, wd, 0, 6, aliases={7: 0})
    )


def _match_field(expr: str, value: int, lo: int, hi: int, aliases=None) -> bool:
    for part in expr.split(","):
        if _part_matches(part, value, lo, hi, aliases):
            return True
    return False


def _part_matches(part: str, value: int, lo: int, hi: int, aliases) -> bool:
    step = 1
    if "/" in part:
        base, _, step_s = part.partition("/")
        step = int(step_s)
    else:
        base = part
    if base == "*" or base == "":
        start, end = lo, hi
    elif "-" in base:
        a, _, b = base.partition("-")
        start, end = int(a), int(b)
    else:
        n = int(base)
        if aliases and n in aliases:
            n = aliases[n]
        if step > 1:
            return value == n  # rarely meaningful, but consistent
        return value == n
    return lo <= value <= hi and start <= value <= end and ((value - start) % step == 0)


# ---------- discovery ----------


def discover_jobs() -> list[dict]:
    jobs: list[dict] = []
    if not JOBS_DIR.is_dir():
        return jobs
    for md in sorted(JOBS_DIR.glob("*.md")):
        if md.name.startswith(".") or md.stem in RESERVED_STEMS:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[scheduler] read error {md}: {e}", file=sys.stderr)
            continue
        fm, _body = parse_frontmatter(text)
        name = fm.get("name") or md.stem
        jobs.append(
            {
                "name": str(name),
                "path": str(md),
                "description": str(fm.get("description", "")),
                "cron": str(fm.get("cron", "")).strip(),
                "max_turns": int(fm.get("max_turns", 50)),
                "max_budget_usd": float(fm.get("max_budget_usd", 2.0)),
                "cwd": os.path.expanduser(str(fm.get("cwd") or "~")),
                "effort": str(fm.get("effort", "high")),
                "model": str(fm.get("model", "")).strip(),
                # setting_sources: "" to skip plugins/settings (massive cache reduction),
                # or "user,project,local" etc. Unset → claude default.
                "setting_sources": fm.get("setting_sources", None),
                # strict_mcp_config: true → load only MCPs explicitly configured
                # for this job (or none if --mcp-config isn't set by run-job.sh).
                # Bypasses the user's full MCP surface. Big cost reduction.
                "strict_mcp_config": bool(fm.get("strict_mcp_config", False)),
                # debounce_seconds: if >0, a new invocation within this window
                # of the last start is suppressed (noop, exit 0). Applies to
                # both cron and ad-hoc triggers.
                "debounce_seconds": int(fm.get("debounce_seconds", 0) or 0),
                # disabled: if true, the job is enumerated in the manifest but
                # scheduler.tick() skips firing it. Ad-hoc trigger still works.
                # Handy for pausing a job without editing its cron.
                "disabled": bool(fm.get("disabled", False)),
                # external_triggers: list of flow-style-object conditions that,
                # if met, cause the job to fire between cron slots. Evaluated
                # each tick. See eval_* functions for supported types.
                "external_triggers": list(fm.get("external_triggers", []) or []),
                "semantic_hooks": list(fm.get("semantic_hooks", []) or []),
            }
        )
    return jobs


# ---------- state ----------


def last_run(name: str) -> int:
    p = STATE_DIR / f"{name}.last-run"
    if not p.exists():
        return 0
    try:
        return int(p.read_text().strip() or "0")
    except (OSError, ValueError):
        return 0


def set_last_run(name: str, ts: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{name}.last-run").write_text(str(int(ts)))


# ---------- external triggers ----------


def evaluate_external_triggers(job: dict) -> bool:
    """Evaluate every external trigger for a job. Returns True if any fired.

    Each trigger has isolated state at .state/<name>.trigger-<index>.json so
    triggers cannot interfere with each other. Evaluation errors (bad config,
    missing paths) are logged to stderr and treated as "no fire" rather than
    aborting the whole tick — one bad trigger shouldn't block unrelated jobs.
    """
    triggers = job.get("external_triggers") or []
    if not triggers:
        return False
    job_name = job["name"]
    fired = False
    for idx, trig in enumerate(triggers):
        try:
            if not isinstance(trig, dict):
                raise ValueError(f"trigger must be an object, got {type(trig).__name__}")
            state_path = STATE_DIR / f"{job_name}.trigger-{idx}.json"
            state = None
            if state_path.exists():
                try:
                    state = json.loads(state_path.read_text())
                except (OSError, ValueError):
                    state = None  # corrupt state → treat as first-run bootstrap
            new_state, trigger_fired = _evaluate_trigger(trig, state)
            if new_state is not None:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(new_state))
            if trigger_fired:
                fired = True
                print(
                    f"[scheduler] external trigger fired: {job_name}[{idx}] type={trig.get('type')!r}",
                    flush=True,
                )
        except Exception as e:
            print(
                f"[scheduler] trigger eval error: {job_name}[{idx}] {trig.get('type', '?')}: {e}",
                file=sys.stderr,
            )
    return fired


def _evaluate_trigger(trig: dict, state: dict | None) -> tuple[dict | None, bool]:
    """Dispatch to per-type evaluator. Returns (new_state, fired)."""
    t = trig.get("type")
    if t == "file_added":
        return _eval_file_added(trig, state)
    if t == "file_changed":
        return _eval_file_changed(trig, state)
    if t == "process_starts":
        return _eval_process_starts(trig, state)
    if t == "command_succeeds":
        return _eval_command_succeeds(trig, state)
    raise ValueError(f"unknown trigger type: {t!r}")


def _eval_file_added(trig: dict, state: dict | None) -> tuple[dict, bool]:
    """Fire once per burst of new files.

    A "burst" is any window of activity followed by `quiet_seconds` of no new
    matching files. The trigger fires after the quiet period elapses, not when
    each file lands. Defaults: `glob='*'`, `quiet_seconds=30`.

    Bootstrap: on first evaluation, record currently-present files as the
    baseline and do NOT fire. New files added after install are what trigger.
    """
    path = os.path.expanduser(str(trig.get("path") or ""))
    pattern = str(trig.get("glob", "*"))
    quiet_seconds = float(trig.get("quiet_seconds", 30))
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(f"file_added path not a directory: {path!r}")

    current = {
        entry.name
        for entry in os.scandir(path)
        if entry.is_file() and fnmatch.fnmatch(entry.name, pattern)
    }
    now = time.time()
    if state is None:
        # Baseline — everything currently present is "seen", don't fire.
        return ({"seen_files": sorted(current), "pending_burst": False, "last_change_at": None}, False)

    seen = set(state.get("seen_files", []))
    pending_burst = bool(state.get("pending_burst", False))
    last_change = state.get("last_change_at")

    new_files = current - seen
    if new_files:
        last_change = now
        pending_burst = True
        seen |= new_files

    # Forget files that have been removed so re-adding them re-fires.
    seen &= current

    fired = False
    if pending_burst and last_change is not None and (now - last_change) >= quiet_seconds:
        fired = True
        pending_burst = False
        last_change = None

    return (
        {"seen_files": sorted(seen), "pending_burst": pending_burst, "last_change_at": last_change},
        fired,
    )


def _eval_file_changed(trig: dict, state: dict | None) -> tuple[dict, bool]:
    """Fire when a file's mtime moves forward.

    Bootstrap: first evaluation records current mtime and doesn't fire.
    """
    path = os.path.expanduser(str(trig.get("path") or ""))
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"file_changed path not found: {path!r}")
    mtime = os.path.getmtime(path)
    if state is None:
        return ({"last_mtime": mtime}, False)
    last = float(state.get("last_mtime", 0))
    if mtime > last:
        return ({"last_mtime": mtime}, True)
    return (state, False)


def _eval_process_starts(trig: dict, state: dict | None) -> tuple[dict, bool]:
    """Fire on the not-running → running transition (edge-triggered).

    `match` is a case-insensitive substring of the full process command line
    (pgrep -if). Matches .app bundles, interpreter-wrapped processes, etc.

    Bootstrap: if the process is already running at first check, record that
    and do NOT fire — the trigger waits for a genuine transition.
    """
    match = str(trig.get("match") or "")
    if not match:
        raise ValueError("process_starts requires a 'match' field")
    result = subprocess.run(
        ["/usr/bin/pgrep", "-if", match],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    running = (result.returncode == 0)
    if state is None:
        return ({"was_running": running}, False)
    was_running = bool(state.get("was_running", False))
    fired = running and not was_running
    return ({"was_running": running}, fired)


def _eval_command_succeeds(trig: dict, state: dict | None) -> tuple[dict, bool]:
    """Fire on the fail → succeed transition of a shell command (edge-triggered).

    Command runs under `zsh -lc` with the same PATH prep that run-job.sh uses
    (`~/.local/bin:~/bin` prepended), so user-installed CLIs resolve the same
    way they do inside jobs. Stdout/stderr are discarded; only the exit code
    matters.

    Bootstrap: records the initial success state without firing.
    """
    cmd = str(trig.get("run") or "")
    if not cmd:
        raise ValueError("command_succeeds requires a 'run' field")
    wrapped = f'export PATH="$HOME/.local/bin:$HOME/bin:$PATH"; {cmd}'
    result = subprocess.run(
        ["/bin/zsh", "-lc", wrapped],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    succeeding = (result.returncode == 0)
    if state is None:
        return ({"was_succeeding": succeeding}, False)
    was_succeeding = bool(state.get("was_succeeding", False))
    fired = succeeding and not was_succeeding
    return ({"was_succeeding": succeeding}, fired)


# ---------- manifest ----------


def write_manifest(jobs: list[dict]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs_dir": str(JOBS_DIR),
        "jobs": [
            {
                "name": j["name"],
                "description": j["description"],
                "cron": j["cron"],
                "disabled": bool(j.get("disabled", False)),
                "semantic_hooks": j["semantic_hooks"],
                "external_triggers": j.get("external_triggers", []),
                "trigger_command": f'{JOBS_DIR / "trigger-job.sh"} {j["name"]}',
                "prompt_path": j["path"],
            }
            for j in jobs
        ],
    }
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2))


# ---------- fire ----------


def fire(job: dict, trigger: str = "scheduled") -> None:
    """Launch run-job.sh in a detached login shell.

    trigger is stamped into the run's env so the runtime context block the
    job receives knows whether it was fired by cron or by an ad-hoc caller
    (another agent matching a semantic hook, or a human).
    """
    env = os.environ.copy()
    env["CLAUDE_JOB_NAME"] = job["name"]
    env["CLAUDE_JOB_PATH"] = job["path"]
    env["CLAUDE_JOB_CWD"] = job["cwd"]
    env["CLAUDE_JOB_MAX_TURNS"] = str(job["max_turns"])
    env["CLAUDE_JOB_MAX_BUDGET_USD"] = str(job["max_budget_usd"])
    env["CLAUDE_JOB_EFFORT"] = job["effort"]
    env["CLAUDE_JOB_CRON"] = job["cron"]
    env["CLAUDE_JOB_MODEL"] = job.get("model", "")
    ss = job.get("setting_sources")
    # Distinguish "unset" (env var absent) from "empty" (env var set to ""):
    # we need both paths so run-job.sh can tell them apart.
    if ss is not None:
        env["CLAUDE_JOB_SETTING_SOURCES"] = str(ss)
        env["CLAUDE_JOB_SETTING_SOURCES_SET"] = "1"
    if job.get("strict_mcp_config"):
        env["CLAUDE_JOB_STRICT_MCP_CONFIG"] = "1"
    if job.get("debounce_seconds"):
        env["CLAUDE_JOB_DEBOUNCE_SECONDS"] = str(job["debounce_seconds"])
    env["CLAUDE_JOB_TRIGGER"] = trigger
    env["CLAUDE_JOB_FIRED_AT"] = datetime.now(timezone.utc).isoformat()

    # Detached login shell so PATH/nvm/keychain resolve as in Terminal.
    # Job name is passed via env (CLAUDE_JOB_NAME) not as a shell argument,
    # preventing injection from maliciously-named .md files.
    subprocess.Popen(
        ["/bin/zsh", "-lc", str(RUN_JOB)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


# ---------- update check ----------


def load_config() -> dict:
    """Read ~/.claude/scheduled-jobs/.open-claude-cron.config.json.

    Returns defaults (auto-check enabled, hourly, no auto-apply) if the file
    is absent or unparseable. The installer ships a default config file so
    this fallback is mostly relevant during upgrades-in-place.
    """
    defaults = {
        "auto_update": {
            "enabled": True,
            "check_interval_seconds": 3600,
            "auto_apply": False,
        }
    }
    if not CONFIG_PATH.exists():
        return defaults
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError):
        return defaults
    # Merge (shallow) onto defaults so partially-specified configs still work.
    merged = defaults.copy()
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def maybe_check_for_updates() -> None:
    """Periodic rate-limited call to update-check.sh.

    Runs on every tick but only actually does network work when the configured
    interval has elapsed since the last check. Keeps all the HTTP + version
    comparison logic in the shell script (single source of truth).
    """
    cfg = load_config().get("auto_update", {})
    if not cfg.get("enabled", True):
        return
    interval = int(cfg.get("check_interval_seconds", 3600))
    auto_apply = bool(cfg.get("auto_apply", False))

    last = 0
    if UPDATE_LAST_CHECK.exists():
        try:
            last = int(UPDATE_LAST_CHECK.read_text().strip() or "0")
        except (OSError, ValueError):
            last = 0
    now_ts = int(time.time())
    if (now_ts - last) < interval:
        return

    if not UPDATE_CHECK.exists():
        return  # installer didn't ship the script; nothing to do

    # Detached so a slow network check can't block the scheduler tick.
    args = [str(UPDATE_CHECK), "--quiet"]
    if auto_apply:
        args.append("--apply")
    try:
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as e:
        print(f"[scheduler] update-check dispatch failed: {e}", file=sys.stderr)


# ---------- main ----------


def tick() -> None:
    jobs = discover_jobs()
    write_manifest(jobs)
    maybe_check_for_updates()
    now = datetime.now()
    minute_start = int(now.replace(second=0, microsecond=0).timestamp())

    for job in jobs:
        if job.get("disabled"):
            continue  # job is paused; ad-hoc trigger still works

        # Minute-level dedup: if the job was already fired this minute (by
        # any path — cron or external trigger), skip further evaluation.
        if last_run(job["name"]) >= minute_start:
            continue

        # Evaluate external triggers first. If any fires, dispatch and mark
        # last_run so the cron check below won't double-fire.
        if evaluate_external_triggers(job):
            set_last_run(job["name"], minute_start)
            print(f"[scheduler] firing {job['name']} @ {now.isoformat()} (external trigger)")
            fire(job, trigger="external")
            continue

        # Cron evaluation.
        if not job["cron"]:
            continue
        try:
            if not cron_matches(job["cron"], now):
                continue
        except ValueError as e:
            print(f"[scheduler] bad cron for {job['name']}: {e}", file=sys.stderr)
            continue
        # Set last-run BEFORE firing to avoid duplicate launches on a slow tick.
        set_last_run(job["name"], minute_start)
        print(f"[scheduler] firing {job['name']} @ {now.isoformat()}")
        fire(job)


def trigger(name: str) -> None:
    jobs = [j for j in discover_jobs() if j["name"] == name]
    if not jobs:
        print(f"[scheduler] no job named {name!r}", file=sys.stderr)
        sys.exit(2)
    fire(jobs[0], trigger="adhoc")
    print(f"[scheduler] ad-hoc triggered {name}")


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--trigger":
        trigger(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--list":
        for j in discover_jobs():
            print(json.dumps(j))
    else:
        tick()


if __name__ == "__main__":
    main()
