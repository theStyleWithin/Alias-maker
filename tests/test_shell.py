"""Tests for the PC's own shell: finding it, protecting its names, and the bash setup script
(src/shell/lets-do-stuff.bash) run in a real bash. Run with: python3 -m unittest discover -s tests"""

import os
import pty
import select
import shutil
import signal
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_doit import DoitTestCase, make_program, doit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
SETUP = ROOT / "src" / "shell" / "lets-do-stuff.bash"


class TestShellDetection(DoitTestCase):
    def test_the_shell_is_the_one_you_pick_or_the_account_has(self):
        os.environ["ALIASMAKER_SHELL"] = "/bin/sh"
        self.assertEqual(doit.login_shell(), "/bin/sh")
        self.assertEqual(doit.shell_kind(), "sh")
        os.environ["ALIASMAKER_SHELL"] = "/no/such/shell"
        self.assertTrue(os.access(doit.login_shell(), os.X_OK), "falls back to a real shell")

    def test_bash_names_are_protected(self):
        (self.home / ".bashrc").write_text("alias gs='git status'\nmyfunc() {\n  :\n}\nfunction other { :; }\n")
        for name in ("gs", "myfunc", "other"):
            self.assertEqual(doit.shell_name_problem(name), ("taken", "a shortcut in your shell setup"), name)
        self.assertEqual(doit.shell_name_problem("export"), ("taken", "a built-in bash command"))
        self.assertIsNone(doit.shell_name_problem("check-drives"))

    def test_the_bash_file_is_written_and_fish_only_where_fish_is(self):
        (self.home / "config" / "fish").rmdir()  # no fish on this PC
        doit.save_custom_command("sayhi", "echo hi", False)
        text = doit.bash_shortcuts_path().read_text()
        self.assertIn("sayhi() {", text)
        self.assertIn("--alias sayhi --", text)
        self.assertFalse(doit.fish_shortcuts_path().exists(), "no fish folders made on a PC without fish")
        (self.home / "config" / "fish").mkdir()
        doit.save_custom_command("sayhi", "echo hi", False)
        self.assertTrue(doit.fish_shortcuts_path().exists())


@unittest.skipUnless(BASH, "bash isn't installed")
class TestScanKnowsTheShell(DoitTestCase):
    def test_the_scan_records_the_shell_and_lists_its_own_commands(self):
        os.environ["ALIASMAKER_SHELL"] = BASH
        make_program(self.programs, "lsblk")
        library = doit.scan_library()
        self.assertEqual(library["shell"]["name"], "bash")
        rows = {p["name"]: p for p in library["programs"]}
        self.assertEqual((rows["cd"]["package"], rows["cd"]["path"]), ("bash", "(built into bash)"))
        self.assertIn("working directory", rows["cd"]["description"])
        self.assertIn("lsblk", rows)

    def test_a_program_keeps_its_row_when_the_shell_has_a_command_of_the_same_name(self):
        os.environ["ALIASMAKER_SHELL"] = BASH
        make_program(self.programs, "echo")
        rows = {p["name"]: p for p in doit.scan_library()["programs"]}
        self.assertEqual(rows["echo"]["path"], str(self.programs / "echo"))


class Bash:
    """A real interactive bash on a pseudo-terminal, started the way the window starts it."""

    def __init__(self, env, cwd):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(cwd)
            os.execve(BASH, [BASH, "--rcfile", str(SETUP), "-i"], env)
        self.seen = ""

    def wait_for(self, text, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if text in self.seen:
                return True
            ready, _, _ = select.select([self.fd], [], [], 0.2)
            if ready:
                try:
                    self.seen += os.read(self.fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    break
        return text in self.seen

    def wait_for_prompt(self, timeout=20):
        """Wait until bash has drawn its prompt and is reading keys (typing sooner is type-ahead, which
        the terminal handles differently)."""
        end = time.time() + timeout
        while time.time() < end:
            if self.seen.endswith("\u276f\x1b[0m "):
                return True
            ready, _, _ = select.select([self.fd], [], [], 0.1)
            if ready:
                try:
                    self.seen += os.read(self.fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    return False
        return False

    def run(self, line, expect, timeout=20):
        """Type a line and wait for what it should print. Returns what came back."""
        self.wait_for_prompt()
        start = len(self.seen)
        os.write(self.fd, (line + "\r").encode())
        self.wait_for_after(start, expect, timeout)
        return self.seen[start:]

    def wait_for_after(self, start, text, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if text in self.seen[start:]:
                return True
            ready, _, _ = select.select([self.fd], [], [], 0.2)
            if ready:
                try:
                    self.seen += os.read(self.fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    break
        return False

    def close(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
            os.waitpid(self.pid, 0)
        except OSError:
            pass
        os.close(self.fd)


@unittest.skipUnless(BASH, "bash isn't installed")
class TestBashSetup(DoitTestCase):
    def setUp(self):
        super().setUp()
        self.stub = self.home / "stub"
        self.stub.mkdir()
        (self.stub / "doit").write_text(
            '#!/bin/sh\ncase "$1" in\n  --not-found) echo "EXPLAINED: $*"; exit 1 ;;\n'
            '  clippy) echo "CLIPPY-LOOKUP: $*" ;;\n  *) echo "DOIT: $*" ;;\nesac\n')
        (self.stub / "doit").chmod(0o755)
        (self.home / ".bashrc").write_text(
            "PS1='(weird)$ '\nPROMPT_COMMAND='echo PC-RAN'\nalias ll='echo LONGLIST'\n"
            "myfn() { echo MYFN-RAN; }\nexport FROM_BASHRC=yes\n")
        doit.save_settings({"logging": False, "yes_words": ["y", "yes"]})
        doit.save_custom_command("sayhi", "echo hello-shortcut", False)
        self.bash_env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
                    "XDG_DATA_HOME": str(self.home / "data"), "TERM": "xterm", "LANG": "C.UTF-8",
                    "PATH": f"{self.stub}:/usr/bin:/bin", "DOIT_EXAMPLES": os.environ["DOIT_EXAMPLES"]}
        self.bash = Bash(self.bash_env, self.home)
        self.addCleanup(self.bash.close)
        self.assertTrue(self.bash.wait_for("Let'sdostuff~"), "the Let'sdostuff~ prompt shows up\n" + self.bash.seen)

    def test_the_prompt_and_title_say_letsdostuff_but_it_is_still_your_bash(self):
        seen = self.bash.seen
        self.assertIn("\x1b]0;Let'sdostuff~\x07", seen, "the window title")
        self.assertNotIn("(weird)", seen, "your own prompt is replaced inside Alias Maker only")
        self.assertIn("PC-RAN", seen, "your own PROMPT_COMMAND still runs")
        self.assertIn("MYFN-RAN", self.bash.run("myfn", "MYFN-RAN"))
        self.assertIn("LONGLIST", self.bash.run("ll", "LONGLIST"))
        self.assertIn("val=yes", self.bash.run("echo val=$FROM_BASHRC", "val=yes"))
        self.assertIn("v=1", self.bash.run("export V=1; echo v=$V", "v=1"))

    def test_clippy_is_a_slash_command_that_looks_a_topic_up(self):
        out = self.bash.run("/clippy chrooting", "CLIPPY-LOOKUP: clippy chrooting")
        self.assertIn("CLIPPY-LOOKUP: clippy chrooting", out)
        self.assertIn("DOIT: --version", self.bash.run("doit --version", "DOIT: --version"), "other lines are left alone")

    def test_ai_is_a_slash_command_too(self):
        out = self.bash.run("/ai how do I unzip", "DOIT: ai how do I unzip")
        self.assertIn("DOIT: ai how do I unzip", out)
        self.assertIn("DOIT: ai", self.bash.run("/ai", "DOIT: ai"))

    def test_swapai_is_a_slash_command_too(self):
        out = self.bash.run("/swapai some-model", "DOIT: swapai some-model")
        self.assertIn("DOIT: swapai some-model", out)

    def test_your_one_word_commands_work_even_one_made_while_the_prompt_waited(self):
        out = self.bash.run("sayhi", "hello-shortcut")
        self.assertIn("Real command: echo hello-shortcut", out)
        doit.save_custom_command("latecomer", "echo late-ok", False)
        self.assertIn("late-ok", self.bash.run("latecomer", "late-ok"))

    def test_an_unknown_command_gets_a_plain_explanation(self):
        out = self.bash.run("nosuchcmd-xyz", "EXPLAINED: --not-found nosuchcmd-xyz")
        self.assertIn("EXPLAINED: --not-found nosuchcmd-xyz", out)


@unittest.skipUnless(BASH, "bash isn't installed")
class TestBashTypoHelper(DoitTestCase):
    """The real doit, called by the real bash setup: a mistyped command offers close programs."""

    def setUp(self):
        super().setUp()
        self.tools = self.home / "tools"
        self.tools.mkdir()
        (self.tools / "doit").symlink_to(ROOT / "src" / "doit")
        make_program(self.tools, "zzprog-demo", 'echo "ZZ-RAN $*"')
        doit.save_settings({"logging": False, "yes_words": ["y", "yes"]})
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
               "XDG_DATA_HOME": str(self.home / "data"), "TERM": "xterm", "LANG": "C.UTF-8",
               "PATH": f"{self.tools}:/usr/bin:/bin", "DOIT_EXAMPLES": os.environ["DOIT_EXAMPLES"],
               "ALIASMAKER_OS_RELEASE": os.environ.get("ALIASMAKER_OS_RELEASE", "/etc/os-release")}
        self.bash = Bash(env, self.home)
        self.addCleanup(self.bash.close)
        self.assertTrue(self.bash.wait_for("Let'sdostuff~"), self.bash.seen)

    def test_a_typo_offers_the_real_program_and_a_number_runs_it(self):
        out = self.bash.run("zzprog-dmo --hi", "1-")
        self.assertIn("This looks like a typo. Did you mean:", out)
        self.assertIn("1) zzprog-demo", out)
        self.assertNotIn("ZZ-RAN", out, "nothing runs until a number is typed")
        out = self.bash.run("1", "ZZ-RAN --hi")
        self.assertIn("Running: zzprog-demo --hi", out)
        self.assertIn("ZZ-RAN --hi", out)

    def test_enter_skips_and_nothing_runs(self):
        self.bash.run("zzprog-dmo", "1-")
        out = self.bash.run("", "not running anything")
        self.assertIn("not running anything", out)
        self.assertNotIn("ZZ-RAN", out)

    @unittest.skipIf(shutil.which("zypper"), "this PC really has zypper, so it would not be 'another Linux'")
    def test_a_command_from_another_linux_gets_this_systems_version(self):
        # zypper (openSUSE) typed on a pretend Arch: the real one must never be found and run
        osr = self.home / "os-release"
        osr.write_text('ID=arch\nPRETTY_NAME="Arch test"\n')
        make_program(self.tools, "pacman", "true")
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
               "XDG_DATA_HOME": str(self.home / "data"), "TERM": "xterm", "LANG": "C.UTF-8",
               "PATH": f"{self.tools}:/usr/bin:/bin", "DOIT_EXAMPLES": os.environ["DOIT_EXAMPLES"],
               "ALIASMAKER_OS_RELEASE": str(osr)}
        bash = Bash(env, self.home)
        self.addCleanup(bash.close)
        self.assertTrue(bash.wait_for("Let'sdostuff~"), bash.seen)
        out = bash.run("zypper install gimp", "1)")
        self.assertIn("is for openSUSE", out)
        self.assertIn("1) sudo pacman -S gimp", out)
        out = bash.run("", "not running anything")
        self.assertIn("not running anything", out)


if __name__ == "__main__":
    unittest.main()
