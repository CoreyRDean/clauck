"""Unit tests for cron-matching and next-fire helpers in lib/clauck.

Covers: _cron_matches, _cron_next, _fmt_next_fire.

These are a standalone copy of the scheduler's cron logic (kept separate so
the clauck CLI has no runtime dependency on lib/scheduler.py). Testing them
independently catches divergence from the scheduler implementation and
regression-proofs the output of `clauck next`.

Run: python3 -m pytest tests/test_clauck_cron.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import unittest
from datetime import datetime, timedelta
from pathlib import Path

_CLAUCK_PATH = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck", str(_CLAUCK_PATH))
_spec = importlib.util.spec_from_loader("clauck", _loader)
clauck = importlib.util.module_from_spec(_spec)
_loader.exec_module(clauck)

_cron_matches = clauck._cron_matches
_cron_next = clauck._cron_next
_fmt_next_fire = clauck._fmt_next_fire


# ---------------------------------------------------------------------------
# _cron_matches
# ---------------------------------------------------------------------------

class TestCronMatches(unittest.TestCase):
    def _dt(self, y=2026, mo=4, d=1, h=0, m=0):
        return datetime(y, mo, d, h, m)

    def test_wildcard_matches_any_minute(self):
        self.assertTrue(_cron_matches("* * * * *", self._dt(m=0)))
        self.assertTrue(_cron_matches("* * * * *", self._dt(m=30)))
        self.assertTrue(_cron_matches("* * * * *", self._dt(m=59)))

    def test_exact_minute_match(self):
        self.assertTrue(_cron_matches("30 * * * *", self._dt(m=30)))
        self.assertFalse(_cron_matches("30 * * * *", self._dt(m=31)))

    def test_exact_hour_match(self):
        self.assertTrue(_cron_matches("0 9 * * *", self._dt(h=9, m=0)))
        self.assertFalse(_cron_matches("0 9 * * *", self._dt(h=10, m=0)))

    def test_step_expression(self):
        # */15: fire at 0, 15, 30, 45
        self.assertTrue(_cron_matches("*/15 * * * *", self._dt(m=0)))
        self.assertTrue(_cron_matches("*/15 * * * *", self._dt(m=15)))
        self.assertTrue(_cron_matches("*/15 * * * *", self._dt(m=30)))
        self.assertTrue(_cron_matches("*/15 * * * *", self._dt(m=45)))
        self.assertFalse(_cron_matches("*/15 * * * *", self._dt(m=1)))
        self.assertFalse(_cron_matches("*/15 * * * *", self._dt(m=16)))

    def test_range_expression(self):
        # 1-5: fire Mon–Fri (dow 1–5 in cron = Mon–Fri)
        # Wednesday = isoweekday 3 → cron dow 3
        wednesday = self._dt(d=1)  # 2026-04-01 is a Wednesday
        self.assertTrue(_cron_matches("0 9 * * 1-5", wednesday.replace(hour=9)))
        # Sunday = isoweekday 7 → cron dow 0
        sunday = self._dt(d=5)  # 2026-04-05 is a Sunday
        self.assertFalse(_cron_matches("0 9 * * 1-5", sunday.replace(hour=9)))

    def test_dom_and_month(self):
        # First day of April
        self.assertTrue(_cron_matches("0 0 1 4 *", self._dt(d=1, mo=4)))
        self.assertFalse(_cron_matches("0 0 1 4 *", self._dt(d=2, mo=4)))
        self.assertFalse(_cron_matches("0 0 1 4 *", self._dt(d=1, mo=5)))

    def test_invalid_field_count_raises(self):
        with self.assertRaises(ValueError):
            _cron_matches("* * * *", self._dt())  # only 4 fields

    def test_comma_list(self):
        # Fire at minute 0, 30
        self.assertTrue(_cron_matches("0,30 * * * *", self._dt(m=0)))
        self.assertTrue(_cron_matches("0,30 * * * *", self._dt(m=30)))
        self.assertFalse(_cron_matches("0,30 * * * *", self._dt(m=15)))


# ---------------------------------------------------------------------------
# _cron_next
# ---------------------------------------------------------------------------

class TestCronNext(unittest.TestCase):
    def test_hourly_next_fire(self):
        # "0 * * * *" — next should be on the next hour boundary
        from_dt = datetime(2026, 4, 18, 15, 5)
        nf = _cron_next("0 * * * *", from_dt)
        self.assertIsNotNone(nf)
        self.assertEqual(nf, datetime(2026, 4, 18, 16, 0))

    def test_next_fire_is_strictly_after_from(self):
        # from_dt already ON the boundary — next must be STRICTLY after
        from_dt = datetime(2026, 4, 18, 16, 0)
        nf = _cron_next("0 * * * *", from_dt)
        self.assertIsNotNone(nf)
        self.assertEqual(nf, datetime(2026, 4, 18, 17, 0))

    def test_daily_job_next_day(self):
        # "0 9 * * *" at 10:00 today → tomorrow 09:00
        from_dt = datetime(2026, 4, 18, 10, 0)
        nf = _cron_next("0 9 * * *", from_dt)
        self.assertIsNotNone(nf)
        self.assertEqual(nf, datetime(2026, 4, 19, 9, 0))

    def test_daily_job_same_day(self):
        # "0 9 * * *" at 08:59 today → 09:00 today
        from_dt = datetime(2026, 4, 18, 8, 59)
        nf = _cron_next("0 9 * * *", from_dt)
        self.assertIsNotNone(nf)
        self.assertEqual(nf, datetime(2026, 4, 18, 9, 0))

    def test_unmatchable_cron_returns_none(self):
        # 30th of February never exists — no match in 8 days
        from_dt = datetime(2026, 4, 18, 0, 0)
        nf = _cron_next("0 0 30 2 *", from_dt)
        self.assertIsNone(nf)

    def test_five_minute_interval(self):
        from_dt = datetime(2026, 4, 18, 12, 3)
        nf = _cron_next("*/5 * * * *", from_dt)
        self.assertIsNotNone(nf)
        self.assertEqual(nf, datetime(2026, 4, 18, 12, 5))

    def test_invalid_cron_returns_none(self):
        # Malformed expression: 4 fields only — _cron_matches raises ValueError,
        # _cron_next catches it and returns None.
        from_dt = datetime(2026, 4, 18, 0, 0)
        nf = _cron_next("* * * *", from_dt)
        self.assertIsNone(nf)


# ---------------------------------------------------------------------------
# _fmt_next_fire
# ---------------------------------------------------------------------------

class TestFmtNextFire(unittest.TestCase):
    def _now(self):
        return datetime(2026, 4, 18, 12, 0)

    def test_minutes_format(self):
        now = self._now()
        nf = now + timedelta(minutes=30)
        result = _fmt_next_fire(nf, now)
        self.assertIn("30m", result)
        self.assertIn("today", result)

    def test_one_minute_minimum(self):
        # Delta of 30 seconds → shows "in 1m" (minimum 1)
        now = self._now()
        nf = now + timedelta(seconds=30)
        result = _fmt_next_fire(nf, now)
        self.assertIn("1m", result)

    def test_hours_format(self):
        now = self._now()
        nf = now + timedelta(hours=3, minutes=15)
        result = _fmt_next_fire(nf, now)
        self.assertIn("3h 15m", result)

    def test_hours_exact_no_minutes(self):
        now = self._now()
        nf = now + timedelta(hours=2)
        result = _fmt_next_fire(nf, now)
        self.assertIn("2h", result)
        self.assertNotIn("0m", result)

    def test_days_format(self):
        now = self._now()
        nf = now + timedelta(days=2, hours=3)
        result = _fmt_next_fire(nf, now)
        self.assertIn("2d 3h", result)

    def test_tomorrow_label(self):
        now = self._now()
        nf = now + timedelta(hours=14)  # tomorrow
        result = _fmt_next_fire(nf, now)
        self.assertIn("tomorrow", result)

    def test_today_label(self):
        now = self._now()
        nf = now + timedelta(minutes=45)
        result = _fmt_next_fire(nf, now)
        self.assertIn("today", result)
        self.assertIn(nf.strftime("%H:%M"), result)

    def test_future_day_uses_weekday(self):
        now = self._now()
        nf = now + timedelta(days=3)
        result = _fmt_next_fire(nf, now)
        # Neither today nor tomorrow — should show abbreviated weekday name
        self.assertNotIn("today", result)
        self.assertNotIn("tomorrow", result)
        self.assertIn(nf.strftime("%a"), result)


if __name__ == "__main__":
    unittest.main()
