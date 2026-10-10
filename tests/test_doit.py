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

TEST_EXAMPLES = {
    "examples": [
        {"id": "one", "phrase": "example one", "command": "true",
         "explanation": "A harmless example.", "confirm": False, "source_url": None, "warning": None},
        {"id": "two", "phrase": "example two", "command": "exit 3",
         "explanation": "Fails on purpose.", "confirm": False, "source_url": None, "warning": None},
        {"id": "installer", "phrase": "install thing", "command": "true",
         "explanation": "Installs a thing with its vendor's installer.", "confirm": True,
         "source_url": "https://example.com/install.sh", "warning": "Be careful."},
    ]
}


class DoitTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name).resolve()
        self.home = home
        examples = home / "examples.json"
        examples.write_text(json.dumps(TEST_EXAMPLES))
        self.programs = home / "programs"
        self.programs.mkdir()
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"), "DOIT_EXAMPLES": str(examples),
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


class PhraseTestCase(DoitTestCase):
    """Starts with a few commands the user has made (doit ships with none)."""

    def setUp(self):
        super().setUp()
        doit.save_custom_command("do the thing", "true", False)
        doit.save_custom_command("thing", "true", False)
        doit.save_custom_command("break it", "exit 3", False)
        doit.save_custom_command("install thing", "true", True,
                                 doit.example_notes(TEST_EXAMPLES["examples"][2]))


class TestNormalize(DoitTestCase):
    def test_cleans_up_casual_typing(self):
        self.assertEqual(doit.normalize("  PC   Turn OFF!  "), "pc turn off")
        self.assertEqual(doit.normalize("please turn off"), "turn off")
        self.assertEqual(doit.normalize("turn off please!!"), "turn off")
        self.assertEqual(doit.normalize("?!."), "")


class TestBarePrompt(PhraseTestCase):
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


class TestPhrases(PhraseTestCase):
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


class TestConfirmation(PhraseTestCase):
    def test_installer_shows_source_and_warning_and_asks(self):
        code, out, prompts = self.run_doit(["install thing"], answers=["no", "y"])
        self.assertEqual(code, 0)
        self.assertIn("https://example.com/install.sh", out)
        self.assertIn("official installer", out)
        self.assertIn("Heads up: Be careful.", out)
        self.assertIn("Installs a thing with its vendor's installer.", out)
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


class TestLogging(PhraseTestCase):
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


class TestShippedExamples(DoitTestCase):
    def test_examples_are_complete_and_none_run_by_themselves(self):
        examples = doit.load_examples(ROOT / "data" / "examples.json")
        self.assertEqual([e["phrase"] for e in examples],
                         ["turn off", "restart", "disk space", "update my system",
                          "take a snapshot", "install brave"])
        for example in examples:
            self.assertTrue({"id", "phrase", "command", "explanation", "confirm"} <= set(example))
            self.assertIsNone(doit.phrase_problem(doit.normalize(example["phrase"]), {})[0],
                              f"{example['phrase']} should be free for the user to take")
            if example.get("source_url") or "sudo" in example["command"].split():
                self.assertTrue(example["confirm"], f"{example['id']} should ask first")

    def test_examples_are_not_commands(self):
        os.environ["DOIT_EXAMPLES"] = str(ROOT / "data" / "examples.json")
        for words in (["turn", "off"], ["install", "brave"], ["disk", "space"]):
            code, out, _ = self.run_doit(words, tty=False)
            self.assertEqual(code, 1, words)
            self.assertIn("doit create", out)

    def test_help_lists_built_in_words_and_examples(self):
        code, out, _ = self.run_doit(["help"], tty=False)
        self.assertEqual(code, 0)
        for text in ("doit create", "doit forget <phrase>", "/clippy <topic>", "Do what? I am waiting",
                     "doit example one", "-> exit 3"):
            self.assertIn(text, out)
        _, out_list, _ = self.run_doit(["list"], tty=False)
        self.assertEqual(out_list, out)


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
    def test_scan_reads_manuals_then_packages(self):
        doit.scan_library()
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
        doit.scan_library()
        library = json.loads(doit.library_path().read_text())
        _, shown = doit.search_library(library["programs"], "drives")
        self.assertEqual([p["name"] for p in shown], ["lsblk"])

    def test_exact_name_comes_first(self):
        doit.scan_library()
        library = json.loads(doit.library_path().read_text())
        _, shown = doit.search_library(library["programs"], "ls")
        self.assertEqual(shown[0]["name"], "ls")

    def test_before_any_scan_the_database_is_empty(self):
        code, out, _ = self.run_doit(["create"], answers=["1", "mystery"])
        self.assertIn("The database is empty", out)
        self.assertFalse(doit.library_path().exists())



class TestScanWithoutTools(DoitTestCase):
    def test_works_without_manuals_or_pacman(self):
        make_program(self.programs, "lsblk")
        library = doit.scan_library()
        self.assertFalse(library["has_manuals"])
        self.assertEqual([p["name"] for p in library["programs"]], ["lsblk"])


class TestCustomCommands(ScanTestCase):
    def test_type_it_myself_then_use_it(self):
        code, out, _ = self.run_doit(["create"], answers=["3", "true", "just check my fucking drives", "no", "yes"])
        self.assertEqual(code, 0)
        self.assertIn('Now "doit just check my fucking drives" runs: true', out)
        code, out, _ = self.run_doit(["Just", "check", "my", "fucking", "drives!!"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("Real command: true", out)
        self.assertIn("Your own command.", out)

    def test_pick_from_search_and_add_options(self):
        doit.scan_library()
        answers = ["1", "drives", "1", "-f", "check drives", "no", "yes"]
        code, _, _ = self.run_doit(["create"], answers=answers)
        self.assertEqual(code, 0)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["command"], "lsblk -f")
        _, out, _ = self.run_doit(["--dry-run", "check drives"], answers=["no"])
        self.assertIn("(lsblk: list block devices)", out)
        self.assertIn("[dry run] Would run: lsblk -f", out)

    def test_start_from_an_example(self):
        code, _, _ = self.run_doit(["create"], answers=["2", "2", "smash", "no", "yes"])
        self.assertEqual(code, 0)
        code, _, _ = self.run_doit(["smash"], answers=["no"])
        self.assertEqual(code, 3)

    def test_own_words_are_reserved(self):
        _, out, _ = self.run_doit(["create"], answers=["3", "true", "list", "my thing", "no", "yes"])
        self.assertIn("one of Alias Maker's own words", out)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["phrase"], "my thing")

    def test_example_phrase_is_offered_and_enter_takes_it(self):
        _, out, prompts = self.run_doit(["create"], answers=["2", "1", "", "no", "yes"])
        self.assertTrue(any('(Enter for "example one")' in p for p in prompts))
        self.assertIn("A harmless example.", out)
        self.assertEqual([c["phrase"] for c in doit.load_custom()], ["example one"])

    def test_example_notes_travel_with_the_command(self):
        self.run_doit(["create"], answers=["2", "3", "get thing", "yes"])
        saved = doit.load_custom()[0]
        self.assertEqual((saved["source_url"], saved["warning"], saved["confirm"]),
                         ("https://example.com/install.sh", "Be careful.", True))
        _, out, _ = self.run_doit(["get", "thing"], answers=["no", "nah"])
        self.assertIn("https://example.com/install.sh", out)
        self.assertIn("Heads up: Be careful.", out)
        doit.update_custom_command("get thing", "get it", "true", True)
        self.assertEqual(doit.load_custom()[0]["source_url"], "https://example.com/install.sh",
                         "renaming keeps the notes")
        doit.update_custom_command("get it", "get it", "echo different", True)
        self.assertNotIn("source_url", doit.load_custom()[0], "a changed command drops them")

    def test_replacing_my_own_phrase(self):
        self.run_doit(["create"], answers=["3", "true", "x", "no", "yes"])
        self.run_doit(["create"], answers=["3", "exit 4", "x", "yes", "no", "yes"])
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(len(saved), 1)
        code, _, _ = self.run_doit(["x"], answers=["no"])
        self.assertEqual(code, 4)

    def test_sudo_commands_always_ask(self):
        _, out, prompts = self.run_doit(["create"], answers=["3", "sudo true", "admin thing", "yes"])
        self.assertIn("always ask before running it", out)
        self.assertFalse(any(p.startswith("Ask before running") for p in prompts))
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertTrue(saved[0]["confirm"])

    def test_not_saving(self):
        code, out, _ = self.run_doit(["create"], answers=["3", "true", "x", "no", "nah"])
        self.assertEqual(code, 1)
        self.assertFalse(doit.custom_path().exists())

    def test_forget_and_delete(self):
        self.run_doit(["create"], answers=["3", "true", "my thing", "no", "yes"])
        self.run_doit(["create"], answers=["3", "true", "other thing", "no", "yes"])
        code, _, _ = self.run_doit(["forget", "my", "thing"], answers=["yes"])
        self.assertEqual(code, 0)
        code, out, _ = self.run_doit(["delete", "other", "thing"], answers=["yes"])
        self.assertEqual(code, 0)
        self.assertIn("only", out)
        self.assertEqual(json.loads(doit.custom_path().read_text())["commands"], [])
        code, out, _ = self.run_doit(["forget", "my", "thing"], answers=[])
        self.assertEqual(code, 1)
        code, out, _ = self.run_doit(["delete"], answers=[])
        self.assertEqual(code, 1)
        self.assertIn("Tell me which one", out)

    def test_removed_commands_are_gone(self):
        for words in (["add"], ["my", "commands"], ["rescan"], ["menu"], ["search", "drives"]):
            code, out, _ = self.run_doit(words, tty=False)
            self.assertEqual(code, 1, words)
            self.assertIn("don't know how to", out)
        self.assertFalse(doit.library_path().exists())  # nothing scanned from the terminal

    def test_ctrl_d_in_the_middle_saves_nothing(self):
        code, out, _ = self.run_doit(["create"], answers=["3", "true"])
        self.assertEqual(code, 0)
        self.assertIn("never mind", out)
        self.assertFalse(doit.custom_path().exists())


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
        custom_map = {"mine": {"phrase": "mine", "command": "ls"}}
        check = lambda text: doit.phrase_problem(doit.normalize(text), custom_map)
        self.assertEqual(check("  !! "), ("empty", None))
        self.assertEqual(check("list"), ("reserved", None))
        self.assertEqual(check("help"), ("reserved", None))
        self.assertEqual(check("forget my stuff"), ("reserved", None))
        self.assertEqual(check("delete my stuff"), ("reserved", None))
        self.assertEqual(check("create"), ("reserved", None))
        self.assertEqual(check("my commands"), (None, None))
        self.assertEqual(check("rescan"), (None, None))
        self.assertEqual(check("never mind"), ("reserved", None))
        self.assertEqual(check("Mine!"), ("custom-clash", "ls"))
        self.assertEqual(check("turn off"), (None, None))  # only an example, free to use
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



import functools
import http.server
import threading
import time
from datetime import datetime, timedelta


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class FakeWiki:
    """A tiny stand-in for wiki.cachyos.org and the Arch Wiki search, served on this machine."""

    PAGE = """<html><head><title>{title} | CachyOS</title>
<meta name="description" content="{description}"></head><body>text</body></html>"""

    def __init__(self, folder):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(folder)))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.pages = {
            "": ("CachyOS Wiki", "Welcome to the CachyOS wiki"),
            "features/cachy_chroot": ("CachyOS chroot Helper", "Helper tool to make it easier to chroot into systems"),
            "configuration/gaming": ("Gaming with CachyOS", "Set up Steam, Proton and controllers"),
            "configuration/automount_with_fstab": ("Automount with fstab", "Mount drives at boot"),
            "bg/features/cachy_chroot": ("Помощник за chroot", "Bulgarian page"),
        }
        self.write()

    def write(self):
        locs = "".join(f"<url><loc>{self.base}/{path + '/' if path else ''}</loc></url>" for path in self.pages)
        (self.folder / "sitemap-index.xml").write_text(
            f'<?xml version="1.0"?><sitemapindex><sitemap><loc>{self.base}/sitemap-0.xml</loc></sitemap></sitemapindex>')
        (self.folder / "sitemap-0.xml").write_text(f'<?xml version="1.0"?><urlset>{locs}</urlset>')
        for path, (title, description) in self.pages.items():
            folder = self.folder / path
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "index.html").write_text(self.PAGE.format(title=title, description=description))
        (self.folder / "api.php").write_text(json.dumps(
            ["chroot", ["Chroot"], [""], ["https://wiki.archlinux.org/title/Chroot"]]))

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class TestClippy(DoitTestCase):
    def setUp(self):
        super().setUp()
        os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        self.wiki = FakeWiki(self.home / "wiki")
        self.saved = (doit.CACHYOS_WIKI, doit.ARCH_WIKI_API)
        doit.CACHYOS_WIKI = self.wiki.base
        doit.ARCH_WIKI_API = f"{self.wiki.base}/api.php"
        self.opened = self.home / "opened.txt"
        opener = make_program(self.programs, "fake-opener", f'printf "%s" "$1" > "{self.opened}"')
        os.environ["ALIASMAKER_OPENER"] = str(opener)
        self.ran_chroot = self.home / "chroot-ran"
        make_program(self.programs, "chroot", f'touch "{self.ran_chroot}"')

    def tearDown(self):
        doit.CACHYOS_WIKI, doit.ARCH_WIKI_API = self.saved
        os.environ.pop("ALIASMAKER_OPENER", None)
        self.wiki.stop()
        super().tearDown()

    def test_index_keeps_english_pages_with_titles(self):
        index = doit.refresh_wiki_index()
        titles = sorted(p["title"] for p in index["pages"])
        self.assertEqual(titles, ["Automount with fstab", "CachyOS Wiki", "CachyOS chroot Helper",
                                  "Gaming with CachyOS"])
        chroot = [p for p in index["pages"] if p["title"] == "CachyOS chroot Helper"][0]
        self.assertEqual(chroot["url"], f"{self.wiki.base}/features/cachy_chroot/")
        self.assertEqual(chroot["description"], "Helper tool to make it easier to chroot into systems")

    def test_clippy_chrooting_shows_links_and_runs_nothing(self):
        code, out, prompts = self.run_doit(["/clippy", "chrooting"], answers=[""])
        self.assertEqual(code, 0)
        self.assertIn("CachyOS chroot Helper - Helper tool to make it easier to chroot into systems", out)
        self.assertIn(f"{self.wiki.base}/features/cachy_chroot/", out)
        self.assertIn("Arch Wiki", out)
        self.assertIn("https://wiki.archlinux.org/title/Chroot", out)
        self.assertIn("not running anything", out)
        self.assertTrue(prompts[-1].startswith("Open one?"))
        self.assertFalse(self.ran_chroot.exists())  # looked up, never run

    def test_picking_a_link_opens_it_in_the_browser(self):
        code, _, _ = self.run_doit(["/clippy", "chrooting"], answers=["1"])
        self.assertEqual(code, 0)
        for _ in range(50):
            if self.opened.exists():
                break
            time.sleep(0.05)
        self.assertEqual(self.opened.read_text(), f"{self.wiki.base}/features/cachy_chroot/")
        self.assertFalse(self.ran_chroot.exists())

    def test_plain_questions_work_too(self):
        _, out, _ = self.run_doit(["clippy", "how", "do", "I", "set", "up", "gaming"], tty=False)
        self.assertIn("Gaming with CachyOS", out)
        _, out, _ = self.run_doit(["clippy", "mounting", "drives"], tty=False)
        self.assertIn("Automount with fstab", out)

    def test_manual_pages_on_this_pc_are_offered(self):
        make_program(self.programs, "whatis", "printf '%s\\n' 'chroot (8)           - run command or interactive shell with special root directory'")
        doit.scan_library()
        code, out, _ = self.run_doit(["--dry-run", "/clippy", "chrooting"], answers=["3"])
        self.assertIn("On this PC", out)
        self.assertIn("chroot - run command or interactive shell with special root directory", out)
        self.assertIn("[dry run] Would open: man chroot", out)
        self.assertFalse(self.ran_chroot.exists())

    def test_wiki_list_is_reused_for_a_week(self):
        _, out, _ = self.run_doit(["clippy", "gaming"], tty=False)
        self.assertIn("Getting the CachyOS wiki's list", out)
        _, out, _ = self.run_doit(["clippy", "gaming"], tty=False)
        self.assertNotIn("Getting the CachyOS wiki's list", out)
        index = json.loads(doit.wiki_index_path().read_text())
        index["fetched_at"] = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
        doit.wiki_index_path().write_text(json.dumps(index))
        _, out, _ = self.run_doit(["clippy", "gaming"], tty=False)
        self.assertIn("Getting the CachyOS wiki's list", out)

    def test_offline_with_a_saved_list_still_shows_links(self):
        self.run_doit(["clippy", "gaming"], tty=False)
        index = json.loads(doit.wiki_index_path().read_text())
        index["fetched_at"] = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
        doit.wiki_index_path().write_text(json.dumps(index))
        self.wiki.stop()
        code, out, _ = self.run_doit(["clippy", "gaming"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("Gaming with CachyOS", out)
        self.assertIn("seem to be offline", out)
        self.wiki = FakeWiki(self.home / "wiki2")  # so tearDown has something to stop

    def test_offline_with_nothing_saved(self):
        self.wiki.stop()
        code, out, _ = self.run_doit(["clippy", "chrooting"], tty=False)
        self.assertEqual(code, 1)
        self.assertIn("seem to be offline", out)
        self.wiki = FakeWiki(self.home / "wiki2")

    def test_needs_a_topic(self):
        code, out, _ = self.run_doit(["/clippy"], tty=False)
        self.assertEqual(code, 1)
        self.assertIn("/clippy chrooting", out)

    def test_clippy_is_one_of_alias_makers_own_words(self):
        self.assertEqual(doit.phrase_problem("clippy stuff", {})[0], "reserved")

    def test_word_endings(self):
        self.assertIn("chroot", doit.expand_word("chrooting"))
        self.assertIn("run", doit.expand_word("running"))
        self.assertIn("mount", doit.expand_word("mounted"))
        self.assertIn("update", doit.expand_word("updated"))
        self.assertEqual(doit.expand_word("speed"), {"speed"})


if __name__ == "__main__":
    unittest.main()
