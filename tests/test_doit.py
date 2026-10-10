"""Tests for the doit prototype. Run with: python3 -m unittest discover -s tests"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import aliasmaker_core as doit  # noqa: E402  (the engine behind doit and the window)

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
        home = Path(self.tmp.name).resolve()
        self.home = home
        index = home / "commands.json"
        index.write_text(json.dumps(TEST_INDEX))
        self.programs = home / "programs"
        self.programs.mkdir()
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"), "DOIT_COMMANDS": str(index),
            "NO_COLOR": "1", "PATH": str(self.programs),
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


def make_program(folder, name, body="exit 0"):
    path = folder / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


FAKE_WHATIS = """printf '%s\\n' \\
  'lsblk (8)            - list block devices' \\
  'ls (1)               - list directory contents' \\
  'printf (3)           - formatted output conversion' \\
  'printf (1)           - format and print data' \\
  'time (2)             - get time in seconds'
"""


class ScanTestCase(DoitTestCase):
    """A fake PC: a few programs, plus stand-in whatis and pacman that print real-looking output."""

    def setUp(self):
        super().setUp()
        for name in ("lsblk", "ls", "printf", "time", "mystery", "orphan"):
            make_program(self.programs, name)
        p = self.programs
        make_program(p, "whatis", FAKE_WHATIS)
        pacman = f"""case "$1" in
  -Ql) printf '%s\\n' 'util-linux {p}/lsblk' 'coreutils {p}/ls' 'mystery-pkg {p}/mystery' 'mystery-pkg /usr/share/doc/x' ;;
  -Qi) printf '%s\\n' 'Name            : util-linux' 'Description     : Miscellaneous system utilities for Linux' '' \\
         'Name            : coreutils' 'Description     : The basic file utilities' '' \\
         'Name            : mystery-pkg' 'Description     : A mystery tool' ;;
esac
"""
        make_program(p, "pacman", pacman)

    def library(self):
        return {e["name"]: e for e in json.loads(doit.library_path().read_text())["programs"]}


class TestScan(ScanTestCase):
    def test_rescan_reads_manuals_then_packages(self):
        code, out, _ = self.run_doit(["rescan"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("Found", out)
        lib = self.library()
        self.assertEqual(lib["lsblk"]["description"], "list block devices")
        self.assertEqual(lib["lsblk"]["source"], "manual")
        self.assertEqual(lib["lsblk"]["package"], "util-linux")
        self.assertEqual(lib["printf"]["description"], "format and print data")
        self.assertEqual(lib["mystery"]["description"], "A mystery tool")
        self.assertEqual(lib["mystery"]["source"], "package")
        self.assertEqual(lib["time"]["source"], "none")  # only a section-2 page, not a command
        self.assertEqual(lib["orphan"]["description"], "")

    def test_search_finds_drives_through_plain_words(self):
        self.run_doit(["rescan"], tty=False)
        code, out, _ = self.run_doit(["search", "drives"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("lsblk  -  list block devices", out)
        self.assertNotIn(" ls  -", out)

    def test_exact_name_comes_first(self):
        self.run_doit(["rescan"], tty=False)
        library = json.loads(doit.library_path().read_text())
        _, shown = doit.search_library(library["programs"], "ls")
        self.assertEqual(shown[0]["name"], "ls")

    def test_search_before_any_scan_says_the_database_is_empty(self):
        code, out, _ = self.run_doit(["search", "mystery"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("The database is empty", out)
        self.assertFalse(doit.library_path().exists())

    def test_search_also_shows_easy_commands(self):
        _, out, _ = self.run_doit(["search", "harmless"], tty=False)
        self.assertIn("Easy commands:", out)
        self.assertIn("doit do the thing", out)


class TestScanWithoutTools(DoitTestCase):
    def test_works_without_manuals_or_pacman(self):
        make_program(self.programs, "lsblk")
        code, out, _ = self.run_doit(["rescan"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("sudo pacman -S man-db man-pages", out)
        lib = json.loads(doit.library_path().read_text())["programs"]
        self.assertEqual([p["name"] for p in lib], ["lsblk"])


class TestCustomCommands(ScanTestCase):
    def test_type_it_myself_then_use_it(self):
        code, out, _ = self.run_doit(["add"], answers=["3", "true", "just check my fucking drives", "no", "yes"])
        self.assertEqual(code, 0)
        self.assertIn('Now "doit just check my fucking drives" runs: true', out)
        code, out, _ = self.run_doit(["Just", "check", "my", "fucking", "drives!!"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("Real command: true", out)
        self.assertIn("Your own command.", out)

    def test_pick_from_search_and_add_options(self):
        self.run_doit(["rescan"], tty=False)
        answers = ["1", "drives", "1", "-f", "check drives", "no", "yes"]
        code, _, _ = self.run_doit(["add"], answers=answers)
        self.assertEqual(code, 0)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["command"], "lsblk -f")
        _, out, _ = self.run_doit(["--dry-run", "check drives"], answers=["no"])
        self.assertIn("(lsblk: list block devices)", out)
        self.assertIn("[dry run] Would run: lsblk -f", out)

    def test_pick_from_easy_commands(self):
        code, _, _ = self.run_doit(["add"], answers=["2", "2", "smash", "no", "yes"])
        self.assertEqual(code, 0)
        code, _, _ = self.run_doit(["smash"], answers=["no"])
        self.assertEqual(code, 3)

    def test_own_words_are_reserved(self):
        _, out, _ = self.run_doit(["add"], answers=["3", "true", "menu", "my thing", "no", "yes"])
        self.assertIn("one of Alias Maker's own words", out)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["phrase"], "my thing")

    def test_overriding_an_easy_phrase_asks_and_then_wins(self):
        self.run_doit(["add"], answers=["3", "exit 5", "thing", "yes", "no", "yes"])
        code, _, _ = self.run_doit(["thing"], answers=["no"])
        self.assertEqual(code, 5)

    def test_saying_no_to_override_asks_for_another_phrase(self):
        _, out, prompts = self.run_doit(["add"], answers=["3", "exit 5", "thing", "no", "other", "no", "yes"])
        self.assertIn("already an easy command", out)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["phrase"], "other")

    def test_replacing_my_own_phrase(self):
        self.run_doit(["add"], answers=["3", "true", "x", "no", "yes"])
        self.run_doit(["add"], answers=["3", "exit 4", "x", "yes", "no", "yes"])
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(len(saved), 1)
        code, _, _ = self.run_doit(["x"], answers=["no"])
        self.assertEqual(code, 4)

    def test_sudo_commands_always_ask(self):
        _, out, prompts = self.run_doit(["add"], answers=["3", "sudo true", "admin thing", "yes"])
        self.assertIn("always ask before running it", out)
        self.assertFalse(any(p.startswith("Ask before running") for p in prompts))
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertTrue(saved[0]["confirm"])

    def test_not_saving(self):
        code, out, _ = self.run_doit(["add"], answers=["3", "true", "x", "no", "nah"])
        self.assertEqual(code, 1)
        self.assertFalse(doit.custom_path().exists())

    def test_list_and_forget(self):
        self.run_doit(["add"], answers=["3", "true", "my thing", "no", "yes"])
        _, out, _ = self.run_doit(["my", "commands"], tty=False)
        self.assertIn("doit my thing  ->  true", out)
        code, _, _ = self.run_doit(["forget", "my", "thing"], answers=["yes"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(doit.custom_path().read_text())["commands"], [])
        code, out, _ = self.run_doit(["forget", "my", "thing"], answers=[])
        self.assertEqual(code, 1)

    def test_ctrl_d_in_the_middle_saves_nothing(self):
        code, out, _ = self.run_doit(["add"], answers=["3", "true"])
        self.assertEqual(code, 0)
        self.assertIn("never mind", out)
        self.assertFalse(doit.custom_path().exists())


class TestMenu(ScanTestCase):
    def test_walk_into_custom_commands_and_back_out(self):
        code, out, _ = self.run_doit(["menu"], answers=["1", "3", "", "", ""])
        self.assertEqual(code, 0)
        self.assertIn("Alias Maker menu", out)
        self.assertIn("1) Make a new one", out)

    def test_run_an_easy_command_from_the_menu(self):
        code, out, _ = self.run_doit(["menu"], answers=["1", "1", "1", "1", "no", "", "", ""])
        self.assertEqual(code, 0)
        self.assertIn("Real command: true", out)

    def test_find_a_program_and_make_a_custom_command(self):
        self.run_doit(["rescan"], tty=False)
        answers = ["1", "2", "drives", "1", "1", "-f", "see drives", "no", "yes", "", "", ""]
        code, out, _ = self.run_doit(["menu"], answers=answers)
        self.assertEqual(code, 0)
        self.assertIn("Comes from the package: util-linux", out)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0], {**saved[0], "phrase": "see drives", "command": "lsblk -f"})

    def test_change_yes_word_in_settings(self):
        self.run_doit(["menu"], answers=["2", "3", "", ""])
        self.assertEqual(self.settings()["yes_words"], ["yes"])

    def test_bad_input_asks_again(self):
        _, out, _ = self.run_doit(["menu"], answers=["9", "banana", ""])
        self.assertIn("Type a number from 1 to 3", out)

    def test_ctrl_d_leaves(self):
        code, out, _ = self.run_doit(["menu"], answers=["1"])
        self.assertEqual(code, 0)
        self.assertIn("never mind", out)

    def test_menu_from_the_waiting_prompt(self):
        code, out, prompts = self.run_doit([], answers=["menu", ""])
        self.assertEqual(code, 0)
        self.assertEqual(prompts[0], "Do what? I am waiting... ")
        self.assertIn("Alias Maker menu", out)

    def test_needs_a_terminal(self):
        code, out, _ = self.run_doit(["menu"], tty=False)
        self.assertEqual(code, 2)


class TestOldFolders(DoitTestCase):
    def test_moves_settings_from_the_old_doit_folder(self):
        old = self.home / "config" / "doit"
        old.mkdir(parents=True)
        (old / "settings.json").write_text(json.dumps({"logging": False, "yes_words": ["yes"]}))
        self.run_doit(["list"], tty=False)
        self.assertEqual(self.settings()["yes_words"], ["yes"])
        self.assertFalse(old.exists())



class TestWindowHelpers(DoitTestCase):
    """The non-interactive helpers the Alias Maker window uses."""

    def test_phrase_problem(self):
        _, phrase_map = doit.load_index(Path(os.environ["DOIT_COMMANDS"]))
        custom_map = {"mine": {"phrase": "mine", "command": "ls"}}
        check = lambda text: doit.phrase_problem(doit.normalize(text), custom_map, phrase_map)
        self.assertEqual(check("  !! "), ("empty", None))
        self.assertEqual(check("menu"), ("reserved", None))
        self.assertEqual(check("search my stuff"), ("reserved", None))
        self.assertEqual(check("never mind"), ("reserved", None))
        self.assertEqual(check("Mine!"), ("custom-clash", "ls"))
        self.assertEqual(check("thing"), ("easy-clash", "true"))
        self.assertEqual(check("just check my fucking drives"), (None, None))

    def test_save_replaces_same_phrase_and_remove(self):
        doit.save_custom_command("Check Drives", "lsblk", False)
        doit.save_custom_command("check drives!", "lsblk -f", True)
        saved = doit.load_custom()
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0]["command"], saved[0]["confirm"]), ("lsblk -f", True))
        self.assertEqual(doit.remove_custom_command("CHECK DRIVES"), [])
        self.assertEqual(doit.load_custom(), [])

    def test_doit_sees_phrases_saved_by_the_window(self):
        doit.save_custom_command("see drives", "true", False)
        code, out, _ = self.run_doit(["see", "drives"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("Real command: true", out)



class TestEditAndDelete(DoitTestCase):
    def test_edit_keeps_position_and_changes_everything(self):
        doit.save_custom_command("first", "true", False)
        doit.save_custom_command("second", "ls", False)
        doit.update_custom_command("first", "renamed", "lsblk -f", True)
        saved = doit.load_custom()
        self.assertEqual([c["phrase"] for c in saved], ["renamed", "second"])
        self.assertEqual((saved[0]["command"], saved[0]["confirm"]), ("lsblk -f", True))
        self.assertIn("edited", saved[0])

    def test_edit_onto_another_alias_replaces_it(self):
        doit.save_custom_command("a", "true", False)
        doit.save_custom_command("b", "ls", False)
        doit.update_custom_command("a", "B!", "lsblk", False)
        saved = doit.load_custom()
        self.assertEqual([(c["phrase"], c["command"]) for c in saved], [("B!", "lsblk")])

    def test_edit_without_changing_the_phrase(self):
        doit.save_custom_command("same", "true", False)
        doit.update_custom_command("same", "same", "ls", False)
        self.assertEqual([c["command"] for c in doit.load_custom()], ["ls"])

    def test_delete_only_touches_the_alias_list(self):
        program = self.programs / "lsblk"
        program.write_text("#!/bin/sh\nexit 0\n")
        program.chmod(0o755)
        def snapshot():
            return {str(f): f.read_bytes() for f in self.home.rglob("*")
                    if f.is_file() and f.name != "custom.json"}
        before = snapshot()
        doit.save_custom_command("check drives", f"{program} -f", False)
        doit.remove_custom_command("check drives")
        self.assertEqual(snapshot(), before)  # every other file is exactly as it was
        self.assertTrue(program.is_file() and os.access(program, os.X_OK))
        self.assertEqual(doit.load_custom(), [])

    def test_forget_says_the_real_command_is_untouched(self):
        doit.save_custom_command("check drives", "sudo lsblk -f", False)
        code, out, _ = self.run_doit(["forget", "check", "drives"], answers=["yes"])
        self.assertEqual(code, 0)
        self.assertIn("not deleted or changed", out)
        self.assertIn("lsblk itself is still there, untouched", out)

    def test_target_program(self):
        self.assertEqual(doit.target_program("sudo lsblk -f"), "lsblk")
        self.assertEqual(doit.target_program("df -h"), "df")


if __name__ == "__main__":
    unittest.main()
