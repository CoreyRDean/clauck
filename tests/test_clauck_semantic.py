"""Unit tests for semantic JSON watchdog helpers in lib/clauck.

Run: python3 -m unittest discover tests
"""

from __future__ import annotations

import importlib.machinery
import json
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
