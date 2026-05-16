"""Unit tests for clauck report interactive mining additions.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import importlib.machinery
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Import lib/clauck as a module (no .py extension)
_LIB = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck_cli", str(_LIB))
_mod = _loader.load_module()

_find_pending_drafts = _mod._find_pending_drafts
_build_interactive_mining_prompt = _mod._build_interactive_mining_prompt
_build_report_exec_prompt = _mod._build_report_exec_prompt
_install_issue_watcher = _mod._install_issue_watcher
_write_auto_draft = _mod._write_auto_draft
_notify_pending_auto_reports = _mod._notify_pending_auto_reports


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


# ---------------------------------------------------------------------------
# _install_issue_watcher
# ---------------------------------------------------------------------------


class TestInstallIssueWatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_jobs = _mod.JOBS_DIR
        _mod.JOBS_DIR = Path(self.tmp.name)

    def tearDown(self):
        _mod.JOBS_DIR = self._orig_jobs
        self.tmp.cleanup()

    def test_creates_job_file(self):
        url = "https://github.com/owner/repo/issues/42"
        name = _install_issue_watcher(url)
        job = Path(self.tmp.name) / f"{name}.md"
        self.assertTrue(job.exists(), f"{job} was not created")

    def test_job_name_contains_issue_number(self):
        url = "https://github.com/owner/repo/issues/99"
        name = _install_issue_watcher(url)
        self.assertIn("99", name)

    def test_same_repo_keeps_stable_name(self):
        url = "https://github.com/acme/widget/issues/42"
        self.assertEqual(_install_issue_watcher(url), _install_issue_watcher(url))

    def test_job_file_contains_issue_url(self):
        url = "https://github.com/acme/widget/issues/7"
        name = _install_issue_watcher(url)
        job = Path(self.tmp.name) / f"{name}.md"
        content = job.read_text()
        self.assertIn(url, content)

    def test_repo_hash_prevents_dash_slash_collision(self):
        left = _install_issue_watcher("https://github.com/acme/x-y/issues/42")
        right = _install_issue_watcher("https://github.com/acme-x/y/issues/42")
        self.assertNotEqual(left, right)
        self.assertTrue((Path(self.tmp.name) / f"{left}.md").exists())
        self.assertTrue((Path(self.tmp.name) / f"{right}.md").exists())

    def test_repo_hash_prevents_dot_collision(self):
        left = _install_issue_watcher("https://github.com/acme/re.po/issues/42")
        right = _install_issue_watcher("https://github.com/acme-re/po/issues/42")
        self.assertNotEqual(left, right)
        self.assertTrue((Path(self.tmp.name) / f"{left}.md").exists())
        self.assertTrue((Path(self.tmp.name) / f"{right}.md").exists())

    def test_job_file_has_valid_cron(self):
        url = "https://github.com/acme/widget/issues/7"
        name = _install_issue_watcher(url)
        job = Path(self.tmp.name) / f"{name}.md"
        self.assertIn("cron:", job.read_text())

    def test_notify_channel_baked_in(self):
        url = "https://github.com/acme/widget/issues/5"
        name = _install_issue_watcher(url, notify_channel="C123ABC")
        job = Path(self.tmp.name) / f"{name}.md"
        self.assertIn("C123ABC", job.read_text())

    def test_invalid_url_raises(self):
        with self.assertRaises(ValueError):
            _install_issue_watcher("https://gitlab.com/owner/repo/issues/1")


# ---------------------------------------------------------------------------
# _find_pending_drafts — auto-draft inclusion
# ---------------------------------------------------------------------------


class TestFindPendingDraftsIncludesAuto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports = Path(self.tmp.name) / "reports"
        self._orig = _mod.REPORTS_DIR
        _mod.REPORTS_DIR = self.reports

    def tearDown(self):
        _mod.REPORTS_DIR = self._orig
        self.tmp.cleanup()

    def test_auto_draft_included(self):
        self.reports.mkdir()
        (self.reports / "20260418T120000Z-clauck-doctor-auto.json").write_text('{"title":"t"}')
        result = _find_pending_drafts()
        self.assertEqual(len(result), 1)

    def test_both_types_returned(self):
        self.reports.mkdir()
        (self.reports / "20260418T110000-draft.json").write_text('{"title":"user"}')
        time.sleep(0.02)
        (self.reports / "20260418T120000Z-clauck-doctor-auto.json").write_text('{"title":"auto"}')
        result = _find_pending_drafts()
        self.assertEqual(len(result), 2)

    def test_submitted_json_still_ignored(self):
        self.reports.mkdir()
        (self.reports / "20260418T100000-draft.json").write_text("{}")
        (self.reports / "20260418T100000-submitted.json").write_text("{}")
        result = _find_pending_drafts()
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# _write_auto_draft
# ---------------------------------------------------------------------------


class TestWriteAutoDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports = Path(self.tmp.name) / "reports"
        self.config_file = Path(self.tmp.name) / "config.json"
        self._orig_reports = _mod.REPORTS_DIR
        self._orig_config = _mod.CONFIG_FILE
        _mod.REPORTS_DIR = self.reports
        _mod.CONFIG_FILE = self.config_file

    def tearDown(self):
        _mod.REPORTS_DIR = self._orig_reports
        _mod.CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def _set_mode(self, mode: str) -> None:
        self.config_file.write_text(json.dumps({"auto_report": {"mode": mode}}))

    def test_off_mode_returns_none(self):
        self._set_mode("off")
        result = _write_auto_draft("test-agent", "title", "body")
        self.assertIsNone(result)

    def test_off_mode_writes_nothing(self):
        self._set_mode("off")
        _write_auto_draft("test-agent", "title", "body")
        self.assertFalse(self.reports.exists())

    def test_draft_mode_creates_file(self):
        self._set_mode("draft")
        path = _write_auto_draft("test-agent", "Test Title", "Test body")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_draft_mode_file_is_valid_json(self):
        self._set_mode("draft")
        path = _write_auto_draft("test-agent", "Test Title", "Test body")
        data = json.loads(path.read_text())
        self.assertEqual(data["title"], "Test Title")
        self.assertEqual(data["body"], "Test body")
        self.assertTrue(data["auto"])
        self.assertEqual(data["source"], "test-agent")
        self.assertEqual(data["classification"], "bug")

    def test_auto_mode_creates_file(self):
        self._set_mode("auto")
        path = _write_auto_draft("doctor", "A bug", "body")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_legacy_scalar_mode_string_still_writes(self):
        self.config_file.write_text(json.dumps({"auto_report": "draft"}))
        path = _write_auto_draft("doctor", "A bug", "body")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_custom_labels_stored(self):
        self._set_mode("draft")
        path = _write_auto_draft("agent", "t", "b", labels=["enhancement"])
        data = json.loads(path.read_text())
        self.assertEqual(data["labels"], ["enhancement"])

    def test_filename_contains_auto(self):
        self._set_mode("draft")
        path = _write_auto_draft("clauck-doctor", "t", "b")
        self.assertIn("auto", path.name)
        self.assertIn("clauck-doctor", path.name)

    def test_dedupe_key_suppresses_duplicate(self):
        self._set_mode("draft")
        p1 = _write_auto_draft("agent", "t", "b", dedupe_key="abc123")
        self.assertIsNotNone(p1)
        p2 = _write_auto_draft("agent", "t2", "b2", dedupe_key="abc123")
        self.assertIsNone(p2)
        # Only one file should exist
        auto_files = list(self.reports.glob("*-auto.json"))
        self.assertEqual(len(auto_files), 1)

    def test_different_dedupe_keys_both_written(self):
        self._set_mode("draft")
        p1 = _write_auto_draft("agent", "t1", "b1", dedupe_key="key-a")
        p2 = _write_auto_draft("agent", "t2", "b2", dedupe_key="key-b")
        self.assertIsNotNone(p1)
        self.assertIsNotNone(p2)
        auto_files = list(self.reports.glob("*-auto.json"))
        self.assertEqual(len(auto_files), 2)

    def test_no_dedupe_key_always_writes(self):
        self._set_mode("draft")
        p1 = _write_auto_draft("agent", "t", "b")
        time.sleep(0.01)
        p2 = _write_auto_draft("agent", "t", "b")
        # Both should exist (no deduplication without a key)
        self.assertIsNotNone(p1)
        self.assertIsNotNone(p2)

    def test_special_chars_in_source_sanitized(self):
        self._set_mode("draft")
        path = _write_auto_draft("my/agent name", "t", "b")
        self.assertIsNotNone(path)
        self.assertNotIn("/", path.name.split("-auto.json")[0].split("Z-")[1])


# ---------------------------------------------------------------------------
# _notify_pending_auto_reports
# ---------------------------------------------------------------------------


class TestNotifyPendingAutoReports(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports = Path(self.tmp.name) / "reports"
        self.config_file = Path(self.tmp.name) / "config.json"
        self._orig_reports = _mod.REPORTS_DIR
        self._orig_config = _mod.CONFIG_FILE
        _mod.REPORTS_DIR = self.reports
        _mod.CONFIG_FILE = self.config_file

    def tearDown(self):
        _mod.REPORTS_DIR = self._orig_reports
        _mod.CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def _set_mode(self, mode: str) -> None:
        self.config_file.write_text(json.dumps({"auto_report": {"mode": mode}}))

    def _capture_notify(self):
        buf = io.StringIO()
        with patch("builtins.print", side_effect=lambda *a, **k: buf.write(" ".join(str(x) for x in a) + "\n")):
            _notify_pending_auto_reports()
        return buf.getvalue()

    def test_off_mode_prints_nothing(self):
        self._set_mode("off")
        self.reports.mkdir()
        (self.reports / "ts-agent-auto.json").write_text("{}")
        out = self._capture_notify()
        self.assertEqual(out, "")

    def test_no_reports_dir_prints_nothing(self):
        self._set_mode("draft")
        out = self._capture_notify()
        self.assertEqual(out, "")

    def test_no_auto_files_prints_nothing(self):
        self._set_mode("draft")
        self.reports.mkdir()
        (self.reports / "20260101-draft.json").write_text("{}")
        out = self._capture_notify()
        self.assertEqual(out, "")

    def test_auto_files_present_prints_notice(self):
        self._set_mode("draft")
        self.reports.mkdir()
        (self.reports / "20260418T120000Z-doctor-auto.json").write_text("{}")
        out = self._capture_notify()
        self.assertIn("auto-report", out)
        self.assertIn("clauck report --inbox", out)

    def test_notice_includes_count(self):
        self._set_mode("draft")
        self.reports.mkdir()
        for i in range(3):
            (self.reports / f"20260418T12000{i}Z-doctor-auto.json").write_text("{}")
        out = self._capture_notify()
        self.assertIn("3", out)

    def test_legacy_scalar_mode_string_still_prints_notice(self):
        self.config_file.write_text(json.dumps({"auto_report": "draft"}))
        self.reports.mkdir()
        (self.reports / "20260418T120000Z-doctor-auto.json").write_text("{}")
        out = self._capture_notify()
        self.assertIn("auto-report", out)


class TestLegacyAutoReportConfigCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.jobs_dir = root / "jobs"
        self.jobs_dir.mkdir()
        self.state_dir = self.jobs_dir / ".state"
        self.state_dir.mkdir()
        self.reports_dir = root / "reports"
        self.reports_dir.mkdir()
        self.config_file = root / "config.json"
        self.version_file = root / ".version"
        self.version_file.write_text("v1.5.7")
        self.manifest_file = root / ".manifest.json"
        self.manifest_file.write_text(json.dumps({"jobs": []}))
        self._orig_jobs = _mod.JOBS_DIR
        self._orig_state = _mod.STATE_DIR
        self._orig_reports = _mod.REPORTS_DIR
        self._orig_config = _mod.CONFIG_FILE
        self._orig_version = _mod.VERSION_FILE
        self._orig_manifest = _mod.MANIFEST
        _mod.JOBS_DIR = self.jobs_dir
        _mod.STATE_DIR = self.state_dir
        _mod.REPORTS_DIR = self.reports_dir
        _mod.CONFIG_FILE = self.config_file
        _mod.VERSION_FILE = self.version_file
        _mod.MANIFEST = self.manifest_file

    def tearDown(self):
        _mod.JOBS_DIR = self._orig_jobs
        _mod.STATE_DIR = self._orig_state
        _mod.REPORTS_DIR = self._orig_reports
        _mod.CONFIG_FILE = self._orig_config
        _mod.VERSION_FILE = self._orig_version
        _mod.MANIFEST = self._orig_manifest
        self.tmp.cleanup()

    def test_main_list_does_not_brick_on_legacy_scalar_mode(self):
        self.config_file.write_text(json.dumps({"auto_report": "draft"}))
        with patch.object(_mod, "jit_update_check"), \
                patch.object(_mod, "cmd_list") as mock_list, \
                patch.object(sys, "argv", ["clauck", "list"]):
            _mod.main()
        mock_list.assert_called_once_with(tag_filter="")

    def test_status_handles_legacy_scalar_mode_and_pending_drafts(self):
        self.config_file.write_text(json.dumps({"auto_report": "draft"}))
        (self.reports_dir / "20260418T120000Z-doctor-auto.json").write_text("{}")
        buf = io.StringIO()
        with patch("builtins.print", side_effect=lambda *a, **k: buf.write(" ".join(str(x) for x in a) + "\n")), \
                patch.object(_mod.subprocess, "run", return_value=subprocess.CompletedProcess(["launchctl", "list"], 0, "", "")):
            _mod.cmd_status()
        out = buf.getvalue()
        self.assertIn("auto-report: draft", out)
        self.assertIn("auto-report drafts: 1 pending", out)


class TestDoctorAutoReportHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.jobs_dir = root / "jobs"
        self.jobs_dir.mkdir()
        self.state_dir = self.jobs_dir / ".state"
        self.state_dir.mkdir()
        self.reports_dir = root / "reports"
        self.config_file = root / "config.json"
        self.config_file.write_text(json.dumps({"auto_report": {"mode": "draft"}}))
        self._orig_jobs = _mod.JOBS_DIR
        self._orig_state = _mod.STATE_DIR
        self._orig_reports = _mod.REPORTS_DIR
        self._orig_config = _mod.CONFIG_FILE
        _mod.JOBS_DIR = self.jobs_dir
        _mod.STATE_DIR = self.state_dir
        _mod.REPORTS_DIR = self.reports_dir
        _mod.CONFIG_FILE = self.config_file

    def tearDown(self):
        _mod.JOBS_DIR = self._orig_jobs
        _mod.STATE_DIR = self._orig_state
        _mod.REPORTS_DIR = self._orig_reports
        _mod.CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def test_dry_fix_prompt_writes_auto_draft_before_exec_handoff(self):
        class ExecHandoff(Exception):
            pass

        class DummyThread:
            def __init__(self, target=None, daemon=None):
                self.target = target

            def start(self):
                return None

            def join(self, timeout=None):
                return None

        stage1 = subprocess.CompletedProcess(
            ["claude", "-p"],
            0,
            json.dumps({
                "result": json.dumps({
                    "interpretation": "Inspect install.sh drift",
                    "task_complexity_scale": 0.2,
                }),
                "is_error": False,
            }),
            "",
        )
        stage2 = subprocess.CompletedProcess(
            ["claude", "-p"],
            0,
            json.dumps({
                "result": json.dumps({
                    "report": "install.sh needs a clauck internal fix",
                    "fix_instruction": "repair install.sh handling",
                }),
                "session_id": "session-123",
                "is_error": False,
            }),
            "",
        )

        events = []

        def fake_write_auto_draft(*args, **kwargs):
            events.append("draft")
            return self.reports_dir / "draft.json"

        def fake_execvp(path, argv):
            events.append("execvp")
            raise ExecHandoff()

        with patch.object(_mod, "_find_claude", return_value="/usr/bin/claude"), \
                patch.object(_mod.sizing, "load_doctor_config", return_value={"scale_skew": 0.0, "max_budget_usd": 10.0}), \
                patch.object(_mod.sizing, "estimate_tokens", return_value=0), \
                patch.object(_mod.sizing, "compute_sizing", return_value={
                    "model": "haiku",
                    "effort": "low",
                    "max_turns": 2,
                    "max_budget_usd": 1.0,
                    "explanation": "scaled",
                    "base_cost": 0.0,
                    "context_cost": 0.0,
                    "headroom": 1.3,
                }), \
                patch.object(_mod.subprocess, "run", side_effect=[stage1, stage2]), \
                patch.object(_mod, "_write_auto_draft", side_effect=fake_write_auto_draft), \
                patch("threading.Thread", DummyThread), \
                patch.object(sys.stdin, "isatty", return_value=True), \
                patch.object(sys.stdout, "isatty", return_value=True), \
                patch("builtins.input", return_value=""), \
                patch.object(_mod.os, "execvp", side_effect=fake_execvp), \
                patch.object(sys, "argv", ["clauck", "doctor", "--dry", "check install.sh"]):
            with self.assertRaises(ExecHandoff):
                _mod.cmd_doctor(dry=True, fix=False, safe=True, unsafe=False, interactive=False, context="check install.sh")

        self.assertEqual(events, ["draft", "execvp"])
