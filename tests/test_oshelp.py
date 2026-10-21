"""The typo helper knows which system this is: a command from another Linux (apt on Arch, pacman on
Ubuntu, ifconfig on a system without it) gets this PC's version, offered by number, never run unasked."""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_doit import DoitTestCase, make_program, doit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class OSHelpCase(DoitTestCase):
    def setUp(self):
        super().setUp()
        (self.home / "examples.json").write_text((ROOT / "data" / "examples.json").read_text())
        os.environ["DOIT_EXAMPLES"] = str(self.home / "examples.json")
        self.log = self.home / "ran.txt"
        make_program(self.programs, "sudo", 'exec "$@"')

    def system(self, os_id, like, *programs):
        path = self.home / "os-release"
        path.write_text(f'ID={os_id}\nID_LIKE="{like}"\nPRETTY_NAME="{os_id} test system"\n')
        os.environ["ALIASMAKER_OS_RELEASE"] = str(path)
        for name in programs:
            make_program(self.programs, name, f'echo "{name} $*" >> "{self.log}"')

    def ran(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def not_found(self, *words, answers=(), tty=True, dry=False):
        args = (["--dry-run"] if dry else []) + ["--not-found", *words]
        return self.run_doit(args, answers=list(answers), tty=tty)


class TestParsing(OSHelpCase):
    def test_what_a_package_command_asked_for(self):
        cases = {
            ("apt", "install", "gimp"): ("apt", "install", ["gimp"]),
            ("apt", "install", "-y", "gimp", "vlc"): ("apt", "install", ["gimp", "vlc"]),
            ("apt-get", "remove", "gimp"): ("apt-get", "remove", ["gimp"]),
            ("apt", "purge", "gimp"): ("apt", "remove", ["gimp"]),
            ("apt", "search", "firefox"): ("apt", "search", ["firefox"]),
            ("apt", "update"): ("apt", "upgrade", []),
            ("apt", "full-upgrade"): ("apt", "upgrade", []),
            ("pacman", "-S", "gimp"): ("pacman", "install", ["gimp"]),
            ("pacman", "-Syu"): ("pacman", "upgrade", []),
            ("pacman", "-Ss", "firefox"): ("pacman", "search", ["firefox"]),
            ("pacman", "-Rns", "gimp"): ("pacman", "remove", ["gimp"]),
            ("dnf", "install", "gimp"): ("dnf", "install", ["gimp"]),
            ("yum", "erase", "gimp"): ("yum", "remove", ["gimp"]),
            ("dnf", "upgrade"): ("dnf", "upgrade", []),
            ("zypper", "in", "gimp"): ("zypper", "install", ["gimp"]),
            ("zypper", "dup"): ("zypper", "upgrade", []),
            ("apt",): ("apt", None, []),
            ("apt", "install"): ("apt", None, []),
            ("pacman", "-Q"): ("pacman", None, []),
            ("apt", "install", "gimp;rm"): ("apt", None, []),
            ("apt", "install", "$(evil)"): ("apt", None, []),
        }
        for words, expect in cases.items():
            self.assertEqual(doit.parse_package_command(list(words)), expect, words)


class TestOtherLinuxCommands(OSHelpCase):
    def test_pacman_on_ubuntu_becomes_apt(self):
        self.system("ubuntu", "debian", "apt")
        code, out, prompts = self.not_found("pacman", "-S", "gimp", answers=["1", "yes"])
        self.assertEqual(code, 0)
        self.assertIn("is for Arch Linux and the systems built on it", out)
        self.assertIn("ubuntu test system, which uses apt", out)
        self.assertIn("1) sudo apt install gimp", out)
        self.assertIn("Running: sudo apt install gimp", out)
        self.assertEqual(self.ran(), ["apt install gimp"])
        self.assertTrue(prompts[1].startswith("This one changes software"))

    def test_nothing_runs_without_the_number_and_a_yes(self):
        self.system("ubuntu", "debian", "apt")
        for answers in ([""], ["n"], ["9"], ["1", "no"], ["1", ""]):
            self.not_found("pacman", "-S", "gimp", answers=answers)
        self.assertEqual(self.ran(), [])

    def test_searching_needs_no_yes(self):
        self.system("ubuntu", "debian", "apt")
        _, out, prompts = self.not_found("pacman", "-Ss", "firefox", answers=["1"])
        self.assertEqual(self.ran(), ["apt search firefox"])
        self.assertEqual(len(prompts), 1)

    def test_removing_and_each_systems_own_tool(self):
        cases = (("ubuntu", "debian", "apt", ["pacman", "-Rns", "foo"], "sudo apt remove foo"),
                 ("fedora", "", "dnf", ["apt", "install", "foo"], "sudo dnf install foo"),
                 ("opensuse-leap", "opensuse suse", "zypper", ["apt", "install", "foo"], "sudo zypper install foo"),
                 ("manjaro", "arch", "pacman", ["apt", "install", "foo"], "sudo pacman -S foo"),
                 ("cachyos", "arch", "pacman", ["yum", "install", "foo"], "sudo pacman -S foo"),
                 ("linuxmint", "ubuntu debian", "apt", ["dnf", "remove", "foo"], "sudo apt remove foo"))
        for os_id, like, tool, words, expect in cases:
            self.system(os_id, like, tool)
            _, out, _ = self.not_found(*words, answers=[""])
            self.assertIn(f"1) {expect}", out, os_id)
            os.remove(self.programs / tool)

    def test_updating_uses_this_systems_own_update_command(self):
        self.system("cachyos", "arch", "pacman")
        make_program(self.programs, "sh", 'exec /bin/sh "$@"')  # the test PATH has only fake programs
        _, out, _ = self.not_found("apt", "update", answers=["1", "yes"])
        self.assertIn("archlinux-keyring", out, "the same update command Alias Maker offers for this system")
        self.assertTrue(self.ran() and self.ran()[0].startswith("pacman -Sy --needed archlinux-keyring"))

    def test_a_typo_in_the_other_systems_name_is_understood_too(self):
        self.system("cachyos", "arch", "pacman")
        _, out, _ = self.not_found("aptt", "install", "gimp", answers=[""])
        self.assertIn("1) sudo pacman -S gimp", out)

    def test_without_a_clear_request_it_only_explains(self):
        self.system("ubuntu", "debian", "apt")
        _, out, prompts = self.not_found("pacman", answers=[])
        self.assertIn("uses apt.", out)
        self.assertNotIn("1)", out)
        self.assertEqual(prompts, [])

    def test_odd_package_names_never_reach_a_command(self):
        self.system("ubuntu", "debian", "apt")
        _, out, _ = self.not_found("pacman", "-S", "gimp;touch-evil", "$(x)", answers=[])
        self.assertNotIn("1)", out)
        self.assertEqual(self.ran(), [])

    def test_the_own_tools_typo_is_a_normal_typo_not_another_systems_command(self):
        self.system("ubuntu", "debian", "apt")
        _, out, _ = self.not_found("aptt", "install", "gimp", answers=[""])
        self.assertIn("This looks like a typo. Did you mean:", out)
        self.assertIn("1) apt", out)
        self.assertNotIn("is for", out)
        self.system("cachyos", "arch", "pacman")
        _, out, _ = self.not_found("pacmna", "-S", "gimp", answers=[""])
        self.assertIn("1) pacman", out)

    def test_without_a_terminal_it_only_tells_you(self):
        self.system("ubuntu", "debian", "apt")
        code, out, prompts = self.not_found("pacman", "-S", "gimp", tty=False)
        self.assertEqual(code, 1)
        self.assertEqual(prompts, [])
        self.assertIn("1) sudo apt install gimp", out)
        self.assertEqual(self.ran(), [])

    def test_dry_run_shows_but_does_not_run(self):
        self.system("ubuntu", "debian", "apt")
        _, out, _ = self.not_found("pacman", "-S", "gimp", answers=["1"], dry=True)
        self.assertIn("[dry run] Would run: sudo apt install gimp", out)
        self.assertEqual(self.ran(), [])

    def test_logged_only_when_logging_is_on(self):
        self.system("ubuntu", "debian", "apt")
        self.not_found("pacman", "-Ss", "x", answers=["1"])
        self.assertEqual(self.log_lines(), [])
        doit.save_settings({"logging": True, "yes_words": ["y", "yes"]})
        self.not_found("pacman", "-Ss", "x", answers=["1"])
        self.assertIn("other-system command: pacman", self.log_lines()[0])

    def test_old_command_names_point_to_their_replacements(self):
        self.system("arch", "", "ip")
        _, out, _ = self.not_found("ifconfig", answers=["1"])
        self.assertIn("isn't on this PC any more", out)
        self.assertIn("1) ip addr", out)
        self.assertEqual(self.ran(), ["ip addr"])
        self.system("arch", "", "ss")
        _, out, _ = self.not_found("netstat", answers=[""])
        self.assertIn("1) ss -tulpn", out)

    def test_an_old_name_without_its_replacement_is_the_plain_message(self):
        self.system("arch", "")
        _, out, _ = self.not_found("ifconfig", answers=[])
        self.assertIn("isn't a program on this PC", out)


class TestSteamOS(OSHelpCase):
    def test_installing_points_to_discover_and_flatpak_never_to_pacman(self):
        self.system("steamos", "arch", "pacman", "flatpak")
        _, out, _ = self.not_found("apt", "install", "gimp", answers=["1"])
        self.assertIn("not SteamOS", out)
        self.assertIn("Discover", out)
        self.assertIn("1) flatpak search gimp", out)
        self.assertNotIn("pacman -S", out)
        self.assertEqual(self.ran(), ["flatpak search gimp"])

    def test_updating_is_apps_only_and_asks(self):
        self.system("steamos", "arch", "pacman", "flatpak")
        _, out, prompts = self.not_found("apt", "update", answers=["1", "yes"])
        self.assertIn("1) flatpak update", out)
        self.assertEqual(self.ran(), ["flatpak update"])
        self.assertTrue(prompts[1].startswith("This one changes software"))

    def test_removing_and_a_missing_flatpak_only_explain(self):
        self.system("steamos", "arch", "pacman", "flatpak")
        _, out, prompts = self.not_found("apt", "remove", "gimp", answers=[])
        self.assertIn("Discover", out)
        self.assertNotIn("1)", out)
        self.assertEqual(prompts, [])
        os.remove(self.programs / "flatpak")
        _, out, _ = self.not_found("apt", "install", "gimp", answers=[])
        self.assertIn("Discover", out)
        self.assertNotIn("1)", out)

    def test_pacman_itself_is_just_a_command_there_not_a_foreign_one(self):
        self.system("steamos", "arch", "pacman")
        self.assertIsNone(doit.os_translation(doit.State([], doit.load_settings(), False), ["pacman", "-S", "x"]))


class TestRanking(OSHelpCase):
    def test_this_systems_own_tools_win_ties(self):
        self.system("ubuntu", "debian", "apt")
        make_program(self.programs, "apd", "true")
        make_program(self.programs, "ape", "true")
        state = doit.State([], doit.load_settings(), False)
        names = [n for n, _ in doit.typo_suggestions(state, "apr")]
        self.assertEqual(names[0], "apt")


if __name__ == "__main__":
    unittest.main()
