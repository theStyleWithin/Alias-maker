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
        examples = doit.load_examples(ROOT / "data" / "examples.json", every=True)
        self.assertEqual(sorted({e["phrase"] for e in examples}),
                         ["disk space", "install brave", "restart", "take a snapshot",
                          "turn off", "update my apps", "update my system"])
        self.assertEqual(len({e["id"] for e in examples}), len(examples))
        for example in examples:
            self.assertTrue({"id", "phrase", "command", "explanation", "confirm"} <= set(example))
            self.assertIsNone(doit.phrase_problem(doit.normalize(example["phrase"]), {})[0],
                              f"{example['phrase']} should be free for the user to take")
            if example.get("source_url") or "sudo" in example["command"].split():
                self.assertTrue(example["confirm"], f"{example['id']} should ask first")

    def os_release(self, text):
        path = Path(self.tmp.name) / "os-release"
        path.write_text(text)
        os.environ["ALIASMAKER_OS_RELEASE"] = str(path)
        self.addCleanup(os.environ.pop, "ALIASMAKER_OS_RELEASE", None)

    def offered(self):
        everything = Path(self.tmp.name) / "bin"
        everything.mkdir(exist_ok=True)
        for program in ("systemctl", "df", "pacman", "apt", "dnf", "flatpak", "snapper", "curl"):
            (everything / program).write_text("#!/bin/sh\n")
            (everything / program).chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(everything)}):
            examples = doit.load_examples(ROOT / "data" / "examples.json")
        return {e["phrase"]: e["command"] for e in examples}

    def test_each_os_gets_its_own_update_command(self):
        self.os_release('NAME="CachyOS Linux"\nID=cachyos\nID_LIKE=arch\n')
        self.assertIn("cachyos-keyring", self.offered()["update my system"])
        self.os_release('NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04 LTS"\n')
        self.assertEqual(doit.detect_os()["name"], "Ubuntu 24.04 LTS")
        self.assertEqual(self.offered()["update my system"], "sudo apt update && sudo apt full-upgrade")
        self.os_release('NAME="SteamOS"\nID=steamos\nID_LIKE=arch\n')
        offered = self.offered()
        self.assertNotIn("update my system", offered, "SteamOS is read-only: no pacman updates")
        self.assertNotIn("install brave", offered)
        self.assertEqual(offered["update my apps"], "flatpak update")

    def test_examples_need_their_program(self):
        self.os_release("ID=ubuntu\nID_LIKE=debian\n")
        with mock.patch.dict(os.environ, {"PATH": str(Path(self.tmp.name))}):
            self.assertEqual(doit.load_examples(ROOT / "data" / "examples.json"), [])

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

    def test_best_match_comes_first(self):
        def prog(name, description, package=""):
            return {"name": name, "description": description, "package": package}
        programs = [
            prog("df", "report file system space usage", "coreutils"),
            prog("du", "estimate file space usage", "coreutils"),
            prog("findmnt", "find a filesystem", "util-linux"),
            prog("fdisk", "manipulate disk partition table", "util-linux"),
            prog("lsblk", "list block devices", "util-linux"),
            prog("udisksctl", "The udisks command line tool", "udisks2"),
            prog("hdparm", "get/set SATA/IDE device parameters", "hdparm"),
            prog("nmcli", "command-line tool for controlling NetworkManager", "networkmanager"),
            prog("iwctl", "Internet wireless control utility", "iwd"),
        ]
        _, shown = doit.search_library(programs, "drives")
        names = [p["name"] for p in shown]
        self.assertEqual(names[:3], ["lsblk", "df", "findmnt"])
        self.assertNotIn("hdparm", names)
        _, shown = doit.search_library(programs, "disk space")
        self.assertEqual(shown[0]["name"], "df")
        _, shown = doit.search_library(programs, "wifi")
        self.assertEqual(shown[0]["name"], "nmcli")
        _, shown = doit.search_library(programs, "lsblk")
        self.assertEqual([p["name"] for p in shown], ["lsblk"])

    def test_before_any_scan_the_database_is_empty(self):
        code, out, _ = self.run_doit(["create"], answers=["", "1", "mystery"])
        self.assertIn("The database is empty", out)
        self.assertFalse(doit.library_path().exists())

    def test_installing_something_makes_the_database_out_of_date(self):
        self.assertTrue(doit.library_outdated(), "no scan yet")
        doit.scan_library()
        self.assertFalse(doit.library_outdated())
        os.utime(self.programs, (1, 1))  # what installing or removing a program does
        self.assertTrue(doit.library_outdated())

    def test_unknown_commands_are_explained(self):
        doit.scan_library()
        doit.save_custom_command("check my drives", "lsblk", False)
        code, out, _ = self.run_doit(["--not-found", "check", "my", "drives"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn("Put doit in front of it: doit check my drives", out)
        code, out, _ = self.run_doit(["--not-found", "lsblkk"], tty=False)
        self.assertEqual(code, 1)
        self.assertIn('"lsblkk" isn\'t a program on this PC', out)
        self.assertIn("similar name: lsblk", out)


class TestScanOnUbuntu(DoitTestCase):
    def test_packages_come_from_dpkg(self):
        make_program(self.programs, "lsblk")
        make_program(self.programs, "dpkg-query",
                     "printf 'util-linux\\tmiscellaneous system utilities\\nother\\t\\n'")
        info = Path(self.tmp.name) / "dpkg-info"
        info.mkdir()
        (info / "util-linux:amd64.list").write_text(f"/.\n{self.programs}/lsblk\n")
        with mock.patch.object(doit, "DPKG_INFO", str(info)):
            library = doit.scan_library()
        self.assertEqual(library["package_tool"], "dpkg")
        lsblk = next(p for p in library["programs"] if p["name"] == "lsblk")
        self.assertEqual((lsblk["package"], lsblk["description"]),
                         ("util-linux", "miscellaneous system utilities"))



class TestScanWithoutTools(DoitTestCase):
    def test_works_without_manuals_or_pacman(self):
        make_program(self.programs, "lsblk")
        library = doit.scan_library()
        self.assertFalse(library["has_manuals"])
        self.assertEqual([p["name"] for p in library["programs"]], ["lsblk"])


class TestCustomCommands(ScanTestCase):
    def test_type_it_myself_then_use_it(self):
        code, out, _ = self.run_doit(["create"], answers=["true", "just check my fucking drives", "4", "no", "yes"])
        self.assertEqual(code, 0)
        self.assertIn('Now "doit just check my fucking drives" runs: true', out)
        code, out, _ = self.run_doit(["Just", "check", "my", "fucking", "drives!!"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("Real command: true", out)
        self.assertIn("Your own command.", out)

    def test_pick_from_search_and_add_options(self):
        doit.scan_library()
        answers = ["", "1", "drives", "1", "-f", "check drives", "2", "no", "yes"]
        code, _, _ = self.run_doit(["create"], answers=answers)
        self.assertEqual(code, 0)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["command"], "lsblk -f")
        _, out, _ = self.run_doit(["--dry-run", "check drives"], answers=["no"])
        self.assertIn("(lsblk: list block devices)", out)
        self.assertIn("[dry run] Would run: lsblk -f", out)

    def test_start_from_an_example(self):
        code, _, _ = self.run_doit(["create"], answers=["", "2", "2", "smash", "no", "yes"])
        self.assertEqual(code, 0)
        code, _, _ = self.run_doit(["smash"], answers=["no"])
        self.assertEqual(code, 3)

    def test_own_words_are_reserved(self):
        _, out, _ = self.run_doit(["create"], answers=["true", "list", "my thing", "2", "no", "yes"])
        self.assertIn("one of Alias Maker's own words", out)
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(saved[0]["phrase"], "my thing")

    def test_example_phrase_is_offered_and_enter_takes_it(self):
        _, out, prompts = self.run_doit(["create"], answers=["", "2", "1", "", "2", "no", "yes"])
        self.assertTrue(any('(Enter for "example one")' in p for p in prompts))
        self.assertIn("A harmless example.", out)
        self.assertEqual([c["phrase"] for c in doit.load_custom()], ["example one"])

    def test_example_notes_travel_with_the_command(self):
        self.run_doit(["create"], answers=["", "2", "3", "get thing", "2", "yes"])
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
        self.run_doit(["create"], answers=["true", "x", "no", "yes"])
        self.run_doit(["create"], answers=["exit 4", "x", "yes", "no", "yes"])
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertEqual(len(saved), 1)
        code, _, _ = self.run_doit(["x"], answers=["no"])
        self.assertEqual(code, 4)

    def test_sudo_commands_always_ask(self):
        _, out, prompts = self.run_doit(["create"], answers=["sudo true", "admin thing", "2", "yes"])
        self.assertIn("always ask before running it", out)
        self.assertFalse(any(p.startswith("Ask before running") for p in prompts))
        saved = json.loads(doit.custom_path().read_text())["commands"]
        self.assertTrue(saved[0]["confirm"])

    def test_not_saving(self):
        code, out, _ = self.run_doit(["create"], answers=["true", "x", "no", "nah"])
        self.assertEqual(code, 1)
        self.assertFalse(doit.custom_path().exists())

    def test_forget_and_delete(self):
        self.run_doit(["create"], answers=["true", "my thing", "2", "no", "yes"])
        self.run_doit(["create"], answers=["true", "other thing", "2", "no", "yes"])
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
        code, out, _ = self.run_doit(["create"], answers=["true"])
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
            return {str(f): f.read_bytes() for f in self.home.rglob("*")  # Alias Maker's own two files aside
                    if f.is_file() and f.name not in ("custom.json", "alias-maker.fish")}
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



class TestRealTerminalCommands(DoitTestCase):
    """One-word commands become real fish commands through Alias Maker's own file."""

    def shortcuts(self):
        path = doit.fish_shortcuts_path()
        return path.read_text() if path.exists() else ""

    def test_spaces_get_the_pick_a_name_menu(self):
        code, out, prompts = self.run_doit(
            ["create"], answers=["lsblk -f", "just check my fucking drives", "2", "no", "yes"])
        self.assertEqual(code, 0)
        self.assertTrue(prompts[0].startswith("What command do you want it to point to?"))
        self.assertTrue(prompts[1].startswith("Name the new command:"))
        self.assertIn('it would look for a program called "just"', out)
        for line in ("1) doit check drives", "2) check-drives", "3) just-check-my-fucking-drives",
                     "4) doit just check my fucking drives"):
            self.assertIn(line, out)
        self.assertEqual([c["phrase"] for c in doit.load_custom()], ["check-drives"])
        self.assertIn("You can also type just: check-drives", out)

    def test_from_an_appimage_shortcuts_run_the_appimage_file(self):
        appimage = Path(self.tmp.name) / "Alias-Maker-x86_64.AppImage"
        appimage.write_text("")
        with mock.patch.dict(os.environ, {"APPIMAGE": str(appimage)}):
            doit.save_custom_command("checkdrives", "lsblk -f", False)
        self.assertIn(f"{doit.fish_quote(str(appimage))} 'doit' --alias 'checkdrives' -- $argv",
                      self.shortcuts())

    def test_the_file_is_made_and_kept_in_step(self):
        doit.save_custom_command("checkdrives", "lsblk -f", False)
        doit.save_custom_command("check drives", "lsblk", False)
        text = self.shortcuts()
        self.assertTrue(text.startswith("# Made by Alias Maker. Don't edit this file by hand"))
        self.assertIn("function checkdrives --description 'Alias Maker: lsblk -f'", text)
        self.assertIn(f"{doit.fish_quote(str(doit.doit_path()))} --alias 'checkdrives' -- $argv", text)
        self.assertFalse(any("check drives" in line for line in text.splitlines()
                             if line.startswith("function")), "names with spaces get no shortcut")
        doit.update_custom_command("checkdrives", "drives", "lsblk -f", False)
        self.assertIn("function drives ", self.shortcuts())
        self.assertNotIn("function checkdrives ", self.shortcuts())
        doit.remove_custom_command("drives")
        self.assertNotIn("function drives ", self.shortcuts())
        self.assertTrue(self.shortcuts().startswith("# Made by Alias Maker."))

    def test_taken_names_only_work_with_doit(self):
        make_program(self.programs, "lsblk")
        fake_cachyos = self.home / "cachyos-config.fish"
        fake_cachyos.write_text("alias update='sudo cachyos-rate-mirrors && sudo pacman -Syu'\nfunction backup --argument f\nend\n")
        saved = doit.CACHYOS_FISH_CONFIG
        doit.CACHYOS_FISH_CONFIG = str(fake_cachyos)
        try:
            for name, why in (("lsblk", "a program on your PC"), ("cd", "a built-in fish command"),
                              ("update", "a shortcut in your fish setup"), ("backup", "a shortcut in your fish setup")):
                problem = doit.shell_name_problem(name)
                self.assertEqual(problem[0], "taken", name)
                self.assertIn(why, problem[1])
                doit.save_custom_command(name, "true", False)
                self.assertNotIn(f"function {name} ", self.shortcuts())
            _, out, _ = self.run_doit(["create"], answers=["true", "update2"])
            self.assertIn("type it on its own: update2", out)
            doit.remove_custom_command("update")
            _, out, _ = self.run_doit(["create"], answers=["true", "update", "no", "yes"])
            self.assertIn('"update" is already a shortcut in your fish setup', out)
            self.assertIn('work as "doit update" only', out)
        finally:
            doit.CACHYOS_FISH_CONFIG = saved

    def test_users_own_fish_functions_are_respected(self):
        functions = self.home / "config" / "fish" / "functions"
        functions.mkdir(parents=True)
        (functions / "mine.fish").write_text("function mine\nend\n")
        self.assertEqual(doit.shell_name_problem("mine")[0], "taken")

    def test_shortcut_runs_through_doit_with_extra_words(self):
        doit.save_custom_command("checkdrives", "lsblk -f", False)
        code, out, _ = self.run_doit(["--dry-run", "--alias", "checkdrives", "--", "/dev/sda", "it's"],
                                     answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("Real command: lsblk -f", out)
        self.assertIn("""[dry run] Would run: lsblk -f /dev/sda 'it'"'"'s'""", out)

    def test_shortcut_for_a_deleted_command(self):
        code, out, _ = self.run_doit(["--alias", "gone", "--"], tty=False)
        self.assertEqual(code, 127)
        self.assertIn("doesn't have a command called", out)

    def test_shortcut_file_lists_its_names_for_live_reload(self):
        doit.save_custom_command("check-drives", "lsblk -f", False)
        doit.save_custom_command("doit thing", "ls", False)  # has a space: not a shortcut
        text = doit.fish_shortcuts_path().read_text()
        self.assertIn("set -g __aliasmaker_shortcut_names 'check-drives'\n", text)

    def test_create_says_where_the_shortcut_works(self):
        os.environ["ALIASMAKER"], os.environ["SHELL"] = "1", "/usr/bin/fish"
        self.assertIn("works right away", doit.where_shortcuts_work())
        os.environ.pop("ALIASMAKER")
        self.assertEqual(doit.where_shortcuts_work(), "(in a new terminal window)")

    def test_name_suggestions(self):
        self.assertEqual(doit.name_suggestions("just check my fucking drives"),
                         ("check drives", "check-drives", "just-check-my-fucking-drives"))
        self.assertEqual(doit.name_suggestions("check drives"), (None, None, "check-drives"))
        self.assertEqual(doit.name_suggestions("Check My Drives!"),
                         ("check drives", "check-drives", "check-my-drives"))



FISH = os.environ.get("ALIASMAKER_TEST_FISH") or __import__("shutil").which("fish")
SHELL_SCRIPT = Path(__file__).resolve().parent.parent / "src" / "shell" / "lets-do-stuff.fish"


@unittest.skipUnless(FISH, "fish isn't installed")
class TestFishSetup(DoitTestCase):
    """Runs the real fish with the Alias Maker window's setup script."""

    def fish(self, script):
        import subprocess
        env = dict(os.environ, PATH=os.pathsep.join([str(self.programs), "/usr/bin", "/bin"]))
        result = subprocess.run([FISH, "--no-config", "-c", f"source '{SHELL_SCRIPT}'\n{script}"],
                                capture_output=True, text=True, env=env, timeout=30)
        return result.stdout

    def save(self, name, command):
        return (f"python3 -c \"import sys; sys.path.insert(0, '{SHELL_SCRIPT.parent.parent}'); "
                f"import aliasmaker_core as c; c.save_custom_command('{name}', '{command}', False)\"")

    def test_new_commands_work_without_a_new_window(self):
        out = self.fish("\n".join([
            "emit fish_prompt",
            "functions -q check-drives; and echo before:yes; or echo before:no",
            self.save("check-drives", "lsblk -f"),
            "emit fish_prompt",
            "functions -q check-drives; and echo after:yes; or echo after:no",
        ]))
        self.assertIn("before:no", out)
        self.assertIn("after:yes", out)

    def test_deleted_commands_go_away(self):
        doit.save_custom_command("check-drives", "lsblk -f", False)
        out = self.fish("\n".join([
            f"source '{doit.fish_shortcuts_path()}'",
            "set -g __aliasmaker_shortcuts_text (string collect < " + f"'{doit.fish_shortcuts_path()}')",
            "python3 -c \"import sys; sys.path.insert(0, '" + str(SHELL_SCRIPT.parent.parent)
            + "'); import aliasmaker_core as c; c.remove_custom_command('check-drives')\"",
            "emit fish_prompt",
            "functions -q check-drives; and echo still:yes; or echo still:no",
        ]))
        self.assertIn("still:no", out)

    def test_clippy_is_an_abbreviation(self):
        out = self.fish("abbr --query __aliasmaker_clippy; and echo abbr:yes")
        self.assertIn("abbr:yes", out)


class TestWelcome(DoitTestCase):
    def setUp(self):
        super().setUp()  # the environment is put back after each test
        os.environ["ALIASMAKER"] = "1"  # as inside the Alias Maker window
        os.environ.pop("TERM_PROGRAM", None)

    def test_without_fastfetch_shows_doit_and_pc_info(self):
        os.environ["SHELL"] = "/usr/bin/fish"
        code, out, _ = self.run_doit(["--welcome"], tty=False)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("██████╗   ██████╗  ██╗ ████████╗"))
        for label in ("OS:", "Kernel:", "Shell: fish", "Terminal: aliasmaker", "Memory:", "Disk (/):"):
            self.assertIn(label, out)
        self.assertNotIn("\033[", out)  # no colors when not printing to a terminal
        self.assertNotIn("$1", out)

    def test_with_fastfetch_uses_it_with_the_doit_logo(self):
        make_program(self.programs, "fastfetch", 'printf "FASTFETCH %s\\n" "$*"')
        code, out, _ = self.run_doit(["--welcome"], tty=False)
        self.assertEqual(code, 0)
        self.assertIn(f"--logo {doit.logo_path()} --logo-type file --logo-color-1 96", out)
        self.assertIn(f"FASTFETCH --config {doit.data_dir() / 'fastfetch-welcome.jsonc'}", out)
        config = json.loads((doit.data_dir() / "fastfetch-welcome.jsonc").read_text())
        self.assertIn({"type": "terminal", "format": "aliasmaker"}, config["modules"])  # not "python3"

    def test_outside_alias_maker_it_does_not_claim_to_be_it(self):
        os.environ.pop("ALIASMAKER")
        _, out, _ = self.run_doit(["--welcome"], tty=False)
        self.assertNotIn("Terminal:", out)
        os.environ["TERM_PROGRAM"] = "konsole"
        _, out, _ = self.run_doit(["--welcome"], tty=False)
        self.assertIn("Terminal: konsole", out)

    def test_falls_back_if_fastfetch_fails(self):
        make_program(self.programs, "fastfetch", "exit 1")
        _, out, _ = self.run_doit(["--welcome"], tty=False)
        self.assertIn("Terminal: aliasmaker", out)

    def test_colors_in_a_terminal(self):
        text = doit.welcome_text(color=True)
        self.assertIn("\033[1;96m", text)


if __name__ == "__main__":
    unittest.main()
