"""Tests for the crash recorder and Alias Maker Debug. Run with: python3 -m unittest discover -s tests"""

import getpass
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import aliasmaker_crash as crash  # noqa: E402


class CrashTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        (self.home / "Downloads").mkdir()
        self.env_vars = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"),
                         "XDG_DATA_HOME": str(self.home / "data")}
        self.env = mock.patch.dict(os.environ, self.env_vars)
        self.env.start()
        crash._steps.clear()
        crash._typed = None

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_script(self, *args, code=None):
        argv = [sys.executable] + (["-c", code] if code else list(args))
        env = dict(os.environ, **self.env_vars)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        return subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60)

    def save_custom(self, commands):
        path = self.home / "config" / "alias-maker" / "custom.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "commands": commands}))


class TestScrub(CrashTestCase):
    def test_hides_private_details(self):
        text = (f"{self.home}/notes.txt by {getpass.getuser()} on {socket.gethostname()} "
                "mail jane.doe@example.com from 192.168.1.20 mac aa:bb:cc:dd:ee:ff "
                "password=hunter2 sudo --password s3cret token: abc123 "
                "https://bob:pw@example.com/x /home/alice/file /run/media/alice/HDD "
                "ghp_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5")
        clean = crash.scrub(text)
        for secret in ("hunter2", "s3cret", "abc123", "jane.doe", "192.168.1.20", "aa:bb:cc",
                       "bob:pw", "alice", "ghp_aB3d", str(self.home)):
            self.assertNotIn(secret, clean)
        self.assertIn("~/notes.txt", clean)
        self.assertIn("<email>", clean)

    def test_keeps_useful_details(self):
        text = ('File "/usr/lib/python3.13/site-packages/gi/overrides/Gtk.py", line 12 '
                "GTK 4.18.5 at 127.0.0.1")
        self.assertEqual(crash.scrub(text), text)

    def test_hides_custom_commands_and_typed_words(self):
        self.save_custom([{"phrase": "open my secret diary", "command": "xdg-open ~/diary.txt"},
                          {"phrase": "top", "command": "htop"}])
        crash._typed = ["call", "grandma", "now"]
        clean = crash.scrub("ran open my secret diary: xdg-open ~/diary.txt; KeyError: 'grandma' htop")
        self.assertNotIn("secret diary", clean)
        self.assertNotIn("diary.txt", clean)
        self.assertNotIn("grandma", clean)
        self.assertIn("htop", clean)  # a bare program name isn't private

    def test_scrub_twice_is_the_same(self):
        once = crash.scrub("password=x jane@example.com")
        self.assertEqual(crash.scrub(once), once)


class TestReports(CrashTestCase):
    def test_doit_test_crash_saves_a_report(self):
        done = self.run_script(str(SRC / "doit"), "--test-crash")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Test crash done", done.stderr)
        self.assertNotIn("Traceback", done.stderr)  # beginners see a sentence, not a traceback
        reports = crash.list_reports()
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text()
        self.assertIn("Kind: Test report", text)
        self.assertIn("Privacy:", text)
        self.assertIn(f"Alias Maker {crash.app_version()} (doit)", text)

    def test_error_report_hides_what_was_typed(self):
        code = ("import sys; sys.path.insert(0, %r); import aliasmaker_crash as c; "
                "c.install('doit', typed=['open', 'bankaccount']); "
                "c.note('menu: database'); raise ValueError('no bankaccount here')" % str(SRC))
        done = self.run_script(code=code)
        self.assertIn("saved a crash report", done.stderr)
        text = crash.list_reports()[0].read_text()
        self.assertNotIn("bankaccount", text)
        self.assertIn("ValueError", text)
        self.assertIn("menu: database", text)

    def test_sudden_crash_becomes_a_report_next_time(self):
        code = ("import sys, ctypes; sys.path.insert(0, %r); import aliasmaker_crash as c; "
                "c.install('window', sudden_crashes=True); c.note('menu: custom-list'); "
                "ctypes.string_at(0)" % str(SRC))
        done = self.run_script(code=code)
        self.assertLess(done.returncode, 0)  # killed by a signal
        self.assertEqual(crash.list_reports(), [])  # not until the next start
        made = crash.collect_sudden_crashes()
        self.assertEqual(len(made), 1)
        text = made[0].read_text()
        self.assertIn("Kind: Crash", text)
        self.assertIn("Segmentation fault", text)
        self.assertIn("menu: custom-list", text)
        self.assertEqual(list(crash.crash_dir().glob(".running-*")), [])

    def test_clean_exit_leaves_nothing(self):
        code = ("import sys; sys.path.insert(0, %r); import aliasmaker_crash as c; "
                "c.install('window', sudden_crashes=True)" % str(SRC))
        self.assertEqual(self.run_script(code=code).returncode, 0)
        self.assertEqual(crash.collect_sudden_crashes(), [])
        self.assertEqual(list(crash.crash_dir().iterdir()), [])

    def test_ctrl_c_is_not_a_crash(self):
        code = ("import sys; sys.path.insert(0, %r); import aliasmaker_crash as c; "
                "c.install('doit'); raise KeyboardInterrupt" % str(SRC))
        self.run_script(code=code)
        self.assertEqual(crash.list_reports(), [])

    def test_unseen_count_and_old_reports_trimmed(self):
        for _ in range(3):
            crash.save_report("x", "error")
        self.assertEqual(crash.unseen_count(), 3)
        crash.mark_seen()
        self.assertEqual(crash.unseen_count(), 0)
        with mock.patch.object(crash, "MAX_REPORTS", 2):
            crash.save_report("y", "error")
        self.assertEqual(len(crash.list_reports()), 2)


class TestDebugApp(CrashTestCase):
    def test_health_check_and_save_all(self):
        self.run_script(str(SRC / "doit"), "--test-crash")
        results = crash.health_check()
        names = [what for _status, what, _detail in results]
        for expected in ("Alias Maker version", "Python", "doit command", "Crash reports"):
            self.assertIn(expected, names)
        done = self.run_script(str(SRC / "aliasmaker-debug"), "--save-all")
        self.assertIn("Saved: ~/Downloads/alias-maker-debug-", done.stdout)
        saved = next((self.home / "Downloads").glob("alias-maker-debug-*.txt")).read_text()
        self.assertIn("health check", saved)
        self.assertIn("Kind: Test report", saved)
        self.assertNotIn(str(self.home), saved)

    def test_text_mode_without_a_desktop(self):
        env = dict(os.environ, **self.env_vars)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        done = subprocess.run([sys.executable, str(SRC / "aliasmaker-debug")], input="4\n1\n1\nq\n",
                              capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(done.returncode, 0)
        self.assertIn("text mode", done.stdout)
        self.assertIn("Test report", done.stdout)

    def test_report_corrupt_custom_file_in_health_check(self):
        path = self.home / "config" / "alias-maker" / "custom.json"
        path.parent.mkdir(parents=True)
        path.write_text("{ not json")
        status = {what: s for s, what, _d in crash.health_check()}
        self.assertEqual(status["Your custom commands"], crash.BAD)


if __name__ == "__main__":
    unittest.main()
