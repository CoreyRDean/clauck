"""Tests for solo revive config resolution and explicit resume precedence.

Run: python3 -m unittest tests.test_clauck_revive
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


_CLAUCK_PATH = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck_revive", str(_CLAUCK_PATH))
_spec = importlib.util.spec_from_loader("clauck_revive", _loader)
clauck = importlib.util.module_from_spec(_spec)
_loader.exec_module(clauck)

_RUN_JOB = Path(__file__).parent.parent / "lib" / "run-job.sh"


def _make_tombstone(directory: Path, job: str, **extra) -> None:
    ts = datetime.now(timezone.utc) - timedelta(hours=1)
    stone = {
        "job": job,
        "ts": ts.isoformat(),
        "trip_reason": "max_budget",
        "session_id": "revive-session-123",
        "orig_max_budget_usd": 1.25,
        "orig_max_turns": 22,
        "spend_usd": 0.75,
        **extra,
    }
    name = f"{job}-{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
    (directory / name).write_text(json.dumps(stone), encoding="utf-8")


class TestCmdReviveSoloEnv(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir()
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()
        self.broken_dir = self.root / "broken"
        self.broken_dir.mkdir()
        self.run_job = self.jobs_dir / "run-job.sh"
        self.run_job.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
        self.run_job.chmod(self.run_job.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self.tmp.cleanup()

    def test_revive_uses_resolved_job_config_for_solo_path(self):
        _make_tombstone(self.broken_dir, "logical-job")
        job_config = {
            "name": "logical-job",
            "path": str(self.root / "custom" / "actual-job.md"),
            "cwd": str(self.root / "workspace"),
            "max_turns": 77,
            "max_budget_usd": 3.5,
            "effort": "medium",
            "cron": "0 9 * * 1-5",
            "model": "sonnet",
            "setting_sources": "",
            "strict_mcp_config": True,
            "debounce_seconds": 120,
            "session_persist": True,
            "interactive": True,
            "trace_tool_calls": True,
            "consumers": ["downstream-a", "downstream-b"],
        }
        stdout = io.StringIO()
        with patch.object(clauck, "JOBS_DIR", self.jobs_dir), \
             patch.object(clauck, "STATE_DIR", self.state_dir), \
             patch.object(clauck, "BROKEN_DIR", self.broken_dir), \
             patch.object(clauck, "_discover_job_config", return_value=job_config), \
             patch("sys.stdout", stdout), \
             patch.object(clauck.subprocess, "Popen") as mock_popen:
            clauck.cmd_revive("logical-job")

        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["zsh", str(self.run_job), "logical-job"])
        env = kwargs["env"]
        self.assertEqual(env["CLAUDE_JOB_NAME"], "logical-job")
        self.assertEqual(env["CLAUDE_JOB_PATH"], job_config["path"])
        self.assertEqual(env["CLAUDE_JOB_CWD"], job_config["cwd"])
        self.assertEqual(env["CLAUDE_JOB_MAX_TURNS"], "77")
        self.assertEqual(env["CLAUDE_JOB_MAX_BUDGET_USD"], "3.5")
        self.assertEqual(env["CLAUDE_JOB_EFFORT"], "medium")
        self.assertEqual(env["CLAUDE_JOB_MODEL"], "sonnet")
        self.assertEqual(env["CLAUDE_JOB_CRON"], "0 9 * * 1-5")
        self.assertEqual(env["CLAUDE_JOB_SETTING_SOURCES"], "")
        self.assertEqual(env["CLAUDE_JOB_SETTING_SOURCES_SET"], "1")
        self.assertEqual(env["CLAUDE_JOB_STRICT_MCP_CONFIG"], "1")
        self.assertEqual(env["CLAUDE_JOB_DEBOUNCE_SECONDS"], "120")
        self.assertEqual(env["CLAUDE_JOB_SESSION_PERSIST"], "1")
        self.assertEqual(env["CLAUDE_JOB_INTERACTIVE"], "1")
        self.assertEqual(env["CLAUDE_JOB_TRACE_TOOL_CALLS"], "1")
        self.assertEqual(env["CLAUDE_JOB_TRIGGER"], "revive")
        self.assertIn("CLAUDE_JOB_FIRED_AT", env)

        revive_payload = json.loads((self.state_dir / "logical-job.revive.json").read_text())
        self.assertEqual(revive_payload["session_id"], "revive-session-123")
        self.assertEqual(revive_payload["max_budget_usd"], 2.5)
        self.assertEqual(revive_payload["max_turns"], 44)
        self.assertEqual(revive_payload["consumers"], ["downstream-a", "downstream-b"])
        self.assertEqual(list(self.broken_dir.glob("logical-job-*.json")), [])
        self.assertIn("tail logs with: clauck logs logical-job --show", stdout.getvalue())


class TestRunJobResumePrecedence(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.jobs_dir = self.home / ".clauck"
        self.state_dir = self.jobs_dir / ".state"
        self.jobs_dir.mkdir()
        self.state_dir.mkdir()
        (self.home / ".local" / "bin").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_revive_session_skips_persisted_resume(self):
        fake_claude = self.home / ".local" / "bin" / "claude"
        fake_claude.write_text(
            "#!/bin/zsh\n"
            "printf '%s\\n' \"$@\" > \"$HOME/claude-args.txt\"\n"
            "printf '{\"session_id\":\"new-session\",\"terminal_reason\":\"completed\",\"total_cost_usd\":0.01}\\n'\n",
            encoding="utf-8",
        )
        fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IXUSR)

        (self.jobs_dir / "prompt.md").write_text("global prompt\n", encoding="utf-8")
        (self.jobs_dir / "my-job.md").write_text(
            "---\n"
            "session_persist: true\n"
            "---\n"
            "Do the thing.\n",
            encoding="utf-8",
        )
        (self.state_dir / "my-job.revive.json").write_text(
            json.dumps({
                "session_id": "revive-session",
                "max_budget_usd": 9.0,
                "max_turns": 88,
                "consumers": [],
            }),
            encoding="utf-8",
        )
        (self.state_dir / "my-job.session-id").write_text("persisted-session\n", encoding="utf-8")

        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env["CLAUDE_JOB_SESSION_PERSIST"] = "1"

        result = subprocess.run(
            ["/bin/zsh", str(_RUN_JOB), "my-job"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        args = (self.home / "claude-args.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(args.count("--resume"), 1)
        resume_index = args.index("--resume")
        self.assertEqual(args[resume_index + 1], "revive-session")
        self.assertNotIn("persisted-session", args)


if __name__ == "__main__":
    unittest.main()
