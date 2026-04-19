#!/usr/bin/env python3
"""
scheduler.py — auto-discover scheduled-job prompts and fire due ones.

Runs once per minute under a launchd LaunchAgent. On each tick:
  1. Scans ~/.clauck/*.md for job prompts.
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

# Sizing helpers — shared with the CLI. Same loader pattern as lib/clauck so
# the module works from either the installed location (~/.clauck/sizing.py)
# or the dev-tree (lib/sizing.py, when scheduler.py is run uninstalled).
try:
    _SIZING_DIR = Path(os.environ.get("HOME", str(Path.home()))) / ".clauck"
    if not (_SIZING_DIR / "sizing.py").exists():
        _SIZING_DIR = Path(__file__).resolve().parent
    sys.path.insert(0, str(_SIZING_DIR))
    import sizing  # type: ignore[import-not-found]
finally:
    if str(_SIZING_DIR) in sys.path:
        sys.path.remove(str(_SIZING_DIR))

HOME = Path(os.environ.get("HOME", str(Path.home())))
JOBS_DIR = HOME / ".clauck"
STATE_DIR = JOBS_DIR / ".state"
GLOBAL_PROMPT = JOBS_DIR / "prompt.md"
MANIFEST_PATH = JOBS_DIR / ".manifest.json"
RUN_JOB = JOBS_DIR / "run-job.sh"
DAG_RUNNER = JOBS_DIR / "dag-runner.py"
UPDATE_CHECK = JOBS_DIR / "update-check.sh"
CONFIG_PATH = JOBS_DIR / ".clauck.config.json"
UPDATE_LAST_CHECK = STATE_DIR / ".update-last-check"
DISPATCH_LOG = JOBS_DIR / ".scheduler-dispatch.log"
_DISPATCH_LOG_MAX_BYTES = 100 * 1024  # rotate at 100 KB


def _open_dispatch_log():
    """Open the dispatch log in append mode, rotating if it exceeds the size cap.

    Returns an open file object (binary append). Caller is responsible for
    closing it after the subprocess is launched (child retains its own copy
    of the fd after fork).
    """
    if DISPATCH_LOG.exists() and DISPATCH_LOG.stat().st_size > _DISPATCH_LOG_MAX_BYTES:
        rotated = DISPATCH_LOG.with_suffix(".log.1")
        try:
            DISPATCH_LOG.replace(rotated)
        except OSError:
            pass  # best-effort; if rename fails, continue appending
    return open(DISPATCH_LOG, "ab")


# Files with these stems are skipped even if they live in jobs dir.
RESERVED_STEMS = {"scheduler", "run-job", "trigger-job", "update-check", "prompt"}


# ---------- frontmatter ----------

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    return _parse_yaml_subset(m.group(1)), m.group(2)


def _strip_inline_comment(value: str) -> str:
    """Strip trailing YAML inline comment (` #...`), respecting quotes.

    YAML's rule: `#` starts a comment only when preceded by whitespace or is
    at the start of a line, AND only when not inside a quoted string. So:
      complexity: 0.15   # comment       → 0.15
      description: "a # b"               → "a # b"   (# is inside quotes)
      slug: "foo#bar"                    → "foo#bar" (no preceding space)
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(value):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or value[i - 1].isspace():
                return value[:i].rstrip()
    return value


def _parse_yaml_subset(block: str) -> dict:
    """Minimal YAML supporting:
      - flat scalars: `key: value`
      - simple string lists: `- value`
      - list-of-objects in flow style: `- {key: value, key: value}`
      - inline `#` comments trailing a scalar value
    No nested block-style maps.
    """
    data: dict = {}
    current_list_key: str | None = None
    for raw in block.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key is not None:
            item = _strip_inline_comment(stripped[2:].strip())
            if item.startswith("{") and item.endswith("}"):
                data[current_list_key].append(_parse_flow_object(item))
            else:
                data[current_list_key].append(_strip_quotes(item))
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = _strip_inline_comment(val.strip())
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


def _load_scheduler_sizing_config() -> dict:
    """Load sizing config for scheduler-time resolution.

    Takes the doctor block (for min_budget_usd / max_budget_usd / headroom /
    context_growth_per_turn) but **forces scale_skew=0**. Rationale: the
    skew is auto-bumped when DOCTOR hits its budget — that signal is about
    doctor task shapes and must not cross-contaminate every scheduled job.
    A user whose doctor has been auto-bumped to +0.20 shouldn't see every
    cron-fired job also skewed upward when those jobs never truncated.

    Loaded once per tick (not per job) — called from discover_jobs().
    """
    cfg = sizing.load_doctor_config()
    cfg = dict(cfg)
    cfg["scale_skew"] = 0.0
    return cfg


def _resolve_sizing(fm: dict, body: str, cfg: dict) -> dict:
    """Resolve model/effort/max_turns/max_budget_usd via sizing.resolve_params.

    Called once per job per tick when building the manifest. If the frontmatter
    has `complexity:`, the four sizing fields derive from that + any explicit
    overrides. If not, legacy defaults apply.

    Body tokens are estimated from the prompt body (post-frontmatter text) so
    the context-injection tax in the derived budget reflects at least the
    prompt body. Producer outputs are added at fire time by run-job.sh, and
    are not known here — but the static body estimate is the right lower
    bound for scheduler-time resolution.

    `cfg` is passed in (not loaded per-call) so the whole tick shares one
    config read — called ~20 times per tick at 20 jobs × 60s ticks that's
    a ~30k disk-read/day savings.
    """
    try:
        body_tokens = sizing.estimate_tokens(body)
        return sizing.resolve_params(fm, body_tokens, cfg)
    except Exception as e:  # noqa: BLE001 — scheduler must never crash on sizing
        print(f"[scheduler] sizing resolution failed: {e}", file=sys.stderr)
        return {
            "model": str(fm.get("model", "")).strip(),
            "effort": str(fm.get("effort", "high")),
            "max_turns": int(fm.get("max_turns", 50) or 50),
            "max_budget_usd": float(fm.get("max_budget_usd", 2.0) or 2.0),
            "provenance": {},
            "sizing": None,
        }


def discover_jobs() -> list[dict]:
    jobs: list[dict] = []
    if not JOBS_DIR.is_dir():
        return jobs
    # Load the sizing config once per tick and share it across every job's
    # resolution — avoids ~20 redundant disk reads per tick at ~20 jobs.
    # scale_skew is forced to 0 for scheduled jobs (see _load_scheduler_sizing_config).
    sizing_cfg = _load_scheduler_sizing_config()
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
        resolved = _resolve_sizing(fm, _body, sizing_cfg)
        jobs.append(
            {
                "name": str(name),
                "path": str(md),
                "description": str(fm.get("description", "")),
                "cron": str(fm.get("cron", "")).strip(),
                "max_turns": int(resolved["max_turns"]),
                "max_budget_usd": float(resolved["max_budget_usd"]),
                "cwd": os.path.expanduser(str(fm.get("cwd") or "~")),
                "effort": str(resolved["effort"]),
                "model": str(resolved["model"]).strip(),
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
                # --- temporal scheduling ---
                # run_once: if true, auto-disable after first fire.
                "run_once": bool(fm.get("run_once", False)),
                # max_runs: auto-disable after N fires. 0 = unlimited.
                "max_runs": int(fm.get("max_runs", 0) or 0),
                # valid_after: ISO8601 date or datetime. Scheduler skips until
                # now >= this. e.g. "2026-05-01" or "2026-05-01T09:00:00".
                "valid_after": str(fm.get("valid_after", "")).strip(),
                # expires_after: ISO8601 date or datetime. Scheduler auto-disables
                # once now > this.
                "expires_after": str(fm.get("expires_after", "")).strip(),
                # --- session ---
                # session_persist: if true, run-job.sh passes --resume to
                # reuse the same session across runs (cross-run context).
                "session_persist": bool(fm.get("session_persist", False)),
                # interactive: if true, opens a Terminal window with the
                # running session visible, and leaves it open for user
                # follow-up after completion.
                "interactive": bool(fm.get("interactive", False)),
                # trace_tool_calls: if true, switches output format to
                # stream-json so every tool call appears in the log.
                # Useful for pipeline debugging.
                "trace_tool_calls": bool(fm.get("trace_tool_calls", False)),
                # --- triggers ---
                # external_triggers: list of flow-style-object conditions that,
                # if met, cause the job to fire between cron slots. Evaluated
                # each tick. See eval_* functions for supported types.
                "external_triggers": list(fm.get("external_triggers", []) or []),
                "semantic_hooks": list(fm.get("semantic_hooks", []) or []),
                # tags: freeform string list for categorization, filtering, and
                # marketplace search. Not used by the scheduler itself.
                "tags": list(fm.get("tags", []) or []),
                # --- pipeline ---
                "producers": list(fm.get("producers", []) or []),
                "consumers": list(fm.get("consumers", []) or []),
                # --- inputs ---
                "inputs": list(fm.get("inputs", []) or []),
                # --- module ---
                "module_root": "",
                # module_parent names the anchor job of the enclosing module, if any.
                # Empty for flat jobs and module anchors; set only on module-internal
                # stages so tick/trigger/manifest can filter them out while the DAG
                # runner still sees them for producer resolution.
                "module_parent": "",
            }
        )

    # Discover module-format jobs: <name>/JOB.md
    for job_dir in sorted(JOBS_DIR.iterdir()):
        if not job_dir.is_dir():
            continue
        if job_dir.name.startswith("."):
            continue
        job_md = job_dir / "JOB.md"
        if not job_md.exists():
            continue
        # This is a module — JOB.md is the entry point
        try:
            text = job_md.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[scheduler] read error {job_md}: {e}", file=sys.stderr)
            continue
        fm, _body = parse_frontmatter(text)
        name = fm.get("name") or job_dir.name
        resolved = _resolve_sizing(fm, _body, sizing_cfg)
        # Build the job dict same as flat format, plus module_root
        jobs.append(
            {
                "name": str(name),
                "path": str(job_md),
                "description": str(fm.get("description", "")),
                "cron": str(fm.get("cron", "")).strip(),
                "max_turns": int(resolved["max_turns"]),
                "max_budget_usd": float(resolved["max_budget_usd"]),
                "cwd": os.path.expanduser(str(fm.get("cwd") or "~")),
                "effort": str(resolved["effort"]),
                "model": str(resolved["model"]).strip(),
                "setting_sources": fm.get("setting_sources", None),
                "strict_mcp_config": bool(fm.get("strict_mcp_config", False)),
                "debounce_seconds": int(fm.get("debounce_seconds", 0) or 0),
                "disabled": bool(fm.get("disabled", False)),
                "run_once": bool(fm.get("run_once", False)),
                "max_runs": int(fm.get("max_runs", 0) or 0),
                "valid_after": str(fm.get("valid_after", "")).strip(),
                "expires_after": str(fm.get("expires_after", "")).strip(),
                "session_persist": bool(fm.get("session_persist", False)),
                "interactive": bool(fm.get("interactive", False)),
                "trace_tool_calls": bool(fm.get("trace_tool_calls", False)),
                "external_triggers": list(fm.get("external_triggers", []) or []),
                "semantic_hooks": list(fm.get("semantic_hooks", []) or []),
                "tags": list(fm.get("tags", []) or []),
                "producers": list(fm.get("producers", []) or []),
                "consumers": list(fm.get("consumers", []) or []),
                "inputs": list(fm.get("inputs", []) or []),
                "module_root": str(job_dir),  # extra field for modules
                # Module anchors are user-facing; module_parent stays empty.
                "module_parent": "",
            }
        )

        # Discover module-internal stages: <module>/*.md (excluding JOB.md).
        # These are NOT fired independently by the scheduler — they're only
        # reachable through the module anchor's producer DAG. But dag-runner.py
        # needs them in its configs map to resolve producers declared on the
        # anchor, so we register them here with module_parent set.
        anchor_name = str(name)
        for stage_md in sorted(job_dir.glob("*.md")):
            if stage_md.name == "JOB.md":
                continue
            if stage_md.name.startswith("."):
                continue
            try:
                stage_text = stage_md.read_text(encoding="utf-8")
            except OSError as e:
                print(f"[scheduler] read error {stage_md}: {e}", file=sys.stderr)
                continue
            stage_fm, _stage_body = parse_frontmatter(stage_text)
            stage_name = stage_fm.get("name") or stage_md.stem
            stage_resolved = _resolve_sizing(stage_fm, _stage_body, sizing_cfg)
            jobs.append(
                {
                    "name": str(stage_name),
                    "path": str(stage_md),
                    "description": str(stage_fm.get("description", "")),
                    "cron": str(stage_fm.get("cron", "")).strip(),
                    "max_turns": int(stage_resolved["max_turns"]),
                    "max_budget_usd": float(stage_resolved["max_budget_usd"]),
                    "cwd": os.path.expanduser(str(stage_fm.get("cwd") or "~")),
                    "effort": str(stage_resolved["effort"]),
                    "model": str(stage_resolved["model"]).strip(),
                    "setting_sources": stage_fm.get("setting_sources", None),
                    "strict_mcp_config": bool(stage_fm.get("strict_mcp_config", False)),
                    "debounce_seconds": int(stage_fm.get("debounce_seconds", 0) or 0),
                    "disabled": bool(stage_fm.get("disabled", False)),
                    "run_once": bool(stage_fm.get("run_once", False)),
                    "max_runs": int(stage_fm.get("max_runs", 0) or 0),
                    "valid_after": str(stage_fm.get("valid_after", "")).strip(),
                    "expires_after": str(stage_fm.get("expires_after", "")).strip(),
                    "session_persist": bool(stage_fm.get("session_persist", False)),
                    "interactive": bool(stage_fm.get("interactive", False)),
                    "trace_tool_calls": bool(stage_fm.get("trace_tool_calls", False)),
                    "external_triggers": list(stage_fm.get("external_triggers", []) or []),
                    "semantic_hooks": list(stage_fm.get("semantic_hooks", []) or []),
                    "tags": list(stage_fm.get("tags", []) or []),
                    "producers": list(stage_fm.get("producers", []) or []),
                    "consumers": list(stage_fm.get("consumers", []) or []),
                    "inputs": list(stage_fm.get("inputs", []) or []),
                    "module_root": str(job_dir),
                    "module_parent": anchor_name,
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


def is_auto_disabled(name: str) -> bool:
    return (STATE_DIR / f"{name}.auto-disabled").exists()


def auto_disable(name: str, reason: str) -> None:
    """Mark a job as auto-disabled (run_once exhausted, max_runs hit, expired).

    Creates a state file rather than editing the .md frontmatter — safer and
    reversible (delete the file to re-enable). The file contains the reason
    for debugging.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{name}.auto-disabled").write_text(
        json.dumps({"reason": reason, "at": datetime.now(timezone.utc).isoformat()})
    )
    print(f"[scheduler] auto-disabled {name}: {reason}")


def get_runs_remaining(name: str) -> int | None:
    """Read the runs-remaining counter. Returns None if not set."""
    p = STATE_DIR / f"{name}.runs-remaining"
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return None


def decrement_runs_remaining(name: str) -> int:
    """Decrement and return the new count. Returns 0 if file missing."""
    p = STATE_DIR / f"{name}.runs-remaining"
    current = get_runs_remaining(name) or 0
    new = max(0, current - 1)
    p.write_text(str(new))
    return new


def parse_datetime_lenient(s: str) -> datetime | None:
    """Parse ISO8601 date or datetime. Returns None on failure.

    Accepts: "2026-05-01", "2026-05-01T09:00:00", "2026-05-01T09:00:00Z",
    "2026-05-01T09:00:00+00:00". Date-only is treated as midnight local time.
    """
    if not s:
        return None
    s = s.strip()
    try:
        # Full datetime
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        # Date only → midnight local
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


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


def detect_cycles(jobs):
    """Check for cycles in the producer graph. Returns list of error strings."""
    # Build adjacency: job -> its producers
    graph = {}
    names = set()
    for j in jobs:
        name = j["name"]
        names.add(name)
        producers = [p["name"] if isinstance(p, dict) else p for p in j.get("producers", [])]
        graph[name] = producers

    errors = []
    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in names}

    def dfs(node, path):
        if node not in color:
            errors.append(f"producer '{node}' referenced but no job file exists")
            return
        if color[node] == GRAY:
            cycle = path[path.index(node):]
            errors.append(f"cycle detected: {' -> '.join(cycle + [node])}")
            return
        if color[node] == BLACK:
            return
        color[node] = GRAY
        path.append(node)
        for dep in graph.get(node, []):
            dfs(dep, path)
        path.pop()
        color[node] = BLACK

    for name in names:
        if color[name] == WHITE:
            dfs(name, [])
    return errors


def write_manifest(jobs: list[dict]) -> None:
    # User-facing manifest: hide module-internal stages so `clauck list`, the
    # SessionStart hook, and semantic interpreters see only directly-fireable
    # jobs. The internals remain visible to dag-runner.py via discover_jobs().
    visible_jobs = [j for j in jobs if not j.get("module_parent")]
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
                "tags": j.get("tags", []),
                "external_triggers": j.get("external_triggers", []),
                "producers": j.get("producers", []),
                "consumers": j.get("consumers", []),
                "inputs": j.get("inputs", []),
                "trigger_command": f'{JOBS_DIR / "trigger-job.sh"} {j["name"]}',
                "prompt_path": j["path"],
                "module_root": j.get("module_root", ""),
                "session_persist": bool(j.get("session_persist", False)),
            }
            for j in visible_jobs
        ],
    }
    # Cycle detection uses the full job set (including internals) so
    # module-internal producer chains are validated too.
    dag_errors = detect_cycles(jobs)
    if dag_errors:
        payload["dag_errors"] = dag_errors
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
    if job.get("session_persist"):
        env["CLAUDE_JOB_SESSION_PERSIST"] = "1"
    if job.get("interactive"):
        env["CLAUDE_JOB_INTERACTIVE"] = "1"
    if job.get("trace_tool_calls"):
        env["CLAUDE_JOB_TRACE_TOOL_CALLS"] = "1"
    env["CLAUDE_JOB_TRIGGER"] = trigger
    env["CLAUDE_JOB_FIRED_AT"] = datetime.now(timezone.utc).isoformat()

    # Detached login shell so PATH/nvm/keychain resolve as in Terminal.
    # Job name is passed via env (CLAUDE_JOB_NAME) not as a shell argument,
    # preventing injection from maliciously-named .md files.
    # stderr → dispatch log so failures before the job log is created are visible.
    dispatch_log = _open_dispatch_log()
    subprocess.Popen(
        ["/bin/zsh", "-lc", str(RUN_JOB)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=dispatch_log,
        start_new_session=True,
        close_fds=True,
    )
    dispatch_log.close()


def fire_dag(job: dict, trigger: str = "scheduled") -> None:
    """Launch dag-runner.py in a detached subprocess for a pipeline job.

    Builds the same env-var set as fire() (plus CLAUDE_JOB_TRIGGER) and
    delegates execution to dag-runner.py, which handles topological sort,
    parallel layer execution, and output injection.
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
    env["CLAUDE_JOB_TRIGGER"] = trigger
    env["CLAUDE_JOB_FIRED_AT"] = datetime.now(timezone.utc).isoformat()
    dispatch_log = _open_dispatch_log()
    subprocess.Popen(
        ["/usr/bin/python3", str(DAG_RUNNER), job["name"]],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=dispatch_log,
        start_new_session=True,
        close_fds=True,
    )
    dispatch_log.close()


# ---------- update check ----------


def load_config() -> dict:
    """Read ~/.clauck/.clauck.config.json.

    Returns defaults (auto-check enabled, hourly, no auto-apply) if the file
    is absent or unparseable. The installer ships a default config file so
    this fallback is mostly relevant during upgrades-in-place.
    """
    defaults = {
        "auto_update": {
            "enabled": True,
            "check_interval_seconds": 3600,
            "auto_apply": False,
        },
        "output_dir": "~/Documents/clauck",
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
        dispatch_log = _open_dispatch_log()
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=dispatch_log,
            start_new_session=True,
            close_fds=True,
        )
        dispatch_log.close()
    except OSError as e:
        print(f"[scheduler] update-check dispatch failed: {e}", file=sys.stderr)


# ---------- main ----------


def _cleanup_stale_tombstones(retention_hours: int = 72) -> None:
    """Remove tombstones and expired DAG invocation state after retention_hours.

    Tombstones live in ~/.clauck/.broken/; DAG invocation state (used by
    `clauck revive` to drive true mid-DAG resume) lives in
    ~/.clauck/.state/.dag-invocations/. Both share the same TTL so an expired
    tombstone and its matching invocation state get reaped in lockstep.
    """
    cutoff = datetime.now().timestamp() - retention_hours * 3600
    for sub in (JOBS_DIR / ".broken", JOBS_DIR / ".state" / ".dag-invocations"):
        if not sub.exists():
            continue
        for p in sub.glob("*.json"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass


def tick() -> None:
    jobs = discover_jobs()
    write_manifest(jobs)
    maybe_check_for_updates()
    _cleanup_stale_tombstones()
    now = datetime.now()
    minute_start = int(now.replace(second=0, microsecond=0).timestamp())

    for job in jobs:
        name = job["name"]

        # Module-internal stages are only reachable via their module's DAG.
        # Never fire them directly from the tick loop — that would execute
        # them out of order and without producer context.
        if job.get("module_parent"):
            continue

        if job.get("disabled") or is_auto_disabled(name):
            continue  # paused (manual or auto); ad-hoc trigger still works

        # --- Temporal validity gates ---
        va = job.get("valid_after", "")
        if va:
            valid_dt = parse_datetime_lenient(va)
            if valid_dt and now < valid_dt:
                continue  # not yet valid

        ea = job.get("expires_after", "")
        if ea:
            expires_dt = parse_datetime_lenient(ea)
            if expires_dt and now > expires_dt:
                auto_disable(name, f"expired (expires_after={ea})")
                continue

        # max_runs: initialize counter on first encounter, skip if exhausted.
        mr = job.get("max_runs", 0)
        if mr > 0:
            remaining = get_runs_remaining(name)
            if remaining is None:
                # First time seeing this job — initialize counter.
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                (STATE_DIR / f"{name}.runs-remaining").write_text(str(mr))
            elif remaining <= 0:
                auto_disable(name, f"max_runs exhausted (max_runs={mr})")
                continue

        # --- Minute-level dedup ---
        if last_run(name) >= minute_start:
            continue

        # --- Evaluate triggers and cron ---
        fired = False

        # External triggers first.
        if evaluate_external_triggers(job):
            set_last_run(name, minute_start)
            print(f"[scheduler] firing {name} @ {now.isoformat()} (external trigger)")
            if job.get("producers"):
                fire_dag(job, trigger="external")
            else:
                fire(job, trigger="external")
            fired = True
        else:
            # Cron evaluation.
            if job["cron"]:
                try:
                    if cron_matches(job["cron"], now):
                        set_last_run(name, minute_start)
                        print(f"[scheduler] firing {name} @ {now.isoformat()}")
                        if job.get("producers"):
                            fire_dag(job, trigger="scheduled")
                        else:
                            fire(job)
                        fired = True
                except ValueError as e:
                    print(f"[scheduler] bad cron for {name}: {e}", file=sys.stderr)

        # --- Post-fire temporal bookkeeping ---
        if fired:
            if job.get("run_once"):
                auto_disable(name, "run_once=true (one-shot job)")

            if mr > 0:
                new_remaining = decrement_runs_remaining(name)
                if new_remaining <= 0:
                    auto_disable(name, f"max_runs exhausted (max_runs={mr})")


def trigger(name: str) -> None:
    jobs = [j for j in discover_jobs() if j["name"] == name]
    if not jobs:
        print(f"[scheduler] no job named {name!r}", file=sys.stderr)
        sys.exit(2)
    job = jobs[0]
    # Reject direct triggering of module-internal stages — they're only meant
    # to run as part of their enclosing module's DAG. Fire the anchor instead.
    parent = job.get("module_parent")
    if parent:
        print(
            f"[scheduler] {name!r} is a module-internal stage of {parent!r}; "
            f"fire the module anchor ({parent}) instead",
            file=sys.stderr,
        )
        sys.exit(2)
    # If the job has producers, delegate to the DAG runner instead of direct fire.
    if job.get("producers"):
        fire_dag(job, trigger="adhoc")
    else:
        fire(job, trigger="adhoc")
    print(f"[scheduler] ad-hoc triggered {name}")


def substitute_bash_templates(body: str) -> tuple[str, list[str]]:
    """Expand ``{{cmd: shell_command}}`` markers in a prompt body.

    Returns ``(expanded_body, log_lines)``.  Each marker is evaluated via
    ``zsh -lc`` with a 5-second timeout; stdout replaces the marker (capped at
    2048 chars).  On failure the marker is replaced with a visible
    ``[cmd-error: ...]`` string so failures are always observable.
    """
    import re
    import subprocess

    log_lines: list[str] = []

    def _substitute(m: "re.Match[str]") -> str:
        cmd = m.group(1).strip()
        log_lines.append(f"  cmd={cmd[:80]!r}")
        try:
            r = subprocess.run(
                ["/bin/zsh", "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = r.stdout
            if len(out) > 2048:
                out = out[:2048] + "...[truncated]"
            if r.returncode != 0:
                log_lines.append(f"  exit={r.returncode}")
                return f"[cmd-error: exit {r.returncode}: {r.stderr.strip()[:200]}]"
            log_lines.append(f"  ok len={len(out.strip())}")
            return out.strip()
        except subprocess.TimeoutExpired:
            log_lines.append("  timeout")
            return "[cmd-error: timeout after 5s]"
        except Exception as e:  # noqa: BLE001
            log_lines.append(f"  exception: {e}")
            return f"[cmd-error: {e}]"

    expanded = re.sub(r"\{\{cmd:\s*(.*?)\}\}", _substitute, body)
    return expanded, log_lines


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
