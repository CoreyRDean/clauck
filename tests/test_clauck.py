"""Unit tests for circuit-breaker tombstone helpers and commands in lib/clauck.

Covers: _format_age, _tombstone_age_hours, _list_tombstones, _find_tombstone,
cmd_broken, and cmd_discard.

Run: python3 -m unittest tests.test_clauck
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# lib/clauck has a shebang and no .py extension; spec_from_file_location
# cannot infer the loader without an extension, so use SourceFileLoader directly.
import importlib.machinery
_CLAUCK_PATH = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck", str(_CLAUCK_PATH))
_spec = importlib.util.spec_from_loader("clauck", _loader)
clauck = importlib.util.module_from_spec(_spec)
_loader.exec_module(clauck)


# ---------------------------------------------------------------------------
# _format_age
# ---------------------------------------------------------------------------

class TestFormatAge(unittest.TestCase):

    def test_minutes_when_less_than_one_hour(self):
        result = clauck._format_age(0.5)
        self.assertEqual(result, "30m ago")

    def test_zero_hours_is_zero_minutes(self):
        result = clauck._format_age(0.0)
        self.assertEqual(result, "0m ago")

    def test_hours_when_one_to_twenty_three(self):
        result = clauck._format_age(5.5)
        self.assertEqual(result, "5.5h ago")

    def test_exactly_one_hour(self):
        result = clauck._format_age(1.0)
        self.assertEqual(result, "1.0h ago")

    def test_days_when_twenty_four_hours_or_more(self):
        result = clauck._format_age(48.0)
        self.assertEqual(result, "2.0d ago")

    def test_days_fractional(self):
        result = clauck._format_age(36.0)
        self.assertEqual(result, "1.5d ago")

    def test_just_under_one_hour_is_minutes(self):
        result = clauck._format_age(0.999)
        self.assertIn("m ago", result)
        self.assertNotIn("h ago", result)

    def test_just_under_twenty_four_hours_is_hours(self):
        result = clauck._format_age(23.9)
        self.assertIn("h ago", result)
        self.assertNotIn("d ago", result)


# ---------------------------------------------------------------------------
# _tombstone_age_hours
# ---------------------------------------------------------------------------

class TestTombstoneAgeHours(unittest.TestCase):

    def _stone_with_offset(self, hours_ago: float) -> dict:
        ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return {"ts": ts.isoformat()}

    def test_recent_tombstone_returns_small_age(self):
        stone = self._stone_with_offset(1.0)
        age = clauck._tombstone_age_hours(stone)
        self.assertAlmostEqual(age, 1.0, delta=0.01)

    def test_old_tombstone_returns_large_age(self):
        stone = self._stone_with_offset(48.0)
        age = clauck._tombstone_age_hours(stone)
        self.assertAlmostEqual(age, 48.0, delta=0.1)

    def test_missing_ts_returns_infinity(self):
        stone = {}
        age = clauck._tombstone_age_hours(stone)
        self.assertEqual(age, float("inf"))

    def test_malformed_ts_returns_infinity(self):
        stone = {"ts": "not-a-timestamp"}
        age = clauck._tombstone_age_hours(stone)
        self.assertEqual(age, float("inf"))

    def test_z_suffix_timestamp_parsed(self):
        ts = datetime.now(timezone.utc) - timedelta(hours=2.0)
        stone = {"ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ")}
        age = clauck._tombstone_age_hours(stone)
        self.assertAlmostEqual(age, 2.0, delta=0.05)


# ---------------------------------------------------------------------------
# _list_tombstones and _find_tombstone
# ---------------------------------------------------------------------------

def _make_stone(tmpdir: Path, job: str, hours_ago: float = 1.0, **extra) -> dict:
    """Write a tombstone JSON file and return the dict."""
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    stone = {"job": job, "ts": ts.isoformat(), "trip_reason": "max_budget", **extra}
    # Filename format mirrors run-job.sh: <job>-<ts>.json
    fname = f"{job}-{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    (tmpdir / fname).write_text(json.dumps(stone))
    return stone


class TestListTombstones(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._broken_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch_broken_dir(self):
        return patch.object(clauck, "BROKEN_DIR", self._broken_dir)

    def test_empty_dir_returns_empty_list(self):
        with self._patch_broken_dir():
            result = clauck._list_tombstones()
        self.assertEqual(result, [])

    def test_missing_dir_returns_empty_list(self):
        with patch.object(clauck, "BROKEN_DIR", Path(self._tmp.name) / "nonexistent"):
            result = clauck._list_tombstones()
        self.assertEqual(result, [])

    def test_single_tombstone_returned(self):
        _make_stone(self._broken_dir, "my-job")
        with self._patch_broken_dir():
            result = clauck._list_tombstones()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["job"], "my-job")

    def test_multiple_tombstones_all_returned(self):
        _make_stone(self._broken_dir, "job-a", hours_ago=1.0)
        _make_stone(self._broken_dir, "job-b", hours_ago=2.0)
        with self._patch_broken_dir():
            result = clauck._list_tombstones()
        names = {s["job"] for s in result}
        self.assertEqual(names, {"job-a", "job-b"})

    def test_malformed_json_file_skipped(self):
        (self._broken_dir / "bad-20260101T000000Z.json").write_text("not json {{{")
        _make_stone(self._broken_dir, "good-job")
        with self._patch_broken_dir():
            result = clauck._list_tombstones()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["job"], "good-job")

    def test_tombstones_sorted_newest_first_same_job(self):
        # Sorting is lexicographic by filename. For the same job prefix,
        # timestamp ordering determines newest-first correctly.
        _make_stone(self._broken_dir, "repeat-job", hours_ago=10.0, spend_usd=0.1)
        _make_stone(self._broken_dir, "repeat-job", hours_ago=1.0, spend_usd=0.9)
        with self._patch_broken_dir():
            result = clauck._list_tombstones()
        # Newest stone (spend=0.9) should appear before older stone (spend=0.1)
        spends = [s["spend_usd"] for s in result]
        self.assertGreater(spends.index(0.1), spends.index(0.9))


class TestFindTombstone(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._broken_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch_broken_dir(self):
        return patch.object(clauck, "BROKEN_DIR", self._broken_dir)

    def test_returns_none_when_no_tombstones(self):
        with self._patch_broken_dir():
            result = clauck._find_tombstone("any-job")
        self.assertIsNone(result)

    def test_returns_none_when_job_not_present(self):
        _make_stone(self._broken_dir, "other-job")
        with self._patch_broken_dir():
            result = clauck._find_tombstone("my-job")
        self.assertIsNone(result)

    def test_finds_exact_job(self):
        _make_stone(self._broken_dir, "target-job")
        with self._patch_broken_dir():
            result = clauck._find_tombstone("target-job")
        self.assertIsNotNone(result)
        self.assertEqual(result["job"], "target-job")

    def test_does_not_match_partial_name(self):
        _make_stone(self._broken_dir, "my-job-extended")
        with self._patch_broken_dir():
            result = clauck._find_tombstone("my-job")
        self.assertIsNone(result)

    def test_returns_most_recent_when_multiple(self):
        _make_stone(self._broken_dir, "repeat-job", hours_ago=5.0, spend_usd=1.0)
        _make_stone(self._broken_dir, "repeat-job", hours_ago=1.0, spend_usd=2.0)
        with self._patch_broken_dir():
            result = clauck._find_tombstone("repeat-job")
        # Should return the more-recent one (hours_ago=1.0, spend_usd=2.0)
        self.assertAlmostEqual(result["spend_usd"], 2.0)


class TestCmdBroken(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._broken_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch_broken_dir(self):
        return patch.object(clauck, "BROKEN_DIR", self._broken_dir)

    def test_prints_empty_state_when_no_tombstones(self):
        stdout = io.StringIO()
        with self._patch_broken_dir(), patch("sys.stdout", stdout):
            clauck.cmd_broken()
        self.assertEqual(stdout.getvalue().strip(), "no broken jobs")

    def test_lists_sorted_tombstones_and_marks_stale_entries(self):
        _make_stone(
            self._broken_dir,
            "repeat-job",
            hours_ago=clauck.BROKEN_RETENTION_HOURS + 2,
            spend_usd=1.25,
            session_id="stale-session-1234567890",
        )
        _make_stone(
            self._broken_dir,
            "repeat-job",
            hours_ago=1.0,
            spend_usd=0.75,
            session_id="fresh-session-1234567890",
        )

        stdout = io.StringIO()
        with self._patch_broken_dir(), patch("sys.stdout", stdout):
            clauck.cmd_broken()

        out = stdout.getvalue()
        self.assertIn("job", out)
        self.assertIn("reason", out)
        self.assertIn("revive: clauck revive <name>", out)
        self.assertIn("discard: clauck discard <name>", out)
        self.assertIn("repeat-job", out)
        self.assertIn("[stale]", out)
        self.assertLess(out.index("fresh-session-1234567890"), out.index("stale-session-1234567890"))


class TestCmdDiscard(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._broken_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch_broken_dir(self):
        return patch.object(clauck, "BROKEN_DIR", self._broken_dir)

    def test_removes_all_matching_tombstones_and_reports_count(self):
        _make_stone(self._broken_dir, "repeat-job", hours_ago=5.0)
        _make_stone(self._broken_dir, "repeat-job", hours_ago=1.0)
        _make_stone(self._broken_dir, "other-job", hours_ago=1.0)

        stdout = io.StringIO()
        with self._patch_broken_dir(), patch("sys.stdout", stdout):
            clauck.cmd_discard("repeat-job")

        self.assertEqual(list(self._broken_dir.glob("repeat-job-*.json")), [])
        self.assertEqual(len(list(self._broken_dir.glob("other-job-*.json"))), 1)
        self.assertIn("discarded 2 tombstone(s) for: repeat-job", stdout.getvalue())

    def test_reports_missing_tombstone_without_error(self):
        stdout = io.StringIO()
        with self._patch_broken_dir(), patch("sys.stdout", stdout):
            clauck.cmd_discard("missing-job")
        self.assertIn("no tombstone found for: missing-job", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
