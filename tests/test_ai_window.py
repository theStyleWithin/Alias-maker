"""The ☰ → AI window, driven for real on a (virtual) screen against a stand-in AI service.
Skipped when GTK or a display isn't there. Run with: xvfb-run -a python3.12 -m unittest tests.test_ai_window"""

import importlib.machinery
import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ai import AITestCase, CLAUDE_KEY, GROK_KEY, doit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
mod = None
if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
    try:
        loader = importlib.machinery.SourceFileLoader("aliasmaker_window", str(ROOT / "src" / "aliasmaker"))
        spec = importlib.util.spec_from_loader("aliasmaker_window", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    except (ImportError, ValueError, SystemExit):
        mod = None


class StubTerminal:
    def __init__(self):
        self.typed = []

    def type_into_terminal(self, text, run=False):
        self.typed.append((text, run))


class StubApp:
    def __init__(self):
        self.stub = StubTerminal()

    def terminal(self):
        return self.stub


@unittest.skipUnless(mod, "GTK or a display isn't available")
class TestAIWindow(AITestCase):
    def setUp(self):
        super().setUp()
        self.app = StubApp()
        self.win = mod.AIWindow(self.app)
        self.addCleanup(self.win.destroy)

    def spin(self, until=lambda: False, seconds=5):
        context = mod.GLib.MainContext.default()
        end = time.time() + seconds
        while time.time() < end:
            while context.pending():
                context.iteration(False)
            if until():
                return True
            time.sleep(0.02)
        return until()

    def check_with(self, key):
        self.win.key.set_text(key)
        self.win.check_key()
        self.assertTrue(self.spin(lambda: not self.win.checking), "the check finished")

    def test_it_starts_empty_and_off(self):
        self.assertFalse(self.win.switch.get_active())
        self.assertFalse(self.win.chat.get_sensitive())
        self.assertFalse(self.win.forget.get_sensitive())
        self.assertIn("add a key first", self.win.state.get_label())
        self.assertEqual(self.ai.requests, [], "opening the window sends nothing anywhere")

    def test_a_good_key_is_saved_and_turns_it_on(self):
        self.check_with(CLAUDE_KEY)
        config = doit.ai_load()
        self.assertEqual((config["provider"], config["key"], config["model"], config["enabled"]),
                         ("claude", CLAUDE_KEY, "claude-sonnet-5-5", True))
        self.assertEqual(self.win.service.get_label(), "Claude (Anthropic)")
        self.assertTrue(self.win.switch.get_active())
        self.assertTrue(self.win.chat.get_sensitive())
        self.assertEqual(self.win.models, self.ai.models)
        self.assertEqual(self.win.key.get_text(), "", "the key isn't left on screen")
        self.assertIn("The key works", self.win.message.get_label())

    def test_a_bad_key_is_explained_and_not_saved(self):
        self.ai.status = 401
        self.check_with(CLAUDE_KEY)
        self.assertIn("didn't accept that key", self.win.message.get_label())
        self.assertEqual(doit.ai_load(), {})
        self.assertNotIn(CLAUDE_KEY, self.win.message.get_label())

    def test_an_unknown_key_asks_which_service_before_checking(self):
        self.win.key.set_text("mystery-key-1")
        self.win.check_key()
        self.assertTrue(self.win.provider_pick.get_visible())
        self.assertEqual(self.ai.requests, [])
        self.win.provider_pick.set_selected(1)
        self.win.check_key()
        self.assertTrue(self.spin(lambda: not self.win.checking))
        self.assertEqual(doit.ai_load()["provider"], "grok")

    def test_a_grok_key_is_recognised(self):
        self.ai.models = ["grok-text"]
        self.check_with(GROK_KEY)
        self.assertEqual(doit.ai_load()["provider"], "grok")
        self.assertEqual(self.win.service.get_label(), "Grok (xAI)")

    def test_picking_another_model_is_saved(self):
        self.check_with(CLAUDE_KEY)
        self.win.model.set_selected(self.ai.models.index("claude-opus-5-5"))
        self.assertEqual(doit.ai_load()["model"], "claude-opus-5-5")

    def test_the_switch_needs_a_key_and_turns_it_off_and_on(self):
        self.win.switch.set_active(True)
        self.assertFalse(self.win.switch.get_active())
        self.assertIn("Add and check a key first", self.win.message.get_label())
        self.check_with(CLAUDE_KEY)
        self.win.switch.set_active(False)
        self.assertFalse(doit.ai_load()["enabled"])
        self.assertFalse(self.win.chat.get_sensitive())
        self.assertTrue(doit.ai_load()["key"], "turning it off keeps the key")
        self.win.switch.set_active(True)
        self.assertTrue(doit.ai_load()["enabled"])

    def test_the_chat_button_types_doit_ai_into_the_terminal(self):
        self.check_with(CLAUDE_KEY)
        self.win.chat.emit("clicked")
        self.assertEqual(self.app.stub.typed, [("doit ai", True)])

    def test_forgetting_the_key_takes_two_clicks(self):
        self.check_with(CLAUDE_KEY)
        self.win.forget.emit("clicked")
        self.assertTrue(doit.ai_path().exists())
        self.assertIn("Click again", self.win.forget.get_label())
        self.win.forget.emit("clicked")
        self.assertFalse(doit.ai_path().exists())
        self.assertFalse(self.win.switch.get_active())
        self.assertFalse(self.win.forget.get_sensitive())

    def test_reopening_shows_what_is_saved_without_the_key(self):
        self.check_with(CLAUDE_KEY)
        self.win.reload()
        self.assertEqual(self.win.key.get_text(), "")
        self.assertEqual(self.win.service.get_label(), "Claude (Anthropic)")
        self.assertTrue(self.win.switch.get_active())


if __name__ == "__main__":
    unittest.main()
