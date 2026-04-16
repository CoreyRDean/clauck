"""Unit tests for pure-function components of lib/dag-runner.py.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
