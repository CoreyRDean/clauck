"""Unit tests for _parse_log_summary, _age_str, and cmd_cost.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import importlib.machinery
import io
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

_LIB = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck_hc", str(_LIB))
_mod = _loader.load_module()

_parse_log_summary = _mod._parse_log_summary
_age_str = _mod._age_str
cmd_cost = _mod.cmd_cost


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(directory: Path, name: str, ts: str, pid: str, content: str) -> Path:
    """Write a fake log file and return its Path."""
    log = directory / f"{name}-{ts}-{pid}.log"
    log.write_text(content)
    return log


# ---------------------------------------------------------------------------
# _parse_log_summary
# ---------------------------------------------------------------------------

class TestParseLogSummary(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _log(self, name: str, ts: str, pid: str, content: str) -> Path:
        return _make_log(self.d, name, ts, pid, content)

    def test_all_fields_populated(self):
        log = self._log(
            "my-job", "20260418T170000Z", "12345",
            '{"total_cost_usd":0.1234}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        r = _parse_log_summary(log)
        self.assertIsNotNone(r)
        self.assertEqual(r["name"], "my-job")
        self.assertEqual(r["ts_str"], "20260418T170000Z")
        self.assertEqual(r["pid"], "12345")
        self.assertEqual(r["exit_code"], 0)
        self.assertAlmostEqual(r["cost_usd"], 0.1234)
        self.assertEqual(r["terminal_reason"], "completed")
        self.assertFalse(r["running"])

    def test_invocation_id_format(self):
        log = self._log("job", "20260418T120000Z", "99", "")
        r = _parse_log_summary(log)
        self.assertEqual(r["invocation_id"], "20260418T120000Z-99")

    def test_no_exit_code_means_running(self):
        log = self._log("job", "20260418T120000Z", "1", "=== clauck start ===\n")
        r = _parse_log_summary(log)
        self.assertIsNone(r["exit_code"])
        self.assertTrue(r["running"])

    def test_exit_code_nonzero(self):
        log = self._log("job", "20260418T120000Z", "2", "--- exit_code=1 ---\n")
        r = _parse_log_summary(log)
        self.assertEqual(r["exit_code"], 1)
        self.assertFalse(r["running"])

    def test_cost_usd_extracted(self):
        log = self._log("job", "20260418T120000Z", "3", '{"total_cost_usd":0.0512}\n')
        r = _parse_log_summary(log)
        self.assertAlmostEqual(r["cost_usd"], 0.0512)

    def test_no_cost_line_returns_none(self):
        log = self._log("job", "20260418T120000Z", "4", "--- exit_code=0 ---\n")
        r = _parse_log_summary(log)
        self.assertIsNone(r["cost_usd"])

    def test_terminal_reason_extracted(self):
        log = self._log(
            "job", "20260418T120000Z", "5",
            '{"terminal_reason":"max_turns"}\n--- exit_code=1 ---\n',
        )
        r = _parse_log_summary(log)
        self.assertEqual(r["terminal_reason"], "max_turns")

    def test_malformed_filename_returns_none(self):
        bad = self.d / "no-timestamp-here.log"
        bad.write_text("content")
        self.assertIsNone(_parse_log_summary(bad))

    def test_empty_file_returns_dict_with_running_true(self):
        log = self._log("job", "20260418T120000Z", "6", "")
        r = _parse_log_summary(log)
        self.assertIsNotNone(r)
        self.assertTrue(r["running"])
        self.assertIsNone(r["exit_code"])
        self.assertIsNone(r["cost_usd"])

    def test_path_field_is_original_path(self):
        log = self._log("job", "20260418T120000Z", "7", "")
        r = _parse_log_summary(log)
        self.assertEqual(r["path"], log)

    def test_hyphenated_job_name_parsed_correctly(self):
        log = self._log("pe-pipeline", "20260418T120000Z", "8", "--- exit_code=0 ---\n")
        r = _parse_log_summary(log)
        self.assertEqual(r["name"], "pe-pipeline")


# ---------------------------------------------------------------------------
# _age_str
# ---------------------------------------------------------------------------

class TestAgeStr(unittest.TestCase):

    def _now(self) -> datetime:
        return datetime(2026, 4, 18, 17, 0, 0, tzinfo=timezone.utc)

    def test_seconds_ago(self):
        ts = self._now() - timedelta(seconds=45)
        self.assertEqual(_age_str(ts, self._now()), "45s ago")

    def test_minutes_ago(self):
        ts = self._now() - timedelta(minutes=7)
        self.assertEqual(_age_str(ts, self._now()), "7m ago")

    def test_hours_ago(self):
        ts = self._now() - timedelta(hours=3)
        self.assertEqual(_age_str(ts, self._now()), "3h ago")

    def test_days_ago(self):
        ts = self._now() - timedelta(days=5)
        self.assertEqual(_age_str(ts, self._now()), "5d ago")

    def test_boundary_exactly_60_seconds(self):
        ts = self._now() - timedelta(seconds=60)
        self.assertEqual(_age_str(ts, self._now()), "1m ago")

    def test_boundary_exactly_1_hour(self):
        ts = self._now() - timedelta(hours=1)
        self.assertEqual(_age_str(ts, self._now()), "1h ago")


# ---------------------------------------------------------------------------
# cmd_cost
# ---------------------------------------------------------------------------

class TestCmdCost(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jobs_dir = Path(self.tmp.name)
        self._orig = _mod.JOBS_DIR
        _mod.JOBS_DIR = self.jobs_dir

    def tearDown(self):
        _mod.JOBS_DIR = self._orig
        self.tmp.cleanup()

    def _log(self, name: str, ts: str, pid: str, content: str) -> Path:
        return _make_log(self.jobs_dir, name, ts, pid, content)

    def _run(self, **kwargs) -> str:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            cmd_cost(**kwargs)
        return buf.getvalue()

    def test_no_logs_prints_no_data(self):
        out = self._run()
        self.assertIn("no log data found", out)

    def test_single_run_shows_spend(self):
        self._log(
            "heartbeat", "20260418T170000Z", "100",
            '{"total_cost_usd":0.0050}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        out = self._run()
        self.assertIn("heartbeat", out)
        self.assertIn("0.0050", out)

    def test_multiple_jobs_sorted_by_spend_descending(self):
        self._log(
            "cheap-job", "20260418T160000Z", "101",
            '{"total_cost_usd":0.0010}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        self._log(
            "expensive-job", "20260418T161000Z", "102",
            '{"total_cost_usd":0.9000}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        out = self._run()
        expensive_pos = out.find("expensive-job")
        cheap_pos = out.find("cheap-job")
        self.assertGreater(cheap_pos, expensive_pos, "expensive job should appear before cheap job")

    def test_total_row_present_for_multiple_jobs(self):
        for i, cost in enumerate(["0.0100", "0.0200"]):
            self._log(
                f"job-{i}", f"2026041{i}T170000Z", str(i + 1),
                f'{{"total_cost_usd":{cost}}}\n{{"terminal_reason":"completed"}}\n--- exit_code=0 ---\n',
            )
        out = self._run()
        self.assertIn("total", out)

    def test_name_filter_limits_output(self):
        self._log(
            "alpha", "20260418T170000Z", "200",
            '{"total_cost_usd":0.1000}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        self._log(
            "beta", "20260418T170100Z", "201",
            '{"total_cost_usd":0.2000}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        out = self._run(name="alpha")
        self.assertIn("alpha", out)
        self.assertNotIn("beta", out)

    def test_failure_run_counted_in_fails_column(self):
        self._log(
            "flaky-job", "20260418T170000Z", "300",
            '{"total_cost_usd":0.0500}\n{"terminal_reason":"max_turns"}\n--- exit_code=1 ---\n',
        )
        out = self._run()
        # The failure count should appear in the output (failures != "–")
        self.assertIn("1", out)

    def test_dag_log_excluded(self):
        # A "-dag-" pattern in the filename marks orchestration logs
        dag_log = self.jobs_dir / "my-pipeline-dag-20260418T170000Z-400.log"
        dag_log.write_text(
            '{"total_cost_usd":9.9999}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n'
        )
        out = self._run()
        self.assertIn("no log data found", out)

    def test_days_filter_excludes_old_log(self):
        # Log timestamped 60 days ago — outside default 30-day window
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y%m%dT%H%M%SZ")
        log = self.jobs_dir / f"old-job-{old_ts}-500.log"
        log.write_text(
            '{"total_cost_usd":0.5000}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        # Force mtime to match the timestamp (cmd_cost uses mtime for --days filter)
        import time as _time
        sixty_days_ago = _time.time() - 60 * 86400
        import os
        os.utime(log, (sixty_days_ago, sixty_days_ago))
        out = self._run(days=30)
        self.assertIn("no log data found", out)

    def test_all_time_includes_old_log(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y%m%dT%H%M%SZ")
        log = self.jobs_dir / f"old-job-{old_ts}-501.log"
        log.write_text(
            '{"total_cost_usd":0.5000}\n{"terminal_reason":"completed"}\n--- exit_code=0 ---\n',
        )
        import time as _time, os
        sixty_days_ago = _time.time() - 60 * 86400
        os.utime(log, (sixty_days_ago, sixty_days_ago))
        out = self._run(all_time=True)
        self.assertIn("old-job", out)


if __name__ == "__main__":
    unittest.main()
