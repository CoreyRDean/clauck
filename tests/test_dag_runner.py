"""Unit tests for pure-function components of lib/dag-runner.py.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

# dag-runner.py has a hyphen in its name, so it cannot be imported via
# the normal `import` statement.  Use importlib to load it by file path.
import importlib.util

_DAG_RUNNER_PATH = Path(__file__).parent.parent / "lib" / "dag-runner.py"
_spec = importlib.util.spec_from_file_location("dag_runner", _DAG_RUNNER_PATH)
dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dr)


# ---------------------------------------------------------------------------
# Minimal DagLogger stub — satisfies the logger protocol without touching disk.
# ---------------------------------------------------------------------------

class _NullLogger:
    """Drop-in for DagLogger that records calls in memory instead of writing files."""

    def __init__(self):
        self.lines: list[str] = []
        self.events: list[dict] = []
        self.errors: list[str] = []
        self.oplog: list[dict] = []

    def log(self, msg: str) -> None:
        self.lines.append(msg)

    def log_event(self, job: str, event: str, layer: int, **kwargs) -> None:
        entry = {"job": job, "event": event, "layer": layer}
        entry.update(kwargs)
        self.events.append(entry)
        self.oplog.append(entry)

    def log_error(self, msg: str) -> None:
        self.errors.append(msg)

    def finalize(self, exit_code: int) -> None:
        pass


def _logger() -> _NullLogger:
    return _NullLogger()


# ---------------------------------------------------------------------------
# _get_producers
# ---------------------------------------------------------------------------

class TestGetProducers(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(dr._get_producers({}), [])

    def test_none_value(self):
        self.assertEqual(dr._get_producers({"producers": None}), [])

    def test_string_items(self):
        cfg = {"producers": ["job-a", "job-b"]}
        result = dr._get_producers(cfg)
        self.assertEqual(result, [{"name": "job-a"}, {"name": "job-b"}])

    def test_dict_items(self):
        cfg = {"producers": [{"name": "job-a", "timeout_seconds": 30}]}
        result = dr._get_producers(cfg)
        self.assertEqual(result, [{"name": "job-a", "timeout_seconds": 30}])

    def test_mixed_string_and_dict(self):
        cfg = {"producers": ["job-a", {"name": "job-b", "timeout_seconds": 60}]}
        result = dr._get_producers(cfg)
        self.assertEqual(result[0], {"name": "job-a"})
        self.assertEqual(result[1]["name"], "job-b")

    def test_single_string(self):
        cfg = {"producers": ["only-job"]}
        result = dr._get_producers(cfg)
        self.assertEqual(result, [{"name": "only-job"}])


# ---------------------------------------------------------------------------
# _get_consumers
# ---------------------------------------------------------------------------

class TestGetConsumers(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(dr._get_consumers({}), [])

    def test_none_value(self):
        self.assertEqual(dr._get_consumers({"consumers": None}), [])

    def test_string_items(self):
        cfg = {"consumers": ["job-a", "job-b"]}
        self.assertEqual(dr._get_consumers(cfg), ["job-a", "job-b"])

    def test_dict_items(self):
        cfg = {"consumers": [{"name": "job-a"}]}
        self.assertEqual(dr._get_consumers(cfg), ["job-a"])

    def test_mixed_string_and_dict(self):
        cfg = {"consumers": ["job-a", {"name": "job-b"}]}
        self.assertEqual(dr._get_consumers(cfg), ["job-a", "job-b"])

    def test_single_string(self):
        cfg = {"consumers": ["notify"]}
        self.assertEqual(dr._get_consumers(cfg), ["notify"])


# ---------------------------------------------------------------------------
# resolve_dag — helpers
# ---------------------------------------------------------------------------

def _make_configs(**jobs):
    """Build a configs dict from keyword args.

    Usage: _make_configs(root=[], step1=["root"], step2=["step1"])
    Each value is the list of producer names (strings or dicts).
    """
    return {
        name: {"producers": producers, "consumers": []}
        for name, producers in jobs.items()
    }


# ---------------------------------------------------------------------------
# resolve_dag — structure
# ---------------------------------------------------------------------------

class TestResolveDagStructure(unittest.TestCase):
    def test_single_node_no_producers(self):
        """A root with no producers produces a single layer containing just itself."""
        configs = _make_configs(root=[])
        layers, members = dr.resolve_dag("root", configs, _logger())
        self.assertEqual(layers, [["root"]])
        self.assertEqual(members, {"root"})

    def test_linear_chain(self):
        """A -> B -> C: layers should be [[C], [B], [A]] (leaf first)."""
        configs = _make_configs(A=["B"], B=["C"], C=[])
        layers, members = dr.resolve_dag("A", configs, _logger())
        self.assertEqual(layers[0], ["C"])
        self.assertEqual(layers[1], ["B"])
        self.assertEqual(layers[2], ["A"])
        self.assertEqual(members, {"A", "B", "C"})

    def test_diamond_dag(self):
        """A depends on B and C; B and C both depend on D.
        Expected layers: [D], [B, C], [A].
        """
        configs = _make_configs(A=["B", "C"], B=["D"], C=["D"], D=[])
        layers, members = dr.resolve_dag("A", configs, _logger())
        self.assertEqual(layers[0], ["D"])
        self.assertIn("B", layers[1])
        self.assertIn("C", layers[1])
        self.assertEqual(layers[2], ["A"])
        self.assertEqual(members, {"A", "B", "C", "D"})

    def test_two_independent_producers(self):
        """Root depends on two leaf nodes with no shared sub-producers.
        Both leaves must be in the same layer.
        """
        configs = _make_configs(root=["leafA", "leafB"], leafA=[], leafB=[])
        layers, members = dr.resolve_dag("root", configs, _logger())
        self.assertEqual(len(layers), 2)
        self.assertIn("leafA", layers[0])
        self.assertIn("leafB", layers[0])
        self.assertEqual(layers[1], ["root"])

    def test_layer_ordering_deterministic(self):
        """Nodes within a layer are sorted alphabetically for determinism."""
        configs = _make_configs(root=["z-job", "a-job"], **{"a-job": [], "z-job": []})
        layers, _ = dr.resolve_dag("root", configs, _logger())
        self.assertEqual(layers[0], ["a-job", "z-job"])

    def test_members_includes_all_reachable_nodes(self):
        """Tree members must contain every transitively reachable producer."""
        configs = _make_configs(A=["B"], B=["C"], C=["D"], D=[])
        _, members = dr.resolve_dag("A", configs, _logger())
        self.assertEqual(members, {"A", "B", "C", "D"})

    def test_deep_chain_layer_count(self):
        """A five-deep linear chain must produce exactly five layers."""
        configs = _make_configs(
            e=["d"], d=["c"], c=["b"], b=["a"], a=[]
        )
        layers, _ = dr.resolve_dag("e", configs, _logger())
        self.assertEqual(len(layers), 5)

    def test_producer_dict_form_resolved(self):
        """Producers expressed as dicts (with timeout) are resolved correctly."""
        configs = {
            "root": {"producers": [{"name": "dep", "timeout_seconds": 300}], "consumers": []},
            "dep": {"producers": [], "consumers": []},
        }
        layers, members = dr.resolve_dag("root", configs, _logger())
        self.assertIn("dep", members)
        self.assertEqual(layers[0], ["dep"])
        self.assertEqual(layers[1], ["root"])


# ---------------------------------------------------------------------------
# resolve_dag — error cases
# ---------------------------------------------------------------------------

class TestResolveDagErrors(unittest.TestCase):
    def test_simple_cycle_raises(self):
        """A → B → A must raise CycleError."""
        configs = _make_configs(A=["B"], B=["A"])
        with self.assertRaises(dr.CycleError):
            dr.resolve_dag("A", configs, _logger())

    def test_self_cycle_raises(self):
        """A job that lists itself as a producer must raise CycleError."""
        configs = _make_configs(A=["A"])
        with self.assertRaises(dr.CycleError):
            dr.resolve_dag("A", configs, _logger())

    def test_transitive_cycle_raises(self):
        """A → B → C → A must raise CycleError."""
        configs = _make_configs(A=["B"], B=["C"], C=["A"])
        with self.assertRaises(dr.CycleError):
            dr.resolve_dag("A", configs, _logger())

    def test_missing_producer_raises(self):
        """Referencing a producer not in configs must raise MissingJobError."""
        configs = _make_configs(root=["ghost"])
        with self.assertRaises(dr.MissingJobError):
            dr.resolve_dag("root", configs, _logger())

    def test_missing_root_raises(self):
        """Resolving a root that doesn't exist in configs must raise MissingJobError."""
        configs = _make_configs(other=[])
        with self.assertRaises(dr.MissingJobError):
            dr.resolve_dag("nonexistent", configs, _logger())

    def test_cycle_error_message_contains_cycle(self):
        """CycleError message must name the offending nodes."""
        configs = _make_configs(A=["B"], B=["A"])
        try:
            dr.resolve_dag("A", configs, _logger())
            self.fail("Expected CycleError")
        except dr.CycleError as e:
            self.assertIn("A", str(e))
            self.assertIn("B", str(e))

    def test_missing_job_error_message_contains_name(self):
        """MissingJobError message must name the missing job."""
        configs = _make_configs(root=["ghost"])
        try:
            dr.resolve_dag("root", configs, _logger())
            self.fail("Expected MissingJobError")
        except dr.MissingJobError as e:
            self.assertIn("ghost", str(e))


# ---------------------------------------------------------------------------
# resolve_dag — logger interaction
# ---------------------------------------------------------------------------

class TestResolveDagLogger(unittest.TestCase):
    def test_logger_receives_dag_resolved_message(self):
        """resolve_dag must call logger.log() with a summary message."""
        configs = _make_configs(root=["dep"], dep=[])
        log = _logger()
        dr.resolve_dag("root", configs, log)
        combined = "\n".join(log.lines)
        self.assertIn("DAG resolved", combined)

    def test_logger_receives_layer_messages(self):
        """resolve_dag must log each layer."""
        configs = _make_configs(root=["dep"], dep=[])
        log = _logger()
        dr.resolve_dag("root", configs, log)
        combined = "\n".join(log.lines)
        self.assertIn("layer 0", combined)
        self.assertIn("layer 1", combined)


# ---------------------------------------------------------------------------
# Invocation state — helpers
# ---------------------------------------------------------------------------

def _make_invocation_state(invocation_id: str = "test-inv-123", **kwargs) -> dict:
    state = {
        "invocation_id": invocation_id,
        "root": "root-job",
        "layers": [["dep"], ["root-job"]],
        "members": ["dep", "root-job"],
        "completed": {},
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    state.update(kwargs)
    return state


class _InvocationStateFixture:
    """Context manager that redirects INVOCATION_DIR and STATE_DIR to a temp directory."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._inv_dir = self._root / ".dag-invocations"
        self._state_dir = self._root / ".state"
        self._patches = [
            patch.object(dr, "INVOCATION_DIR", self._inv_dir),
            patch.object(dr, "STATE_DIR", self._state_dir),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    @property
    def inv_dir(self) -> Path:
        return self._inv_dir

    @property
    def state_dir(self) -> Path:
        return self._state_dir


# ---------------------------------------------------------------------------
# _invocation_state_path
# ---------------------------------------------------------------------------

class TestInvocationStatePath(unittest.TestCase):
    def test_path_is_inside_invocation_dir(self):
        with _InvocationStateFixture() as fix:
            p = dr._invocation_state_path("abc-123")
            self.assertTrue(str(p).startswith(str(fix.inv_dir)))

    def test_path_ends_with_json(self):
        with _InvocationStateFixture():
            p = dr._invocation_state_path("abc-123")
            self.assertEqual(p.suffix, ".json")

    def test_path_contains_invocation_id(self):
        with _InvocationStateFixture():
            p = dr._invocation_state_path("my-invocation-id")
            self.assertIn("my-invocation-id", p.name)


# ---------------------------------------------------------------------------
# write_invocation_state / read_invocation_state
# ---------------------------------------------------------------------------

class TestWriteReadInvocationState(unittest.TestCase):
    def test_round_trip(self):
        with _InvocationStateFixture():
            state = _make_invocation_state("rt-001")
            dr.write_invocation_state(state)
            loaded = dr.read_invocation_state("rt-001")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["invocation_id"], "rt-001")
            self.assertEqual(loaded["root"], "root-job")

    def test_write_stamps_updated_at(self):
        with _InvocationStateFixture():
            state = _make_invocation_state("ts-001")
            before = datetime.now(timezone.utc)
            dr.write_invocation_state(state)
            after = datetime.now(timezone.utc)
            loaded = dr.read_invocation_state("ts-001")
            updated = datetime.fromisoformat(loaded["updated_at"])
            self.assertGreaterEqual(updated, before.replace(microsecond=0))
            self.assertLessEqual(updated, after + timedelta(seconds=1))

    def test_write_creates_invocation_dir(self):
        with _InvocationStateFixture() as fix:
            self.assertFalse(fix.inv_dir.exists())
            dr.write_invocation_state(_make_invocation_state("dir-create"))
            self.assertTrue(fix.inv_dir.exists())

    def test_no_stale_tmp_file_after_write(self):
        with _InvocationStateFixture() as fix:
            dr.write_invocation_state(_make_invocation_state("atomic-001"))
            stale = list(fix.inv_dir.glob("*.tmp"))
            self.assertEqual(stale, [])

    def test_overwrite_updates_content(self):
        with _InvocationStateFixture():
            s = _make_invocation_state("ow-001", status="running")
            dr.write_invocation_state(s)
            s["status"] = "failed"
            dr.write_invocation_state(s)
            loaded = dr.read_invocation_state("ow-001")
            self.assertEqual(loaded["status"], "failed")


class TestReadInvocationStateMissing(unittest.TestCase):
    def test_missing_file_returns_none(self):
        with _InvocationStateFixture():
            result = dr.read_invocation_state("nonexistent-id")
            self.assertIsNone(result)

    def test_corrupt_json_returns_none(self):
        with _InvocationStateFixture() as fix:
            fix.inv_dir.mkdir(parents=True, exist_ok=True)
            p = dr._invocation_state_path("corrupt-001")
            p.write_text("{ this is not valid json", encoding="utf-8")
            result = dr.read_invocation_state("corrupt-001")
            self.assertIsNone(result)

    def test_empty_file_returns_none(self):
        with _InvocationStateFixture() as fix:
            fix.inv_dir.mkdir(parents=True, exist_ok=True)
            p = dr._invocation_state_path("empty-001")
            p.write_text("", encoding="utf-8")
            result = dr.read_invocation_state("empty-001")
            self.assertIsNone(result)


# ---------------------------------------------------------------------------
# delete_invocation_state
# ---------------------------------------------------------------------------

class TestDeleteInvocationState(unittest.TestCase):
    def test_existing_file_is_removed(self):
        with _InvocationStateFixture():
            dr.write_invocation_state(_make_invocation_state("del-001"))
            self.assertIsNotNone(dr.read_invocation_state("del-001"))
            dr.delete_invocation_state("del-001")
            self.assertIsNone(dr.read_invocation_state("del-001"))

    def test_nonexistent_file_does_not_raise(self):
        with _InvocationStateFixture():
            try:
                dr.delete_invocation_state("no-such-id")
            except Exception as exc:
                self.fail(f"delete_invocation_state raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# invocation_state_age_hours
# ---------------------------------------------------------------------------

class TestInvocationStateAgeHours(unittest.TestCase):
    def test_age_reflects_elapsed_time(self):
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        state = _make_invocation_state("age-001", updated_at=two_hours_ago)
        age = dr.invocation_state_age_hours(state)
        self.assertAlmostEqual(age, 2.0, delta=0.05)

    def test_recent_state_has_small_age(self):
        now_ts = datetime.now(timezone.utc).isoformat()
        state = _make_invocation_state("age-002", updated_at=now_ts)
        age = dr.invocation_state_age_hours(state)
        self.assertLess(age, 0.01)

    def test_missing_updated_at_falls_back_to_started_at(self):
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        state = _make_invocation_state("age-003")
        state.pop("updated_at", None)
        state["started_at"] = one_hour_ago
        age = dr.invocation_state_age_hours(state)
        self.assertAlmostEqual(age, 1.0, delta=0.05)

    def test_no_timestamps_returns_zero(self):
        state = {"invocation_id": "age-004", "root": "x"}
        age = dr.invocation_state_age_hours(state)
        self.assertEqual(age, 0.0)

    def test_invalid_timestamp_returns_zero(self):
        state = _make_invocation_state("age-005", updated_at="not-a-timestamp")
        age = dr.invocation_state_age_hours(state)
        self.assertEqual(age, 0.0)

    def test_naive_datetime_string_treated_as_utc(self):
        one_hour_ago_naive = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        state = _make_invocation_state("age-006", updated_at=one_hour_ago_naive)
        age = dr.invocation_state_age_hours(state)
        self.assertAlmostEqual(age, 1.0, delta=0.05)


# ---------------------------------------------------------------------------
# acquire_lock / release_lock
# ---------------------------------------------------------------------------

class TestAcquireReleaseLock(unittest.TestCase):
    def test_acquire_creates_lock_file(self):
        with _InvocationStateFixture():
            log = _logger()
            lock_file = dr.acquire_lock("my-job", "inv-abc", "root-job", log)
            self.assertTrue(lock_file.exists())

    def test_lock_file_contains_expected_fields(self):
        with _InvocationStateFixture():
            log = _logger()
            lock_file = dr.acquire_lock("my-job", "inv-abc", "root-job", log)
            data = json.loads(lock_file.read_text())
            self.assertEqual(data["invocation_id"], "inv-abc")
            self.assertEqual(data["source_job"], "root-job")
            self.assertIn("acquired_at", data)
            self.assertIn("pid", data)

    def test_acquire_logs_message(self):
        with _InvocationStateFixture():
            log = _logger()
            dr.acquire_lock("my-job", "inv-abc", "root-job", log)
            self.assertTrue(any("lock acquired" in line for line in log.lines))

    def test_lock_file_is_inside_state_dir(self):
        with _InvocationStateFixture() as fix:
            log = _logger()
            lock_file = dr.acquire_lock("my-job", "inv-abc", "root-job", log)
            self.assertTrue(str(lock_file).startswith(str(fix.state_dir)))

    def test_release_removes_lock_file(self):
        with _InvocationStateFixture():
            log = _logger()
            lock_file = dr.acquire_lock("my-job", "inv-release", "root-job", log)
            self.assertTrue(lock_file.exists())
            dr.release_lock(lock_file, log)
            self.assertFalse(lock_file.exists())

    def test_release_logs_message(self):
        with _InvocationStateFixture():
            log = _logger()
            lock_file = dr.acquire_lock("my-job", "inv-logrel", "root-job", log)
            dr.release_lock(lock_file, log)
            self.assertTrue(any("lock released" in line for line in log.lines))

    def test_release_of_nonexistent_file_does_not_raise(self):
        with _InvocationStateFixture() as fix:
            log = _logger()
            fake_path = fix.state_dir / "nonexistent-lock"
            try:
                dr.release_lock(fake_path, log)
            except Exception as exc:
                self.fail(f"release_lock raised unexpectedly: {exc}")

    def test_two_invocations_get_distinct_lock_files(self):
        with _InvocationStateFixture():
            log = _logger()
            lf1 = dr.acquire_lock("shared-job", "inv-1", "root-job", log)
            lf2 = dr.acquire_lock("shared-job", "inv-2", "root-job", log)
            self.assertNotEqual(lf1, lf2)
            self.assertTrue(lf1.exists())
            self.assertTrue(lf2.exists())


if __name__ == "__main__":
    unittest.main()
