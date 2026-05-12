"""Unit tests for pure-function components of lib/scheduler.py.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time as time_module
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make lib/ importable without installing anything
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import scheduler


# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------


class TestCoerce(unittest.TestCase):
    def test_int(self):
        self.assertEqual(scheduler._coerce("42"), 42)
        self.assertEqual(scheduler._coerce("0"), 0)
        self.assertEqual(scheduler._coerce("-1"), -1)

    def test_float(self):
        self.assertAlmostEqual(scheduler._coerce("3.14"), 3.14)
        self.assertAlmostEqual(scheduler._coerce("2.0"), 2.0)

    def test_bool_true(self):
        self.assertIs(scheduler._coerce("true"), True)
        self.assertIs(scheduler._coerce("True"), True)
        self.assertIs(scheduler._coerce("TRUE"), True)

    def test_bool_false(self):
        self.assertIs(scheduler._coerce("false"), False)
        self.assertIs(scheduler._coerce("False"), False)

    def test_string_passthrough(self):
        self.assertEqual(scheduler._coerce("hello"), "hello")
        self.assertEqual(scheduler._coerce("1.2.3"), "1.2.3")
        self.assertEqual(scheduler._coerce(""), "")


# ---------------------------------------------------------------------------
# _strip_quotes
# ---------------------------------------------------------------------------


class TestStripQuotes(unittest.TestCase):
    def test_double_quoted(self):
        self.assertEqual(scheduler._strip_quotes('"hello world"'), "hello world")

    def test_single_quoted(self):
        self.assertEqual(scheduler._strip_quotes("'hello world'"), "hello world")

    def test_unquoted_unchanged(self):
        self.assertEqual(scheduler._strip_quotes("hello"), "hello")

    def test_mismatched_quotes_unchanged(self):
        self.assertEqual(scheduler._strip_quotes('"hello\''), '"hello\'')

    def test_empty_string(self):
        self.assertEqual(scheduler._strip_quotes(""), "")

    def test_single_char(self):
        self.assertEqual(scheduler._strip_quotes("x"), "x")

    def test_quoted_empty(self):
        self.assertEqual(scheduler._strip_quotes('""'), "")
        self.assertEqual(scheduler._strip_quotes("''"), "")


# ---------------------------------------------------------------------------
# _smart_split
# ---------------------------------------------------------------------------


class TestSmartSplit(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(scheduler._smart_split("a,b,c", ","), ["a", "b", "c"])

    def test_quoted_comma_not_split(self):
        result = scheduler._smart_split('a,"b,c",d', ",")
        self.assertEqual(result, ["a", '"b,c"', "d"])

    def test_single_quoted_comma_not_split(self):
        result = scheduler._smart_split("a,'b,c',d", ",")
        self.assertEqual(result, ["a", "'b,c'", "d"])

    def test_no_sep(self):
        self.assertEqual(scheduler._smart_split("abc", ","), ["abc"])

    def test_empty_string(self):
        self.assertEqual(scheduler._smart_split("", ","), [])

    def test_trailing_sep(self):
        # trailing empty part is NOT preserved — the loop's `if current:` guard
        # drops it, which is correct for flow-object parsing ({a: 1, b: 2,})
        result = scheduler._smart_split("a,b,", ",")
        self.assertEqual(result, ["a", "b"])


# ---------------------------------------------------------------------------
# _parse_flow_object
# ---------------------------------------------------------------------------


class TestParseFlowObject(unittest.TestCase):
    def test_simple_pair(self):
        obj = scheduler._parse_flow_object("{type: file_added, path: ~/Downloads}")
        self.assertEqual(obj["type"], "file_added")
        self.assertEqual(obj["path"], "~/Downloads")

    def test_braces_stripped(self):
        obj = scheduler._parse_flow_object("{name: foo}")
        self.assertIn("name", obj)
        self.assertEqual(obj["name"], "foo")

    def test_int_coercion(self):
        obj = scheduler._parse_flow_object("{quiet_seconds: 30}")
        self.assertEqual(obj["quiet_seconds"], 30)

    def test_bool_coercion(self):
        obj = scheduler._parse_flow_object("{enabled: true}")
        self.assertIs(obj["enabled"], True)

    def test_quoted_value_with_comma(self):
        obj = scheduler._parse_flow_object('{msg: "hello, world"}')
        self.assertEqual(obj["msg"], "hello, world")

    def test_no_braces(self):
        obj = scheduler._parse_flow_object("key: value")
        self.assertEqual(obj["key"], "value")


# ---------------------------------------------------------------------------
# _parse_yaml_subset / parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseYamlSubset(unittest.TestCase):
    def test_flat_scalar(self):
        data = scheduler._parse_yaml_subset("name: heartbeat\ncron: 0 * * * *\n")
        self.assertEqual(data["name"], "heartbeat")
        self.assertEqual(data["cron"], "0 * * * *")

    def test_int_coercion(self):
        data = scheduler._parse_yaml_subset("max_turns: 50\n")
        self.assertEqual(data["max_turns"], 50)

    def test_float_coercion(self):
        data = scheduler._parse_yaml_subset("max_budget_usd: 2.5\n")
        self.assertAlmostEqual(data["max_budget_usd"], 2.5)

    def test_bool_coercion(self):
        data = scheduler._parse_yaml_subset("disabled: true\nrun_once: false\n")
        self.assertIs(data["disabled"], True)
        self.assertIs(data["run_once"], False)

    def test_string_list(self):
        block = "tags:\n  - automation\n  - daily\n"
        data = scheduler._parse_yaml_subset(block)
        self.assertEqual(data["tags"], ["automation", "daily"])

    def test_flow_object_list(self):
        block = (
            "external_triggers:\n"
            "  - {type: file_added, path: ~/Downloads}\n"
        )
        data = scheduler._parse_yaml_subset(block)
        self.assertEqual(len(data["external_triggers"]), 1)
        self.assertEqual(data["external_triggers"][0]["type"], "file_added")

    def test_empty_key_starts_list(self):
        # A key with no value initialises an empty list
        data = scheduler._parse_yaml_subset("tags:\n")
        self.assertEqual(data["tags"], [])

    def test_comments_ignored(self):
        data = scheduler._parse_yaml_subset("# this is a comment\nname: foo\n")
        self.assertEqual(data["name"], "foo")
        self.assertNotIn("# this is a comment", data)

    def test_empty_block(self):
        data = scheduler._parse_yaml_subset("")
        self.assertEqual(data, {})

    def test_quoted_value(self):
        data = scheduler._parse_yaml_subset('description: "My job: does things"\n')
        self.assertEqual(data["description"], "My job: does things")


class TestParseFrontmatter(unittest.TestCase):
    _SAMPLE = "---\nname: test\ncron: 0 * * * *\n---\n# Body text\n"

    def test_parses_metadata(self):
        fm, body = scheduler.parse_frontmatter(self._SAMPLE)
        self.assertEqual(fm["name"], "test")
        self.assertEqual(fm["cron"], "0 * * * *")

    def test_body_preserved(self):
        fm, body = scheduler.parse_frontmatter(self._SAMPLE)
        self.assertIn("Body text", body)

    def test_no_frontmatter_returns_empty_dict(self):
        fm, body = scheduler.parse_frontmatter("Just a plain body\n")
        self.assertEqual(fm, {})
        self.assertIn("plain body", body)

    def test_frontmatter_with_list(self):
        text = "---\ntags:\n  - foo\n  - bar\n---\n"
        fm, _ = scheduler.parse_frontmatter(text)
        self.assertEqual(fm["tags"], ["foo", "bar"])


# ---------------------------------------------------------------------------
# cron_matches
# ---------------------------------------------------------------------------


class TestCronMatches(unittest.TestCase):
    # Reference datetime: Thursday 2026-04-16 12:05 UTC
    # isoweekday() = 4 (Thursday); wd = 4 % 7 = 4
    _DT = datetime(2026, 4, 16, 12, 5, tzinfo=timezone.utc)
    # Midnight: 2026-04-16 00:00
    _MIDNIGHT = datetime(2026, 4, 16, 0, 0, tzinfo=timezone.utc)

    def test_all_wildcards(self):
        self.assertTrue(scheduler.cron_matches("* * * * *", self._DT))

    def test_specific_match(self):
        self.assertTrue(scheduler.cron_matches("5 12 16 4 4", self._DT))

    def test_specific_no_match_minute(self):
        self.assertFalse(scheduler.cron_matches("0 12 16 4 4", self._DT))

    def test_specific_no_match_hour(self):
        self.assertFalse(scheduler.cron_matches("5 11 16 4 4", self._DT))

    def test_step_matches(self):
        # */5 on minute 5 → should match (5 % 5 == 0)
        self.assertTrue(scheduler.cron_matches("*/5 * * * *", self._DT))

    def test_step_no_match(self):
        # */7 on minute 5 → 5 is not 0,7,14,...
        self.assertFalse(scheduler.cron_matches("*/7 * * * *", self._DT))

    def test_range_match(self):
        self.assertTrue(scheduler.cron_matches("0-10 * * * *", self._DT))

    def test_range_no_match(self):
        self.assertFalse(scheduler.cron_matches("0-4 * * * *", self._DT))

    def test_list_match(self):
        self.assertTrue(scheduler.cron_matches("1,5,10 * * * *", self._DT))

    def test_list_no_match(self):
        self.assertFalse(scheduler.cron_matches("1,2,3 * * * *", self._DT))

    def test_hourly(self):
        # "0 * * * *" matches only when minute==0
        self.assertTrue(scheduler.cron_matches("0 * * * *", self._MIDNIGHT))
        self.assertFalse(scheduler.cron_matches("0 * * * *", self._DT))

    def test_daily_midnight(self):
        self.assertTrue(scheduler.cron_matches("0 0 * * *", self._MIDNIGHT))
        self.assertFalse(scheduler.cron_matches("0 0 * * *", self._DT))

    def test_dow_sunday_alias(self):
        # Sunday: isoweekday()=7, wd=0. "0" and "7" both = Sunday.
        sunday = datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc)  # April 19 = Sunday
        self.assertTrue(scheduler.cron_matches("* * * * 0", sunday))
        self.assertTrue(scheduler.cron_matches("* * * * 7", sunday))

    def test_invalid_field_count_raises(self):
        with self.assertRaises(ValueError):
            scheduler.cron_matches("* * * *", self._DT)  # 4 fields

    def test_month_match(self):
        # April = month 4
        self.assertTrue(scheduler.cron_matches("* * * 4 *", self._DT))
        self.assertFalse(scheduler.cron_matches("* * * 5 *", self._DT))

    def test_dom_match(self):
        # day 16
        self.assertTrue(scheduler.cron_matches("* * 16 * *", self._DT))
        self.assertFalse(scheduler.cron_matches("* * 15 * *", self._DT))

    def test_step_range(self):
        # 0-59/15 matches 0, 15, 30, 45. Minute 5 → no match.
        self.assertFalse(scheduler.cron_matches("0-59/15 * * * *", self._DT))
        # Minute 15 → match.
        dt15 = datetime(2026, 4, 16, 12, 15, tzinfo=timezone.utc)
        self.assertTrue(scheduler.cron_matches("0-59/15 * * * *", dt15))


# ---------------------------------------------------------------------------
# detect_cycles
# ---------------------------------------------------------------------------


def _make_job(name, producers=None):
    """Minimal job dict for cycle detection tests."""
    return {
        "name": name,
        "producers": [{"name": p} for p in (producers or [])],
    }


class TestDetectCycles(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(scheduler.detect_cycles([]), [])

    def test_single_no_deps(self):
        jobs = [_make_job("a")]
        self.assertEqual(scheduler.detect_cycles(jobs), [])

    def test_linear_chain_no_cycle(self):
        # a → b → c (each job's producers = upstream dependency)
        jobs = [_make_job("a"), _make_job("b", ["a"]), _make_job("c", ["b"])]
        self.assertEqual(scheduler.detect_cycles(jobs), [])

    def test_simple_cycle(self):
        jobs = [_make_job("a", ["b"]), _make_job("b", ["a"])]
        errors = scheduler.detect_cycles(jobs)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_self_cycle(self):
        jobs = [_make_job("a", ["a"])]
        errors = scheduler.detect_cycles(jobs)
        self.assertTrue(len(errors) > 0)

    def test_transitive_cycle(self):
        # a → b → c → a
        jobs = [
            _make_job("a", ["b"]),
            _make_job("b", ["c"]),
            _make_job("c", ["a"]),
        ]
        errors = scheduler.detect_cycles(jobs)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_missing_producer_reference(self):
        # b references "ghost" which doesn't exist
        jobs = [_make_job("a"), _make_job("b", ["ghost"])]
        errors = scheduler.detect_cycles(jobs)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("ghost" in e for e in errors))

    def test_diamond_dag_no_cycle(self):
        # a → b, a → c, d → b, d → c  (diamond, no cycle)
        jobs = [
            _make_job("a"),
            _make_job("b", ["a"]),
            _make_job("c", ["a"]),
            _make_job("d", ["b", "c"]),
        ]
        self.assertEqual(scheduler.detect_cycles(jobs), [])

    def test_producers_as_string_names(self):
        # detect_cycles should handle string producer names too
        jobs = [
            {"name": "a", "producers": []},
            {"name": "b", "producers": ["a"]},  # string, not dict
        ]
        self.assertEqual(scheduler.detect_cycles(jobs), [])


# ---------------------------------------------------------------------------
# parse_datetime_lenient
# ---------------------------------------------------------------------------


class TestParseDatetimeLenient(unittest.TestCase):
    def test_date_only(self):
        dt = scheduler.parse_datetime_lenient("2026-05-01")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 5)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 0)

    def test_datetime_with_t(self):
        dt = scheduler.parse_datetime_lenient("2026-05-01T09:00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 9)

    def test_tz_z_suffix(self):
        dt = scheduler.parse_datetime_lenient("2026-05-01T09:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_tz_offset(self):
        dt = scheduler.parse_datetime_lenient("2026-05-01T09:00:00+05:30")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)

    def test_empty_string(self):
        self.assertIsNone(scheduler.parse_datetime_lenient(""))

    def test_none_input(self):
        self.assertIsNone(scheduler.parse_datetime_lenient(None))

    def test_invalid_string(self):
        self.assertIsNone(scheduler.parse_datetime_lenient("not-a-date"))
        self.assertIsNone(scheduler.parse_datetime_lenient("2026/05/01"))

    def test_whitespace_stripped(self):
        dt = scheduler.parse_datetime_lenient("  2026-05-01  ")
        self.assertIsNotNone(dt)


# ---------------------------------------------------------------------------
# Cron edge-case regression suite
# (documents known tricky behaviors for future contributors)
# ---------------------------------------------------------------------------


class TestCronEdgeCases(unittest.TestCase):
    def test_step_from_zero(self):
        # */2 should match minute 0
        dt = datetime(2026, 4, 16, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(scheduler.cron_matches("*/2 * * * *", dt))

    def test_step_from_zero_odd_minute(self):
        # */2 should NOT match minute 1
        dt = datetime(2026, 4, 16, 0, 1, tzinfo=timezone.utc)
        self.assertFalse(scheduler.cron_matches("*/2 * * * *", dt))

    def test_last_minute_of_hour(self):
        dt = datetime(2026, 4, 16, 12, 59, tzinfo=timezone.utc)
        self.assertTrue(scheduler.cron_matches("59 12 * * *", dt))

    def test_leap_day_cron(self):
        # Feb 29 on a leap year
        dt = datetime(2024, 2, 29, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(scheduler.cron_matches("0 12 29 2 *", dt))


# ---------------------------------------------------------------------------
# _eval_file_changed
# ---------------------------------------------------------------------------


class TestEvalFileChanged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def _trig(self):
        return {"type": "file_changed", "path": self.path}

    def test_bootstrap(self):
        mtime = os.path.getmtime(self.path)
        new_state, fired = scheduler._eval_file_changed(self._trig(), None)
        self.assertAlmostEqual(new_state["last_mtime"], mtime, places=3)
        self.assertFalse(fired)

    def test_same_mtime_no_fire(self):
        mtime = os.path.getmtime(self.path)
        state = {"last_mtime": mtime}
        _, fired = scheduler._eval_file_changed(self._trig(), state)
        self.assertFalse(fired)

    def test_mtime_advanced_fires(self):
        old_mtime = os.path.getmtime(self.path)
        os.utime(self.path, (old_mtime + 10, old_mtime + 10))
        state = {"last_mtime": old_mtime}
        new_state, fired = scheduler._eval_file_changed(self._trig(), state)
        self.assertTrue(fired)
        self.assertGreater(new_state["last_mtime"], old_mtime)

    def test_missing_path_raises(self):
        trig = {"type": "file_changed", "path": "/nonexistent/__no_such_file__.txt"}
        with self.assertRaises(FileNotFoundError):
            scheduler._eval_file_changed(trig, None)


# ---------------------------------------------------------------------------
# _eval_file_added
# ---------------------------------------------------------------------------


class TestEvalFileAdded(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _trig(self, **kwargs):
        t = {"type": "file_added", "path": self.tmpdir, "glob": "*.txt"}
        t.update(kwargs)
        return t

    def _touch(self, name):
        open(os.path.join(self.tmpdir, name), "w").close()

    def test_bootstrap_empty_dir(self):
        new_state, fired = scheduler._eval_file_added(self._trig(), None)
        self.assertFalse(fired)
        self.assertEqual(new_state["seen_files"], [])
        self.assertFalse(new_state["pending_burst"])

    def test_bootstrap_with_existing_files(self):
        self._touch("existing.txt")
        new_state, fired = scheduler._eval_file_added(self._trig(), None)
        self.assertFalse(fired)
        self.assertIn("existing.txt", new_state["seen_files"])

    def test_no_new_files_no_fire(self):
        self._touch("old.txt")
        state = {"seen_files": ["old.txt"], "pending_burst": False, "last_change_at": None}
        new_state, fired = scheduler._eval_file_added(self._trig(), state)
        self.assertFalse(fired)
        self.assertFalse(new_state["pending_burst"])

    def test_new_file_starts_pending_burst(self):
        state = {"seen_files": [], "pending_burst": False, "last_change_at": None}
        self._touch("new.txt")
        new_state, fired = scheduler._eval_file_added(self._trig(), state)
        self.assertFalse(fired)
        self.assertTrue(new_state["pending_burst"])
        self.assertIn("new.txt", new_state["seen_files"])

    def test_quiet_period_elapsed_fires(self):
        self._touch("file.txt")
        state = {"seen_files": ["file.txt"], "pending_burst": True, "last_change_at": 1}
        new_state, fired = scheduler._eval_file_added(self._trig(quiet_seconds=0), state)
        self.assertTrue(fired)
        self.assertFalse(new_state["pending_burst"])
        self.assertIsNone(new_state["last_change_at"])

    def test_pending_burst_quiet_not_elapsed(self):
        self._touch("file.txt")
        state = {
            "seen_files": ["file.txt"],
            "pending_burst": True,
            "last_change_at": time_module.time(),
        }
        new_state, fired = scheduler._eval_file_added(self._trig(quiet_seconds=60), state)
        self.assertFalse(fired)
        self.assertTrue(new_state["pending_burst"])

    def test_removed_file_can_refire(self):
        # Full lifecycle: add file -> delete it -> re-add -> burst fires again.
        self._touch("cycle.txt")
        state = {"seen_files": ["cycle.txt"], "pending_burst": False, "last_change_at": None}
        state1, _ = scheduler._eval_file_added(self._trig(), state)
        self.assertFalse(state1["pending_burst"])
        os.unlink(os.path.join(self.tmpdir, "cycle.txt"))
        state2, _ = scheduler._eval_file_added(self._trig(), state1)
        self.assertNotIn("cycle.txt", state2["seen_files"])
        self._touch("cycle.txt")
        state3, fired3 = scheduler._eval_file_added(self._trig(), state2)
        self.assertFalse(fired3)
        self.assertTrue(state3["pending_burst"])
        self.assertIn("cycle.txt", state3["seen_files"])

    def test_glob_filters_non_matching_files(self):
        self._touch("script.py")
        state = {"seen_files": [], "pending_burst": False, "last_change_at": None}
        new_state, fired = scheduler._eval_file_added(self._trig(), state)
        self.assertFalse(new_state["pending_burst"])

    def test_invalid_path_raises(self):
        trig = {"type": "file_added", "path": "/nonexistent/__no_such_dir__"}
        with self.assertRaises(FileNotFoundError):
            scheduler._eval_file_added(trig, None)


# ---------------------------------------------------------------------------
# _eval_process_starts
# ---------------------------------------------------------------------------


class TestEvalProcessStarts(unittest.TestCase):
    def _trig(self):
        return {"type": "process_starts", "match": "MyTestApp"}

    @patch("scheduler.subprocess.run")
    def test_bootstrap_not_running(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        new_state, fired = scheduler._eval_process_starts(self._trig(), None)
        self.assertFalse(new_state["was_running"])
        self.assertFalse(fired)

    @patch("scheduler.subprocess.run")
    def test_bootstrap_already_running(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        new_state, fired = scheduler._eval_process_starts(self._trig(), None)
        self.assertTrue(new_state["was_running"])
        self.assertFalse(fired)

    @patch("scheduler.subprocess.run")
    def test_transition_starts_fires(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        new_state, fired = scheduler._eval_process_starts(self._trig(), {"was_running": False})
        self.assertTrue(fired)
        self.assertTrue(new_state["was_running"])

    @patch("scheduler.subprocess.run")
    def test_already_running_no_fire(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _, fired = scheduler._eval_process_starts(self._trig(), {"was_running": True})
        self.assertFalse(fired)

    @patch("scheduler.subprocess.run")
    def test_stops_no_fire(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        new_state, fired = scheduler._eval_process_starts(self._trig(), {"was_running": True})
        self.assertFalse(fired)
        self.assertFalse(new_state["was_running"])

    def test_missing_match_raises(self):
        trig = {"type": "process_starts", "match": ""}
        with self.assertRaises(ValueError):
            scheduler._eval_process_starts(trig, None)


# ---------------------------------------------------------------------------
# _eval_command_succeeds
# ---------------------------------------------------------------------------


class TestEvalCommandSucceeds(unittest.TestCase):
    def _trig(self):
        return {"type": "command_succeeds", "run": "true"}

    @patch("scheduler.subprocess.run")
    def test_bootstrap_succeeds(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        new_state, fired = scheduler._eval_command_succeeds(self._trig(), None)
        self.assertTrue(new_state["was_succeeding"])
        self.assertFalse(fired)

    @patch("scheduler.subprocess.run")
    def test_bootstrap_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        new_state, fired = scheduler._eval_command_succeeds(self._trig(), None)
        self.assertFalse(new_state["was_succeeding"])
        self.assertFalse(fired)

    @patch("scheduler.subprocess.run")
    def test_fail_to_succeed_fires(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        new_state, fired = scheduler._eval_command_succeeds(self._trig(), {"was_succeeding": False})
        self.assertTrue(fired)
        self.assertTrue(new_state["was_succeeding"])

    @patch("scheduler.subprocess.run")
    def test_succeed_to_succeed_no_fire(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _, fired = scheduler._eval_command_succeeds(self._trig(), {"was_succeeding": True})
        self.assertFalse(fired)

    @patch("scheduler.subprocess.run")
    def test_succeed_to_fail_no_fire(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        new_state, fired = scheduler._eval_command_succeeds(self._trig(), {"was_succeeding": True})
        self.assertFalse(fired)
        self.assertFalse(new_state["was_succeeding"])

    def test_missing_run_raises(self):
        trig = {"type": "command_succeeds", "run": ""}
        with self.assertRaises(ValueError):
            scheduler._eval_command_succeeds(trig, None)


# ---------------------------------------------------------------------------
# _evaluate_trigger (dispatch)
# ---------------------------------------------------------------------------


class TestEvaluateTrigger(unittest.TestCase):
    @patch("scheduler._eval_file_added", return_value=({"k": "v"}, True))
    def test_dispatches_file_added(self, mock_fn):
        trig = {"type": "file_added", "path": "/tmp"}
        result = scheduler._evaluate_trigger(trig, None)
        mock_fn.assert_called_once_with(trig, None)
        self.assertEqual(result, ({"k": "v"}, True))

    @patch("scheduler._eval_file_changed", return_value=({"k": "v"}, False))
    def test_dispatches_file_changed(self, mock_fn):
        trig = {"type": "file_changed", "path": "/tmp/f"}
        scheduler._evaluate_trigger(trig, None)
        mock_fn.assert_called_once_with(trig, None)

    @patch("scheduler._eval_process_starts", return_value=({"was_running": False}, False))
    def test_dispatches_process_starts(self, mock_fn):
        trig = {"type": "process_starts", "match": "app"}
        scheduler._evaluate_trigger(trig, None)
        mock_fn.assert_called_once_with(trig, None)

    @patch("scheduler._eval_command_succeeds", return_value=({"was_succeeding": False}, False))
    def test_dispatches_command_succeeds(self, mock_fn):
        trig = {"type": "command_succeeds", "run": "true"}
        scheduler._evaluate_trigger(trig, None)
        mock_fn.assert_called_once_with(trig, None)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            scheduler._evaluate_trigger({"type": "nonexistent_type"}, None)


# ---------------------------------------------------------------------------
# substitute_bash_templates
# ---------------------------------------------------------------------------


class TestSubstituteBashTemplates(unittest.TestCase):
    def test_no_markers(self):
        body, log = scheduler.substitute_bash_templates("plain text, no markers")
        self.assertEqual(body, "plain text, no markers")
        self.assertEqual(log, [])

    def test_simple_echo(self):
        body, log = scheduler.substitute_bash_templates("greeting={{cmd: echo hello}}")
        self.assertEqual(body, "greeting=hello")
        self.assertTrue(any("ok" in line for line in log))

    def test_shell_metacharacters_in_prompt_are_safe(self):
        body, log = scheduler.substitute_bash_templates("Use $(foo) or ${bar} safely")
        self.assertEqual(body, "Use $(foo) or ${bar} safely")
        self.assertEqual(log, [])

    def test_command_failure(self):
        body, log = scheduler.substitute_bash_templates("{{cmd: false}}")
        self.assertTrue(body.startswith("[cmd-error: exit 1"))

    def test_output_cap(self):
        body, log = scheduler.substitute_bash_templates(
            "{{cmd: python3 -c \"print('x' * 3000)\"}}"
        )
        self.assertIn("...[truncated]", body)
        self.assertEqual(body.count("x"), 2048)

    def test_multiple_markers(self):
        body, log = scheduler.substitute_bash_templates(
            "A={{cmd: echo a}} B={{cmd: echo b}}"
        )
        self.assertEqual(body, "A=a B=b")
        self.assertEqual(len([line for line in log if "cmd=" in line]), 2)

    def test_whitespace_trimmed(self):
        body, log = scheduler.substitute_bash_templates("{{cmd:  echo hello  }}")
        self.assertEqual(body, "hello")

    def test_nonzero_exit_message(self):
        body, log = scheduler.substitute_bash_templates("{{cmd: exit 42}}")
        self.assertIn("exit 42", body)
        self.assertIn("[cmd-error:", body)


# ---------------------------------------------------------------------------
# _cleanup_stale_tombstones
# ---------------------------------------------------------------------------


class _CleanupFixture:
    """Context manager that redirects JOBS_DIR to a temp directory."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._broken = self._root / ".broken"
        self._dag_inv = self._root / ".state" / ".dag-invocations"
        self._broken.mkdir(parents=True)
        self._dag_inv.mkdir(parents=True)
        self._patches = [
            patch.object(scheduler, "JOBS_DIR", self._root),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *_):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def write_stale(self, subdir: Path, name: str, age_seconds: int = 3 * 3600 + 1) -> Path:
        p = subdir / name
        p.write_text("{}")
        mtime = time_module.time() - age_seconds
        os.utime(p, (mtime, mtime))
        return p

    def write_fresh(self, subdir: Path, name: str) -> Path:
        p = subdir / name
        p.write_text("{}")
        return p

    @property
    def broken(self) -> Path:
        return self._broken

    @property
    def dag_inv(self) -> Path:
        return self._dag_inv


class TestCleanupStaleTombstones(unittest.TestCase):
    def test_removes_stale_tombstone(self):
        with _CleanupFixture() as fix:
            stale = fix.write_stale(fix.broken, "job-a.json")
            scheduler._cleanup_stale_tombstones(retention_hours=1)
            self.assertFalse(stale.exists())

    def test_leaves_fresh_tombstone(self):
        with _CleanupFixture() as fix:
            fresh = fix.write_fresh(fix.broken, "job-b.json")
            scheduler._cleanup_stale_tombstones(retention_hours=1)
            self.assertTrue(fresh.exists())

    def test_removes_stale_dag_invocation_state(self):
        with _CleanupFixture() as fix:
            stale = fix.write_stale(fix.dag_inv, "inv-abc.json")
            scheduler._cleanup_stale_tombstones(retention_hours=1)
            self.assertFalse(stale.exists())

    def test_leaves_fresh_dag_invocation_state(self):
        with _CleanupFixture() as fix:
            fresh = fix.write_fresh(fix.dag_inv, "inv-xyz.json")
            scheduler._cleanup_stale_tombstones(retention_hours=1)
            self.assertTrue(fresh.exists())

    def test_handles_missing_broken_dir(self):
        with _CleanupFixture() as fix:
            fix.broken.rmdir()
            try:
                scheduler._cleanup_stale_tombstones(retention_hours=1)
            except Exception as exc:
                self.fail(f"raised unexpectedly with missing .broken dir: {exc}")

    def test_handles_missing_dag_invocations_dir(self):
        with _CleanupFixture() as fix:
            shutil.rmtree(fix.dag_inv)
            try:
                scheduler._cleanup_stale_tombstones(retention_hours=1)
            except Exception as exc:
                self.fail(f"raised unexpectedly with missing .dag-invocations dir: {exc}")

    def test_cleans_both_dirs_in_same_run(self):
        with _CleanupFixture() as fix:
            stale_t = fix.write_stale(fix.broken, "job-c.json")
            stale_d = fix.write_stale(fix.dag_inv, "inv-def.json")
            scheduler._cleanup_stale_tombstones(retention_hours=1)
            self.assertFalse(stale_t.exists())
            self.assertFalse(stale_d.exists())

    def test_mixed_stale_and_fresh_in_same_dir(self):
        with _CleanupFixture() as fix:
            stale = fix.write_stale(fix.broken, "old-job.json")
            fresh = fix.write_fresh(fix.broken, "new-job.json")
            scheduler._cleanup_stale_tombstones(retention_hours=1)
            self.assertFalse(stale.exists())
            self.assertTrue(fresh.exists())


if __name__ == "__main__":
    unittest.main()
