"""Unit tests for clauck report interactive mining additions.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import importlib.machinery
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Import lib/clauck as a module (no .py extension)
_LIB = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck_cli", str(_LIB))
_mod = _loader.load_module()

_find_pending_drafts = _mod._find_pending_drafts
_build_interactive_mining_prompt = _mod._build_interactive_mining_prompt
_build_report_exec_prompt = _mod._build_report_exec_prompt


# ---------------------------------------------------------------------------
# _find_pending_drafts
# ---------------------------------------------------------------------------


class TestFindPendingDrafts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports = Path(self.tmp.name) / "reports"
        self._orig = _mod.REPORTS_DIR
        _mod.REPORTS_DIR = self.reports

    def tearDown(self):
        _mod.REPORTS_DIR = self._orig
        self.tmp.cleanup()

    def test_no_reports_dir_returns_empty(self):
        self.assertEqual(_find_pending_drafts(), [])

    def test_empty_dir_returns_empty(self):
        self.reports.mkdir()
        self.assertEqual(_find_pending_drafts(), [])

    def test_single_draft_returned(self):
        self.reports.mkdir()
        draft = self.reports / "20260101T120000-draft.json"
        draft.write_text('{"title": "test"}')
        result = _find_pending_drafts()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], draft)

    def test_multiple_drafts_newest_first(self):
        self.reports.mkdir()
        p1 = self.reports / "20260101T100000-draft.json"
        p1.write_text('{"title": "older"}')
        time.sleep(0.02)
        p2 = self.reports / "20260101T120000-draft.json"
        p2.write_text('{"title": "newer"}')
        result = _find_pending_drafts()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], p2)
        self.assertEqual(result[1], p1)

    def test_non_draft_files_ignored(self):
        self.reports.mkdir()
        (self.reports / "20260101T100000-draft.json").write_text("{}")
        (self.reports / "20260101T100000-submitted.json").write_text("{}")
        (self.reports / "somefile.txt").write_text("ignored")
        result = _find_pending_drafts()
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# _build_interactive_mining_prompt
# ---------------------------------------------------------------------------


class TestBuildInteractiveMiningPrompt(unittest.TestCase):
    def test_returns_string(self):
        p = Path("/tmp/test-draft.json")
        result = _build_interactive_mining_prompt(p)
        self.assertIsInstance(result, str)

    def test_draft_path_embedded(self):
        p = Path("/tmp/my-draft.json")
        result = _build_interactive_mining_prompt(p)
        self.assertIn(str(p), result)

    def test_no_prefilled_no_prefill_block(self):
        p = Path("/tmp/test-draft.json")
        result = _build_interactive_mining_prompt(p)
        self.assertNotIn("Pre-loaded draft", result)

    def test_prefilled_included(self):
        p = Path("/tmp/test-draft.json")
        prefilled = {"title": "some bug", "body": "body text", "classification": "bug"}
        result = _build_interactive_mining_prompt(p, prefilled=prefilled)
        self.assertIn("Pre-loaded draft", result)
        self.assertIn("some bug", result)

    def test_prefilled_without_title_skipped(self):
        p = Path("/tmp/test-draft.json")
        result = _build_interactive_mining_prompt(p, prefilled={"classification": "bug"})
        self.assertNotIn("Pre-loaded draft", result)

    def test_none_prefilled_skipped(self):
        p = Path("/tmp/test-draft.json")
        result = _build_interactive_mining_prompt(p, prefilled=None)
        self.assertNotIn("Pre-loaded draft", result)

    def test_contains_save_instruction(self):
        p = Path("/tmp/test-draft.json")
        result = _build_interactive_mining_prompt(p)
        self.assertIn("python3 -c", result)

    def test_contains_gh_submit_instruction(self):
        p = Path("/tmp/test-draft.json")
        result = _build_interactive_mining_prompt(p)
        self.assertIn("gh issue create", result)


# ---------------------------------------------------------------------------
# _build_report_exec_prompt — mine field added
# ---------------------------------------------------------------------------


class TestBuildReportExecPromptMineField(unittest.TestCase):
    def test_mine_field_in_schema(self):
        prompt = _build_report_exec_prompt("some description")
        self.assertIn('"mine"', prompt)

    def test_mine_false_default_in_schema(self):
        prompt = _build_report_exec_prompt("some description")
        self.assertIn('"mine": false', prompt)

    def test_mine_description_present(self):
        prompt = _build_report_exec_prompt("some description")
        self.assertIn("interactive", prompt.lower())

    def test_description_embedded(self):
        prompt = _build_report_exec_prompt("my custom description")
        self.assertIn("my custom description", prompt)

    def test_empty_description_fallback(self):
        prompt = _build_report_exec_prompt("")
        self.assertIn("(no description provided)", prompt)
