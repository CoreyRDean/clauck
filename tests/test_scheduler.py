"""Unit tests for pure-function components of lib/scheduler.py.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
