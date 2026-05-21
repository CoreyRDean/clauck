#!/usr/bin/env python3
"""
dag-runner.py — DAG execution engine for producer/consumer job pipelines.

Invoked by scheduler.py when a job has `producers:` in its frontmatter.
Resolves the full dependency graph, executes layers bottom-up in parallel,
injects producer outputs into downstream nodes, and triggers consumers
after the root completes.

Usage:
    /usr/bin/python3 dag-runner.py <root-job-name> [--invocation-id <uuid>]

Requires only /usr/bin/python3 stdlib (no pip dependencies).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


# ---------- paths (mirrors scheduler.py) ----------

HOME = Path(os.environ.get("HOME", str(Path.home())))
JOBS_DIR = HOME / ".clauck"
DAG_LOGS_DIR = JOBS_DIR / ".dag-logs"
STATE_DIR = JOBS_DIR / ".state"
INVOCATION_DIR = STATE_DIR / ".dag-invocations"
MANIFEST_PATH = JOBS_DIR / ".manifest.json"
RUN_JOB = JOBS_DIR / "run-job.sh"
TRIGGER_JOB = JOBS_DIR / "trigger-job.sh"
DISPATCH_LOG = JOBS_DIR / ".scheduler-dispatch.log"
_DISPATCH_LOG_MAX_BYTES = 100 * 1024

DEFAULT_TIMEOUT = 600  # 10 minutes
INVOCATION_TTL_HOURS = 72  # mirrors BROKEN_RETENTION_HOURS in clauck CLI


def _open_dispatch_log():
    """Open the shared dispatch log in append mode, rotating at 100 KB."""
    if DISPATCH_LOG.exists() and DISPATCH_LOG.stat().st_size > _DISPATCH_LOG_MAX_BYTES:
        try:
            DISPATCH_LOG.replace(DISPATCH_LOG.with_suffix(".log.1"))
        except OSError:
            pass
    return open(DISPATCH_LOG, "ab")


# ---------- logging ----------

class DagLogger:
    """Writes structured DAG execution logs and maintains the oplog."""

    def __init__(self, root_name: str, invocation_id: str):
        self.root_name = root_name
        self.invocation_id = invocation_id
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pid = os.getpid()
        self.log_path = DAG_LOGS_DIR / f"{root_name}-{ts}-{pid}.log"
        self.oplog: list[dict] = []
        # Create log file immediately so failures are observable.
        DAG_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self._write(f"=== dag-runner start: {root_name} @ {ts} ===")
        self._write(f"invocation_id={invocation_id}")
        self._write(f"pid={pid}")

    def _write(self, line: str) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._write(f"[{ts}] {msg}")

    def log_event(self, job: str, event: str, layer: int, **kwargs) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "job": job,
            "event": event,
            "layer": layer,
        }
        entry.update(kwargs)
        self.oplog.append(entry)
        self.log(f"event: {json.dumps(entry)}")

    def log_error(self, msg: str) -> None:
        self.log(f"ERROR: {msg}")

    def finalize(self, exit_code: int) -> None:
        self._write(f"--- exit_code={exit_code} ===")


# ---------- manifest loading ----------

def load_manifest() -> dict:
    """Load the manifest from .manifest.json.

    The manifest is written by scheduler.py on every tick. It contains a
    `jobs` array with each job's config. For DAG resolution we also need
    producers/consumers, which the current manifest doesn't include — so
    we fall back to parsing the job .md files directly for those fields.
    """
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_job_configs() -> dict[str, dict]:
    """Build a name->config map by parsing all job .md files.

    Uses the same frontmatter parser as scheduler.py to extract
    producers, consumers, and all other fields. We import the logic
    inline to avoid duplicating the parser.
    """
    # Import scheduler's parser — it lives next to us at runtime.
    scheduler_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scheduler_dir))

    # Also check the installed location.
    if not (scheduler_dir / "scheduler.py").exists():
        sys.path.insert(0, str(JOBS_DIR))

    try:
        from scheduler import discover_jobs, parse_frontmatter
    except ImportError:
        # Fallback: scheduler.py might be at JOBS_DIR (installed location).
        sys.path.insert(0, str(JOBS_DIR))
        from scheduler import discover_jobs, parse_frontmatter

    # Get all discovered jobs (standard fields).
    jobs = discover_jobs()
    configs: dict[str, dict] = {}
    for job in jobs:
        name = job["name"]
        configs[name] = job

        # Parse the .md file again for producers/consumers which
        # discover_jobs doesn't include.
        try:
            text = Path(job["path"]).read_text(encoding="utf-8")
            fm, _body = parse_frontmatter(text)
            configs[name]["producers"] = fm.get("producers", []) or []
            configs[name]["consumers"] = fm.get("consumers", []) or []
        except OSError:
            configs[name]["producers"] = []
            configs[name]["consumers"] = []

    return configs


# ---------- DAG resolution ----------

def resolve_dag(
    root_name: str, configs: dict[str, dict], logger: DagLogger
) -> tuple[list[list[str]], set[str]]:
    """Walk producers recursively from root, detect cycles, topological sort.

    Returns:
        (layers, tree_members) where layers[0] are roots (no producers),
        and tree_members is the set of all job names in the DAG.
    """
    # Collect all nodes reachable via producers from root.
    tree_members: set[str] = set()
    # adjacency: child -> set of parents (producers).
    # For toposort: edges go from producer -> consumer (producer must run first).
    adjacency: dict[str, list[str]] = defaultdict(list)

    def walk(name: str, path: list[str]) -> None:
        if name in path:
            cycle = " -> ".join(path + [name])
            raise CycleError(f"Cycle detected: {cycle}")
        if name not in configs:
            raise MissingJobError(f"Job not found in manifest: {name!r}")
        if name in tree_members:
            return  # Already fully explored from another path; no cycle.
        tree_members.add(name)
        producers = _get_producers(configs[name])
        for prod in producers:
            prod_name = prod["name"]
            adjacency[name].append(prod_name)
            walk(prod_name, path + [name])

    walk(root_name, [])

    # Topological sort using Kahn's algorithm to produce parallel layers.
    # in_degree: number of producers (dependencies) each node has.
    in_degree: dict[str, int] = {n: 0 for n in tree_members}
    # Forward edges: producer -> list of dependents.
    forward: dict[str, list[str]] = defaultdict(list)
    for consumer, producers in adjacency.items():
        for prod in producers:
            forward[prod].append(consumer)
            in_degree[consumer] = in_degree.get(consumer, 0) + 1

    # Make sure all forward-edge targets are counted.
    for prod in forward:
        if prod not in in_degree:
            in_degree[prod] = 0

    layers: list[list[str]] = []
    queue = deque(n for n, deg in in_degree.items() if deg == 0)

    processed = 0
    while queue:
        layer = sorted(queue)  # Deterministic ordering within a layer.
        layers.append(layer)
        next_queue: deque[str] = deque()
        for node in layer:
            processed += 1
            for dependent in forward.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    next_queue.append(dependent)
        queue = next_queue

    if processed < len(tree_members):
        # Some nodes were never enqueued — there's a cycle Kahn's missed
        # (shouldn't happen if walk() caught it, but belt-and-suspenders).
        remaining = tree_members - {n for layer in layers for n in layer}
        raise CycleError(f"Cycle in DAG involving: {remaining}")

    logger.log(f"DAG resolved: {len(tree_members)} nodes, {len(layers)} layers")
    for i, layer in enumerate(layers):
        logger.log(f"  layer {i}: {layer}")

    return layers, tree_members


def _get_producers(job_config: dict) -> list[dict]:
    """Normalize producers field to list of dicts with at least 'name'."""
    raw = job_config.get("producers", []) or []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append({"name": item})
        elif isinstance(item, dict):
            result.append(item)
        else:
            result.append({"name": str(item)})
    return result


def _get_consumers(job_config: dict) -> list[str]:
    """Normalize consumers field to list of job names."""
    raw = job_config.get("consumers", []) or []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(item.get("name", str(item)))
        else:
            result.append(str(item))
    return result


class CycleError(Exception):
    pass


class MissingJobError(Exception):
    pass


# ---------- durable invocation state ----------

def _invocation_state_path(invocation_id: str) -> Path:
    return INVOCATION_DIR / f"{invocation_id}.json"


def write_invocation_state(state: dict) -> None:
    """Persist DAG invocation state atomically so a tripped node can resume."""
    INVOCATION_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _invocation_state_path(state["invocation_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_invocation_state(invocation_id: str) -> dict | None:
    path = _invocation_state_path(invocation_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def delete_invocation_state(invocation_id: str) -> None:
    try:
        _invocation_state_path(invocation_id).unlink(missing_ok=True)
    except OSError:
        pass


def invocation_state_age_hours(state: dict) -> float:
    ts = state.get("updated_at") or state.get("started_at")
    if not ts:
        return 0.0
    try:
        when = datetime.fromisoformat(ts)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - when
        return delta.total_seconds() / 3600.0
    except ValueError:
        return 0.0


# ---------- lock management ----------

def acquire_lock(
    job_name: str, invocation_id: str, source_job: str, logger: DagLogger
) -> Path:
    """Create an advisory lock file for a node within a DAG invocation.

    Lock path: .state/<job>.lock.d/<invocation-id>--<source-job>
    The lock.d directory is the concurrency guard (atomic mkdir).
    Our per-invocation file inside it lets parallel DAG trees coexist
    when the same node appears in multiple trees.
    """
    lock_dir = STATE_DIR / f"{job_name}.lock.d"
    lock_file = lock_dir / f"{invocation_id}--{source_job}"

    # The lock directory may already exist from run-job.sh's own locking.
    # We create our file inside it rather than competing with mkdir.
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        json.dumps({
            "invocation_id": invocation_id,
            "source_job": source_job,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        })
    )
    logger.log(f"lock acquired: {lock_file}")
    return lock_file


def release_lock(lock_file: Path, logger: DagLogger) -> None:
    """Remove the per-invocation lock file."""
    try:
        lock_file.unlink(missing_ok=True)
        logger.log(f"lock released: {lock_file}")
    except OSError as e:
        logger.log_error(f"lock release failed: {lock_file}: {e}")


# ---------- producer output injection ----------

def write_producer_outputs(
    job_name: str,
    invocation_id: str,
    producer_results: dict[str, dict],
    oplog: list[dict],
    logger: DagLogger,
) -> Path:
    """Write the producer-outputs file that run-job.sh will inject.

    Path: .state/<job>.producer-outputs-<invocation-id>.json
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STATE_DIR / f"{job_name}.producer-outputs-{invocation_id}.json"
    payload = {
        "producers": producer_results,
        "oplog": oplog,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.log(f"producer outputs written: {output_path}")
    return output_path


# ---------- job execution ----------

def execute_job(
    job_name: str,
    configs: dict[str, dict],
    invocation_id: str,
    logger: DagLogger,
    layer: int,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Execute a single job via run-job.sh and return its result.

    Returns dict with keys: result, exit_code, cost, log_path, duration_ms.
    """
    job_config = configs.get(job_name)
    if not job_config:
        return {
            "result": f"Job {job_name!r} not found in configs",
            "exit_code": 127,
            "cost": 0.0,
            "log_path": "",
            "duration_ms": 0,
        }

    # Build environment mirroring scheduler.py's fire() function.
    env = os.environ.copy()
    env["CLAUDE_JOB_NAME"] = job_name
    env["CLAUDE_JOB_PATH"] = str(job_config.get("path", ""))
    env["CLAUDE_JOB_CWD"] = str(job_config.get("cwd", str(HOME)))
    env["CLAUDE_JOB_MAX_TURNS"] = str(job_config.get("max_turns", 50))
    env["CLAUDE_JOB_MAX_BUDGET_USD"] = str(job_config.get("max_budget_usd", 2.0))
    env["CLAUDE_JOB_EFFORT"] = str(job_config.get("effort", "high"))
    env["CLAUDE_JOB_CRON"] = str(job_config.get("cron", ""))
    env["CLAUDE_JOB_MODEL"] = str(job_config.get("model", ""))
    env["CLAUDE_JOB_TRIGGER"] = "pipeline"
    env["CLAUDE_JOB_FIRED_AT"] = datetime.now(timezone.utc).isoformat()

    # Setting sources handling (same logic as scheduler.py fire()).
    ss = job_config.get("setting_sources")
    if ss is not None:
        env["CLAUDE_JOB_SETTING_SOURCES"] = str(ss)
        env["CLAUDE_JOB_SETTING_SOURCES_SET"] = "1"
    if job_config.get("strict_mcp_config"):
        env["CLAUDE_JOB_STRICT_MCP_CONFIG"] = "1"
    if job_config.get("debounce_seconds"):
        env["CLAUDE_JOB_DEBOUNCE_SECONDS"] = str(job_config["debounce_seconds"])
    if job_config.get("session_persist"):
        env["CLAUDE_JOB_SESSION_PERSIST"] = "1"
    if job_config.get("trace_tool_calls"):
        env["CLAUDE_JOB_TRACE_TOOL_CALLS"] = "1"

    # DAG-specific env vars so run-job.sh can find the producer outputs.
    env["CLAUDE_DAG_INVOCATION_ID"] = invocation_id
    env["CLAUDE_DAG_ROOT"] = logger.root_name

    lock_file = acquire_lock(job_name, invocation_id, logger.root_name, logger)
    logger.log_event(job_name, "started", layer)

    start_time = time.monotonic()
    try:
        proc = subprocess.run(
            ["/bin/zsh", "-lc", str(RUN_JOB)],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        logger.log_error(f"job {job_name} timed out after {timeout}s")
        logger.log_event(job_name, "timeout", layer, timeout=timeout)
        release_lock(lock_file, logger)
        return {
            "result": f"Timeout after {timeout}s",
            "exit_code": 124,
            "cost": 0.0,
            "log_path": "",
            "duration_ms": int((time.monotonic() - start_time) * 1000),
        }
    except OSError as e:
        logger.log_error(f"job {job_name} execution error: {e}")
        logger.log_event(job_name, "error", layer, error=str(e))
        release_lock(lock_file, logger)
        return {
            "result": f"Execution error: {e}",
            "exit_code": 126,
            "cost": 0.0,
            "log_path": "",
            "duration_ms": int((time.monotonic() - start_time) * 1000),
        }

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # Find the log file created by run-job.sh.
    log_path, result_text, cost = _extract_job_result(job_name)

    logger.log_event(
        job_name, "completed", layer,
        exit_code=exit_code, cost=cost, duration_ms=duration_ms,
    )
    logger.log(f"job {job_name}: exit_code={exit_code} cost={cost} duration={duration_ms}ms")

    release_lock(lock_file, logger)

    return {
        "result": result_text,
        "exit_code": exit_code,
        "cost": cost,
        "log_path": str(log_path),
        "duration_ms": duration_ms,
    }


def _extract_job_result(job_name: str) -> tuple[str, str, float]:
    """Find the most recent log for a job and extract the result from the JSON envelope.

    Returns (log_path, result_text, cost).
    """
    import glob as glob_mod

    pattern = str(JOBS_DIR / f"{job_name}-[0-9]*.log")
    logs = sorted(glob_mod.glob(pattern), reverse=True)
    if not logs:
        return ("", "(no log found)", 0.0)

    log_path = logs[0]
    result_text = ""
    cost = 0.0

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()

        # The JSON envelope is on a single line after "--- prompt body" marker.
        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                envelope = json.loads(line)
                if "result" in envelope:
                    result_text = str(envelope.get("result", ""))
                    cost = float(envelope.get("total_cost_usd", 0.0))
                    break
            except (json.JSONDecodeError, ValueError):
                continue

        if not result_text:
            # Fallback: use the last non-empty, non-marker line.
            for line in reversed(content.splitlines()):
                stripped = line.strip()
                if stripped and not stripped.startswith("---") and not stripped.startswith("==="):
                    result_text = stripped
                    break

    except OSError:
        result_text = "(log unreadable)"

    return (log_path, result_text, cost)


# ---------- consumer delivery ----------

def deliver_to_consumers(
    job_name: str,
    configs: dict[str, dict],
    tree_members: set[str],
    logger: DagLogger,
) -> None:
    """Trigger consumers of a completed job that are NOT in the DAG tree.

    Consumers that are tree_members are skipped (cycle suppression for
    double-linked jobs). External consumers are triggered via trigger-job.sh.
    """
    job_config = configs.get(job_name, {})
    consumers = _get_consumers(job_config)
    if not consumers:
        return

    for consumer in consumers:
        if consumer in tree_members:
            logger.log(f"consumer {consumer} is a tree member — skipped (cycle suppression)")
            continue

        logger.log(f"triggering consumer: {consumer}")
        try:
            dispatch_log = _open_dispatch_log()
            subprocess.Popen(
                ["/bin/zsh", "-lc", f"{TRIGGER_JOB} {consumer}"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=dispatch_log,
                start_new_session=True,
                close_fds=True,
            )
            dispatch_log.close()
            logger.log_event(
                consumer, "consumer_triggered", layer=-1,
                triggered_by=job_name,
            )
        except OSError as e:
            logger.log_error(f"failed to trigger consumer {consumer}: {e}")


# ---------- DAG execution ----------

def execute_dag(
    root_name: str, invocation_id: str, logger: DagLogger,
    resumed_from: dict | None = None,
) -> int:
    """Main DAG execution loop. Returns exit code (0 = success).

    When `resumed_from` is provided (output of read_invocation_state), skip
    jobs whose names already appear in `completed` and reuse their stored
    results for producer-output injection. This delivers true mid-DAG resume:
    completed work is not re-run; the tripped node picks up via its revive
    override (written separately by the CLI); downstream layers continue.
    """

    logger.log("loading job configs...")
    configs = load_job_configs()

    if root_name not in configs:
        logger.log_error(f"root job {root_name!r} not found")
        return 2

    # Resolve the full DAG.
    logger.log("resolving DAG...")
    try:
        layers, tree_members = resolve_dag(root_name, configs, logger)
    except CycleError as e:
        logger.log_error(str(e))
        return 3
    except MissingJobError as e:
        logger.log_error(str(e))
        return 4

    # Build per-producer timeout map from the root's producer declarations.
    timeout_map = _build_timeout_map(root_name, configs)

    # Accumulate results keyed by job name. Seed with prior completions on resume.
    all_results: dict[str, dict] = {}
    if resumed_from:
        prior = resumed_from.get("completed", {}) or {}
        all_results.update(prior)
        logger.log(
            f"resuming invocation {invocation_id}: "
            f"{len(prior)} completed nodes carried forward "
            f"({', '.join(sorted(prior)) or 'none'})"
        )

    # Persist initial invocation state so a mid-run trip is recoverable.
    inv_state = {
        "invocation_id": invocation_id,
        "root": root_name,
        "started_at": (resumed_from or {}).get(
            "started_at", datetime.now(timezone.utc).isoformat()
        ),
        "layers": layers,
        "tree_members": sorted(tree_members),
        "completed": dict(all_results),
        "status": "running",
    }
    write_invocation_state(inv_state)

    # Execute layers bottom-up (layer 0 = roots with no producers).
    for layer_idx, layer in enumerate(layers):
        # Skip jobs that already completed in a prior (pre-trip) run.
        pending = [j for j in layer if j not in all_results]
        if not pending:
            logger.log(f"--- layer {layer_idx} already complete (resume): {layer} ---")
            continue

        logger.log(
            f"--- executing layer {layer_idx}: {pending}"
            + (f" (skipped already-complete: {[j for j in layer if j not in pending]})"
               if len(pending) != len(layer) else "")
            + " ---"
        )

        # Inject producer outputs for jobs in this layer that have producers.
        for job_name in pending:
            producers = _get_producers(configs.get(job_name, {}))
            if producers:
                producer_results = {}
                for prod in producers:
                    prod_name = prod["name"]
                    if prod_name in all_results:
                        producer_results[prod_name] = {
                            "result": all_results[prod_name]["result"],
                            "exit_code": all_results[prod_name]["exit_code"],
                            "cost": all_results[prod_name]["cost"],
                        }
                if producer_results:
                    write_producer_outputs(
                        job_name, invocation_id, producer_results,
                        logger.oplog, logger,
                    )

        # Execute all pending jobs in this layer in parallel.
        layer_results: dict[str, dict] = {}
        if len(pending) == 1:
            # Single job — no thread pool overhead.
            job_name = pending[0]
            timeout = timeout_map.get(job_name, DEFAULT_TIMEOUT)
            layer_results[job_name] = execute_job(
                job_name, configs, invocation_id, logger, layer_idx, timeout,
            )
        else:
            with ThreadPoolExecutor(max_workers=len(pending)) as executor:
                futures = {}
                for job_name in pending:
                    timeout = timeout_map.get(job_name, DEFAULT_TIMEOUT)
                    future = executor.submit(
                        execute_job,
                        job_name, configs, invocation_id, logger, layer_idx, timeout,
                    )
                    futures[future] = job_name

                for future in as_completed(futures):
                    job_name = futures[future]
                    try:
                        layer_results[job_name] = future.result()
                    except Exception as e:
                        logger.log_error(f"unexpected error executing {job_name}: {e}")
                        layer_results[job_name] = {
                            "result": f"Unexpected error: {e}",
                            "exit_code": 1,
                            "cost": 0.0,
                            "log_path": "",
                            "duration_ms": 0,
                        }

        all_results.update(layer_results)

        # Persist progress after every layer so a mid-DAG trip is recoverable.
        # Store only the fields needed for resume (results) — not log-path-only noise.
        inv_state["completed"] = {
            n: {
                "result": r.get("result", ""),
                "exit_code": r.get("exit_code", 0),
                "cost": r.get("cost", 0.0),
                "log_path": r.get("log_path", ""),
                "duration_ms": r.get("duration_ms", 0),
            }
            for n, r in all_results.items()
            if r.get("exit_code", 1) == 0
        }

        # Check for failures — abort if any job in the layer failed.
        failed = [
            name for name, res in layer_results.items()
            if res["exit_code"] != 0
        ]
        if failed:
            logger.log_error(
                f"layer {layer_idx} had failures: "
                + ", ".join(f"{n} (exit={layer_results[n]['exit_code']})" for n in failed)
            )
            logger.log(
                f"aborting DAG execution due to layer failure; "
                f"invocation state preserved at {_invocation_state_path(invocation_id)} "
                f"(revive with: clauck revive <failed-job>)"
            )
            # Deliver to consumers for any completed nodes in THIS layer only
            # (prior layers already delivered when they completed).
            for name in layer_results:
                if layer_results[name]["exit_code"] == 0:
                    deliver_to_consumers(name, configs, tree_members, logger)
            inv_state["status"] = "failed"
            inv_state["failed_layer"] = layer_idx
            inv_state["failed_jobs"] = failed
            write_invocation_state(inv_state)
            return 1

        # Deliver to consumers for all successfully completed nodes in this layer.
        # On resume, only newly-completed nodes are in `pending`; already-completed
        # ones triggered consumers during the original run — don't double-fire.
        for job_name in pending:
            deliver_to_consumers(job_name, configs, tree_members, logger)

        write_invocation_state(inv_state)

    # All layers complete — write final summary and clean up invocation state.
    total_cost = sum(r["cost"] for r in all_results.values())
    total_duration = sum(r["duration_ms"] for r in all_results.values())
    logger.log(
        f"DAG complete: {len(all_results)} jobs, "
        f"total_cost=${total_cost:.4f}, "
        f"total_duration={total_duration}ms"
    )
    inv_state["status"] = "complete"
    inv_state["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_invocation_state(inv_state)
    delete_invocation_state(invocation_id)

    return 0


def _build_timeout_map(root_name: str, configs: dict[str, dict]) -> dict[str, int]:
    """Walk the entire DAG and build a job_name -> timeout_seconds map.

    Timeouts are specified per-producer in the consuming job's frontmatter:
        producers:
          - {name: job-b, timeout_seconds: 300}

    A job may appear as a producer in multiple places with different timeouts;
    we use the maximum to avoid one consumer's tight timeout killing a shared
    producer. Jobs without an explicit timeout get DEFAULT_TIMEOUT.
    """
    timeout_map: dict[str, int] = {}
    visited: set[str] = set()

    def walk(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        config = configs.get(name, {})
        producers = _get_producers(config)
        for prod in producers:
            prod_name = prod["name"]
            t = int(prod.get("timeout_seconds", DEFAULT_TIMEOUT))
            # Use the max if the same producer appears with different timeouts.
            if prod_name in timeout_map:
                timeout_map[prod_name] = max(timeout_map[prod_name], t)
            else:
                timeout_map[prod_name] = t
            walk(prod_name)

    walk(root_name)
    return timeout_map


# ---------- main ----------

def main() -> None:
    if len(sys.argv) < 2:
        print(
            "usage: dag-runner.py <root-job-name> [--invocation-id <uuid>]\n"
            "       dag-runner.py --resume <invocation-id>",
            file=sys.stderr,
        )
        sys.exit(2)

    # --resume <invocation-id>: rehydrate state and continue from the failure point.
    if sys.argv[1] == "--resume":
        if len(sys.argv) < 3:
            print("--resume requires <invocation-id>", file=sys.stderr)
            sys.exit(2)
        invocation_id = sys.argv[2]
        state = read_invocation_state(invocation_id)
        if state is None:
            print(f"no invocation state for {invocation_id}", file=sys.stderr)
            sys.exit(4)
        age_h = invocation_state_age_hours(state)
        if age_h > INVOCATION_TTL_HOURS:
            print(
                f"invocation {invocation_id} is {age_h:.1f}h old "
                f"(TTL: {INVOCATION_TTL_HOURS}h) — upstream promises likely expired",
                file=sys.stderr,
            )
            sys.exit(5)
        root_name = state["root"]
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        logger = DagLogger(root_name, invocation_id)
        logger.log(f"RESUME: root={root_name} invocation_id={invocation_id} age={age_h:.2f}h")
        try:
            exit_code = execute_dag(root_name, invocation_id, logger, resumed_from=state)
        except Exception as e:
            logger.log_error(f"fatal during resume: {e}")
            import traceback
            logger.log(traceback.format_exc())
            exit_code = 99
        logger.finalize(exit_code)
        sys.exit(exit_code)

    root_name = sys.argv[1]

    # Parse optional --invocation-id.
    invocation_id = str(uuid.uuid4())
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--invocation-id" and i + 1 < len(args):
            invocation_id = args[i + 1]
            i += 2
        else:
            print(f"unknown argument: {args[i]}", file=sys.stderr)
            sys.exit(2)

    # Ensure state directory exists.
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    logger = DagLogger(root_name, invocation_id)
    logger.log(f"root={root_name} invocation_id={invocation_id}")

    try:
        exit_code = execute_dag(root_name, invocation_id, logger)
    except Exception as e:
        logger.log_error(f"fatal: {e}")
        import traceback
        logger.log(traceback.format_exc())
        exit_code = 99

    logger.finalize(exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
