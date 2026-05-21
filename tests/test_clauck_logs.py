"""Unit tests for cmd_logs active-run detection and --follow helper.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import lib/clauck (no .py extension) via importlib — spec_from_file_location
# doesn't infer the loader for extension-less files, so supply it explicitly.
import importlib.machinery

_CLAUCK_PATH = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck", str(_CLAUCK_PATH))
spec = importlib.util.spec_from_loader("clauck", _loader)
clauck = importlib.util.module_from_spec(spec)
_loader.exec_module(clauck)
sys.modules["clauck"] = clauck  # needed so patch.multiple("clauck", ...) resolves


class TestActiveLog(unittest.TestCase):
    """Tests for _active_log()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.jobs_dir = Path(self.tmpdir) / ".clauck"
        self.dag_logs_dir = self.jobs_dir / ".dag-logs"
        self.state_dir = self.jobs_dir / ".state"
        self.jobs_dir.mkdir()
        self.dag_logs_dir.mkdir()
        self.state_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_dirs(self):
        return patch.multiple(
            "clauck",
            JOBS_DIR=self.jobs_dir,
            DAG_LOGS_DIR=self.dag_logs_dir,
            STATE_DIR=self.state_dir,
        )

    def _make_log(self, name: str, ts: str, content: str) -> Path:
        log = self.jobs_dir / f"{name}-{ts}.log"
        log.write_text(content)
        return log

    def _make_lock(self, name: str, pid: int) -> Path:
        lock_dir = self.state_dir / f"{name}.lock.d"
        lock_dir.mkdir()
        (lock_dir / "pid").write_text(str(pid))
        return lock_dir

    def test_no_lock_returns_none(self):
        self._make_log("myjob", "20260417T170000Z-123", "=== start ===\n--- exit_code=0 ===")
        with self._patch_dirs():
            self.assertIsNone(clauck._active_log("myjob"))

    def test_stale_lock_nonexistent_pid_returns_none(self):
        self._make_log("myjob", "20260417T170000Z-123", "=== start ===\n")
        # PID 99999999 is very unlikely to exist
        self._make_lock("myjob", 99999999)
        with self._patch_dirs():
            self.assertIsNone(clauck._active_log("myjob"))

    def test_stale_lock_invalid_pid_returns_none(self):
        self._make_log("myjob", "20260417T170000Z-123", "=== start ===\n")
        lock_dir = self.state_dir / "myjob.lock.d"
        lock_dir.mkdir()
        (lock_dir / "pid").write_text("not-a-number")
        with self._patch_dirs():
            self.assertIsNone(clauck._active_log("myjob"))

    def test_live_lock_returns_active_log(self):
        live_log = self._make_log("myjob", "20260417T170000Z-123", "=== start ===\n")
        self._make_lock("myjob", os.getpid())  # current process — definitely alive
        with self._patch_dirs():
            result = clauck._active_log("myjob")
        self.assertEqual(result, live_log)

    def test_live_lock_skips_completed_logs(self):
        # older completed log has exit_code
        self._make_log("myjob", "20260417T160000Z-100", "=== start ===\n--- exit_code=0 ===")
        # newer active log (no exit_code yet)
        active = self._make_log("myjob", "20260417T170000Z-200", "=== start ===\n")
        # ensure mtime ordering is correct
        time.sleep(0.01)
        active.touch()
        self._make_lock("myjob", os.getpid())
        with self._patch_dirs():
            result = clauck._active_log("myjob")
        self.assertEqual(result, active)

    def test_no_logs_with_live_lock_returns_none(self):
        self._make_lock("myjob", os.getpid())
        with self._patch_dirs():
            self.assertIsNone(clauck._active_log("myjob"))

    def test_pid_file_missing_from_lock_dir_returns_none(self):
        self._make_log("myjob", "20260417T170000Z-123", "=== start ===\n")
        lock_dir = self.state_dir / "myjob.lock.d"
        lock_dir.mkdir()
        # no pid file
        with self._patch_dirs():
            self.assertIsNone(clauck._active_log("myjob"))

    def test_active_dag_log_uses_dedicated_dag_log_dir(self):
        dag_log = self.dag_logs_dir / "pipeline-20260417T170000Z-123.log"
        dag_log.write_text("=== dag start ===\npid=%d\n" % os.getpid())
        with self._patch_dirs():
            result = clauck._active_dag_log("pipeline")
        self.assertEqual(result, dag_log)


class TestFollowLog(unittest.TestCase):
    """Tests for _follow_log()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_dir = Path(self.tmpdir) / "state"
        self.state_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_exits_immediately_when_exit_code_already_present(self):
        log = Path(self.tmpdir) / "myjob-20260417T170000Z-123.log"
        log.write_text("=== start ===\n--- exit_code=0 ===\n")
        lock_dir = self.state_dir / "myjob.lock.d"

        import io
        out = io.StringIO()
        with patch("sys.stdout", out):
            clauck._follow_log(log, lock_dir)

        self.assertIn("exit_code=0", out.getvalue())

    def test_exits_when_lock_disappears(self):
        log = Path(self.tmpdir) / "myjob-20260417T170001Z-456.log"
        log.write_text("=== start ===\n")
        lock_dir = self.state_dir / "myjob.lock.d"
        lock_dir.mkdir()

        def remove_lock_after_delay():
            time.sleep(0.15)
            import shutil
            shutil.rmtree(str(lock_dir), ignore_errors=True)

        t = threading.Thread(target=remove_lock_after_delay, daemon=True)
        t.start()

        import io
        out = io.StringIO()
        with patch("sys.stdout", out):
            clauck._follow_log(log, lock_dir)
        t.join(timeout=2)

        self.assertIn("=== start ===", out.getvalue())

    def test_streams_content_written_after_open(self):
        log = Path(self.tmpdir) / "myjob-20260417T170002Z-789.log"
        log.write_text("=== start ===\n")
        lock_dir = self.state_dir / "myjob.lock.d"
        lock_dir.mkdir()

        def append_exit_after_delay():
            time.sleep(0.15)
            with open(log, "a") as f:
                f.write("--- exit_code=0 ===\n")

        t = threading.Thread(target=append_exit_after_delay, daemon=True)
        t.start()

        import io
        out = io.StringIO()
        with patch("sys.stdout", out):
            clauck._follow_log(log, lock_dir)
        t.join(timeout=2)

        self.assertIn("exit_code=0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
