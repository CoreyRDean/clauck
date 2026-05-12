"""Unit tests for semantic JSON watchdog helpers in lib/clauck.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import importlib.machinery
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

_LIB = Path(__file__).parent.parent / "lib" / "clauck"
_loader = importlib.machinery.SourceFileLoader("clauck_semantic", str(_LIB))
_mod = _loader.load_module()


class TestExtractJsonEnvelope(unittest.TestCase):

    def test_whole_stdout_json_is_parsed(self):
        envelope = {"result": "done", "is_error": False}
        parsed = _mod._extract_json_envelope(json.dumps(envelope))
        self.assertEqual(parsed, envelope)

    def test_last_json_line_wins_when_stdout_has_prefix_noise(self):
        envelope = {"result": '{"command_type":"semantic"}', "is_error": False}
        parsed = _mod._extract_json_envelope(f"note before json\n{json.dumps(envelope)}\n")
        self.assertEqual(parsed, envelope)


class TestParseInterpreterResult(unittest.TestCase):

    def test_multiline_stdout_still_routes(self):
        envelope = {"result": '{"command_type":"semantic","interpretation":"ok"}'}
        result = subprocess.CompletedProcess(
            ["claude"],
            0,
            f"cache warmup\n{json.dumps(envelope)}\n",
            "",
        )
        routing, err = _mod._parse_interpreter_result(result, re)
        self.assertEqual(err, "")
        self.assertEqual(routing["command_type"], "semantic")
        self.assertEqual(routing["interpretation"], "ok")


class TestBuildInterpreterPrompt(unittest.TestCase):

    def test_semantic_routes_emit_scale_only(self):
        prompt = _mod._build_interpreter_prompt()
        self.assertIn('"task_complexity_scale"', prompt)
        self.assertNotIn('"exec_model"', prompt)
        self.assertIn("Emit ONLY `task_complexity_scale`", prompt)


class TestRunJsonCli(unittest.TestCase):

    def test_clean_exit_preserves_json_stdout(self):
        script = (
            "import json; "
            "print(json.dumps({'result':'ok','is_error':False}), flush=True)"
        )
        result = _mod._run_json_cli(
            [sys.executable, "-c", script],
            terminal_wait_seconds=0.1,
            kill_wait_seconds=0.1,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(_mod._extract_json_envelope(result.stdout).get("result"), "ok")

    def test_terminal_output_unblocks_lingering_process(self):
        script = (
            "import json,time; "
            "print(json.dumps({'result':'ok','is_error':False}), flush=True); "
            "time.sleep(30)"
        )
        started = time.monotonic()
        result = _mod._run_json_cli(
            [sys.executable, "-c", script],
            terminal_wait_seconds=0.1,
            kill_wait_seconds=0.1,
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.0)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(_mod._extract_json_envelope(result.stdout).get("result"), "ok")


class TestCmdSemanticSizing(unittest.TestCase):

    def test_semantic_stage_two_uses_shared_sizing_formula(self):
        interpreter_routing = {
            "command_type": "semantic",
            "interpretation": "Inspect registered jobs",
            "enhanced_prompt": "Read the manifest and summarize the registered jobs.",
            "task_complexity_scale": 0.25,
            # Legacy fields should be ignored once sizing is formula-derived.
            "exec_model": "opus",
            "exec_effort": "high",
            "exec_max_turns": 99,
            "exec_max_budget_usd": 9.99,
        }
        stage1 = subprocess.CompletedProcess(
            ["claude"],
            0,
            json.dumps({"result": json.dumps(interpreter_routing), "is_error": False}),
            "",
        )
        stage2 = subprocess.CompletedProcess(
            ["claude"],
            0,
            json.dumps({"result": "done", "is_error": False}),
            "",
        )
        sized = {
            "model": "sonnet",
            "effort": "medium",
            "max_turns": 7,
            "max_budget_usd": 0.42,
            "explanation": "scale=0.25 -> sonnet/medium",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".state"
            jobs_dir = root / "jobs"
            state_dir.mkdir(parents=True, exist_ok=True)
            jobs_dir.mkdir(parents=True, exist_ok=True)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(_mod, "STATE_DIR", state_dir),
                patch.object(_mod, "JOBS_DIR", jobs_dir),
                patch.object(_mod, "MANIFEST", jobs_dir / ".manifest.json"),
                patch.object(_mod, "CONFIG_FILE", jobs_dir / ".clauck.config.json"),
                patch.object(_mod, "MARKETPLACE_DIR", root / "marketplace"),
                patch.object(_mod, "TRIGGER_SCRIPT", root / "trigger-job.sh"),
                patch.object(_mod, "_find_claude", return_value="/usr/bin/claude"),
                patch.object(_mod, "_run_json_cli", side_effect=[stage1, stage2]) as mock_run_json_cli,
                patch.object(_mod.sizing, "load_doctor_config", return_value={}),
                patch.object(_mod.sizing, "compute_sizing", return_value=sized) as mock_compute_sizing,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                _mod.cmd_semantic("list my jobs")

        mock_compute_sizing.assert_called_once_with(
            0.25,
            _mod.sizing.estimate_tokens("Read the manifest and summarize the registered jobs."),
            {},
            strict_mcp=False,
        )
        stage2_argv = mock_run_json_cli.call_args_list[1].args[0]
        self.assertIn("--model", stage2_argv)
        self.assertEqual(stage2_argv[stage2_argv.index("--model") + 1], "sonnet")
        self.assertEqual(stage2_argv[stage2_argv.index("--effort") + 1], "medium")
        self.assertEqual(stage2_argv[stage2_argv.index("--max-turns") + 1], "7")
        self.assertEqual(stage2_argv[stage2_argv.index("--max-budget-usd") + 1], "0.42")
        self.assertIn("scale=0.25 -> sonnet/medium", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
