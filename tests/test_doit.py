"""Tests for the doit prototype. Run with: python3 -m unittest discover -s tests"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("doit", str(ROOT / "src" / "doit"))
_spec = importlib.util.spec_from_loader("doit", _loader)
doit = importlib.util.module_from_spec(_spec)
_loader.exec_module(doit)

TEST_INDEX = {
    "commands": [
        {"id": "ok", "category": "test", "phrases": ["do the thing", "thing"],
         "command": "true", "explanation": "Does a harmless thing.",
         "needs_root": False, "confirm": False, "source_url": None, "warning": None},
        {"id": "fail", "category": "test", "phrases": ["break it"],
         "command": "exit 3", "explanation": "Fails on purpose.",
         "needs_root": False, "confirm": False, "source_url": None, "warning": None},
        {"id": "careful", "category": "test", "phrases": ["install thing"],
         "command": "true", "explanation": "Needs a yes.",
         "needs_root": True, "confirm": True,
         "source_url": "https://example.com/install.sh", "warning": "Be careful."},
    ]
}


class DoitTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        index = home / "commands.json"
        index.write_text(json.dumps(TEST_INDEX))
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"), "DOIT_COMMANDS": str(index),
            "NO_COLOR": "1",
        })
        self.env.start()
        os.environ.pop("DOIT_DRY_RUN", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_doit(self, args, answers=None, tty=True):
        """Run main() with scripted answers. Returns (exit code, output, prompts shown)."""
        prompts = []
        answers = list(answers or [])

        def fake_input(prompt=""):
            prompts.append(prompt)
            if not answers:
                raise EOFError
            return answers.pop(0)

        out = io.StringIO()
        with mock.patch.object(doit, "interactive", return_value=tty), \
             mock.patch("builtins.input", side_effect=fake_input), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = doit.main(args)
        return code, out.getvalue(), prompts

    def settings(self):
        return doit.load_settings()

    def log_lines(self):
        path = doit.log_path()
        return path.read_text().splitlines() if path.is_file() else []


class TestNormalize(DoitTestCase):
    def test_cleans_up_casual_typing(self):
        self.assertEqual(doit.normalize("  PC   Turn OFF!  "), "pc turn off")
        self.assertEqual(doit.normalize("please turn off"), "turn off")
        self.assertEqual(doit.normalize("turn off please!!"), "turn off")
        self.assertEqual(doit.normalize("?!."), "")


class TestBarePrompt(DoitTestCase):
    def test_doit_alone_asks_do_what(self):
        code, out, prompts = self.run_doit([], answers=["do the thing", "no"])
        self.assertEqual(code, 0)
        self.assertEqual(prompts[0], "Do what? I am waiting... ")

    def test_keeps_waiting_through_blank_and_unknown_input(self):
        code, out, prompts = self.run_doit([], answers=["", "do teh thing", "do the thing", "no"])
        self.assertEqual(code, 0)
        self.assertEqual(sum(p.startswith("Do what?") for p in prompts), 3)
        self.assertIn('Did you mean: "do the thing"', out)

    def test_never_mind_runs_nothing(self):
        code, out, _ = self.run_doit([], answers=["never mind"])
        self.assertEqual(code, 0)
        self.assertIn("never mind", out)
        self.assertEqual(self.log_lines(), [])

    def test_ctrl_d_exits_quietly(self):
        code, _, _ = self.run_doit([], answers=[])
        self.assertEqual(code, 0)

    def test_not_a_terminal_prints_usage(self):
        code, out, prompts = self.run_doit([], tty=False)
        self.assertEqual(code, 2)
        self.assertEqual(prompts, [])


class TestPhrases(DoitTestCase):
    def test_runs_matching_phrase_and_shows_real_command(self):
        code, out, _ = self.run_doit(["Do", "the", "thing!"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("Real command: true", out)

    def test_unknown_phrase_suggests_and_fails(self):
        code, out, _ = self.run_doit(["brake", "it"], tty=False)
        self.assertEqual(code, 1)
        self.assertIn('"break it"', out)

    def test_failing_command_returns_its_exit_code(self):
        code, out, _ = self.run_doit(["break", "it"], answers=["no"])
        self.assertEqual(code, 3)
        self.assertIn("didn't work", out)

    def test_dry_run_does_not_run(self):
        code, out, _ = self.run_doit(["--dry-run", "break", "it"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("[dry run] Would run: exit 3", out)


class TestConfirmation(DoitTestCase):
    def test_installer_shows_source_and_warning_and_asks(self):
        code, out, prompts = self.run_doit(["install thing"], answers=["no", "y"])
        self.assertEqual(code, 0)
        self.assertIn("https://example.com/install.sh", out)
        self.assertIn("official installer", out)
        self.assertIn("Heads up: Be careful.", out)
        self.assertTrue(prompts[-1].startswith("Go ahead?"))

    def test_saying_no_cancels(self):
        code, out, _ = self.run_doit(["install thing"], answers=["no", "nah"])
        self.assertEqual(code, 1)
        self.assertIn("not doing it", out)

    def test_strict_mode_needs_full_word(self):
        self.run_doit(["answer", "strict"])
        code, _, _ = self.run_doit(["install thing"], answers=["no", "y"])
        self.assertEqual(code, 1)
        code, _, _ = self.run_doit(["install thing"], answers=["YES"])
        self.assertEqual(code, 0)

    def test_custom_yes_word(self):
        self.run_doit(["answer", "word", "doit"])
        code, _, _ = self.run_doit(["install thing"], answers=["no", "doit"])
        self.assertEqual(code, 0)

    def test_needs_terminal_for_confirmation(self):
        code, out, prompts = self.run_doit(["install thing"], tty=False)
        self.assertEqual(code, 1)
        self.assertIn("needs a yes from you", out)
        self.assertEqual(prompts, [])


class TestLogging(DoitTestCase):
    def test_first_run_asks_once_and_logs_when_yes(self):
        code, out, prompts = self.run_doit(["thing"], answers=["yes"])
        self.assertEqual(code, 0)
        self.assertTrue(any(p.startswith("Keep a log?") for p in prompts))
        self.assertIs(self.settings()["logging"], True)
        self.run_doit(["break it"])
        lines = self.log_lines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("\tthing\ttrue\t0"))
        self.assertTrue(lines[1].endswith("\tbreak it\texit 3\t3"))
        _, _, prompts = self.run_doit(["thing"])
        self.assertFalse(any(p.startswith("Keep a log?") for p in prompts))

    def test_saying_no_still_translates_but_writes_nothing(self):
        code, _, _ = self.run_doit(["thing"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIs(self.settings()["logging"], False)
        self.assertEqual(self.log_lines(), [])

    def test_turn_on_later_and_view_history(self):
        self.run_doit(["thing"], answers=["no"])
        self.run_doit(["logging", "on"])
        self.run_doit(["break it"])
        code, out, _ = self.run_doit(["show me what you did"])
        self.assertEqual(code, 0)
        self.assertIn('"break it"  ->  exit 3  [failed (code 3)]', out)

    def test_non_interactive_never_asks_or_logs(self):
        code, _, prompts = self.run_doit(["thing"], tty=False)
        self.assertEqual(code, 0)
        self.assertEqual(prompts, [])
        self.assertIsNone(self.settings()["logging"])
        self.assertEqual(self.log_lines(), [])


class TestRealIndex(DoitTestCase):
    def test_shipped_index_loads_without_duplicate_phrases(self):
        index = ROOT / "data" / "commands.json"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            commands, phrase_map = doit.load_index(index)
        self.assertEqual(err.getvalue(), "")
        required = {"id", "category", "phrases", "command", "explanation",
                    "needs_root", "confirm", "source_url", "warning"}
        for entry in commands:
            self.assertTrue(required <= set(entry), entry["id"])
            if entry["source_url"]:
                self.assertTrue(entry["confirm"], f"{entry['id']} downloads code but doesn't ask")


if __name__ == "__main__":
    unittest.main()
