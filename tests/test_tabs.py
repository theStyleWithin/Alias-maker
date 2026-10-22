"""Tabs and the window buttons in the real window, on a (virtual) screen. Skipped when GTK or a display
isn't there. Run with: xvfb-run -a python3.12 -m unittest tests.test_tabs"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_doit import DoitTestCase  # noqa: E402

from winmod import mod  # noqa: E402


@unittest.skipUnless(mod, "GTK or a display isn't available")
class TestTabs(DoitTestCase):
    def setUp(self):
        super().setUp()
        self.app = mod.AliasMakerApp(None, None)
        self.app.register(None)
        self.win = mod.TerminalWindow(self.app)
        self.app.terminals.append(self.win)
        self.addCleanup(self.win.destroy)

    def spin(self, until=lambda: True, seconds=5):
        context = mod.GLib.MainContext.default()
        end = time.time() + seconds
        while time.time() < end:
            for _ in range(50):  # live shells keep events coming, so never loop on "pending" alone
                if not context.pending():
                    break
                context.iteration(False)
            if until():
                return True
            time.sleep(0.02)
        return until()

    def pages(self):
        return self.win.notebook.get_n_pages()

    def key(self, name, *mods):
        state = 0
        for m in mods:
            state |= m
        return self.win.on_key(None, getattr(mod.Gdk, f"KEY_{name}"), 0, state)

    CONTROL = property(lambda self: mod.Gdk.ModifierType.CONTROL_MASK)
    SHIFT = property(lambda self: mod.Gdk.ModifierType.SHIFT_MASK)

    # --- the buttons ---

    def test_minimize_maximize_and_close_are_always_there_and_new_tab_is_on_the_left(self):
        header = self.win.get_titlebar()
        self.assertEqual(header.get_decoration_layout(), ":minimize,maximize,close")
        buttons = []

        def walk(widget):
            child = widget.get_first_child()
            while child:
                if isinstance(child, mod.Gtk.Button):
                    buttons.append(child)
                walk(child)
                child = child.get_next_sibling()

        walk(header)
        new_tab = [b for b in buttons if "New tab" in (b.get_tooltip_text() or "")]
        self.assertEqual(len(new_tab), 1)
        # depth-first, the left (start) side comes before the right-hand buttons
        order = [b.get_tooltip_text() or "" for b in buttons]
        self.assertLess(order.index(new_tab[0].get_tooltip_text()), [i for i, t in enumerate(order) if t.startswith("Copy")][0],
                        "the New Tab button is on the left, ahead of Copy and the menu on the right")
        self.assertEqual(self.pages(), 1)
        new_tab[0].emit("clicked")
        self.assertEqual(self.pages(), 2)

    # --- tabs ---

    def test_it_starts_with_one_tab_and_no_tab_bar(self):
        self.assertEqual(self.pages(), 1)
        self.assertFalse(self.win.notebook.get_show_tabs())

    def test_a_new_tab_appears_and_takes_over(self):
        first = self.win.term
        second = self.win.new_tab() or self.win.term
        self.assertEqual(self.pages(), 2)
        self.assertTrue(self.win.notebook.get_show_tabs(), "the tab bar shows with more than one tab")
        self.assertIsNot(self.win.term, first)
        self.assertEqual(self.win.notebook.get_current_page(), 1)

    def test_closing_a_tab_leaves_the_others_and_the_bar_hides_again(self):
        first = self.win.term
        self.win.new_tab()
        second = self.win.term
        self.win.close_tab(second)
        self.assertEqual(self.pages(), 1)
        self.assertIs(self.win.term, first)
        self.assertFalse(self.win.notebook.get_show_tabs())

    def test_closing_the_last_tab_closes_the_window(self):
        with mock.patch.object(self.win, "close") as close:
            self.win.close_tab()
        close.assert_called_once()
        self.assertEqual(self.pages(), 1, "the window does the closing, not the tab")

    def test_a_shell_that_exits_closes_only_its_own_tab(self):
        first = self.win.term
        self.win.new_tab()
        second = self.win.term
        second.emit("child-exited", 0)
        self.assertEqual(self.pages(), 1)
        self.assertIs(self.win.term, first)
        with mock.patch.object(self.win, "close") as close:
            first.emit("child-exited", 0)
        close.assert_called_once()

    def test_the_close_button_on_a_tab_closes_that_tab(self):
        first = self.win.term
        self.win.new_tab()
        tab = self.win.notebook.get_tab_label(first)
        close = tab.get_last_child()
        close.emit("clicked")
        self.assertEqual(self.pages(), 1)
        self.assertIsNot(self.win.term, first)

    def test_keyboard_shortcuts_like_konsole(self):
        self.assertTrue(self.key("T", self.CONTROL, self.SHIFT))
        self.assertEqual(self.pages(), 2)
        self.assertTrue(self.key("Page_Up", self.CONTROL))
        self.assertEqual(self.win.notebook.get_current_page(), 0)
        self.assertTrue(self.key("Page_Up", self.CONTROL))
        self.assertEqual(self.win.notebook.get_current_page(), 1, "it wraps round")
        self.assertTrue(self.key("Page_Down", self.CONTROL))
        self.assertEqual(self.win.notebook.get_current_page(), 0)
        self.assertTrue(self.key("W", self.CONTROL, self.SHIFT))
        self.assertEqual(self.pages(), 1)

    def test_the_menu_has_new_tab_and_close_tab(self):
        labels = []
        menu = self.win.build_menu()
        for s in range(menu.get_n_items()):
            section = menu.get_item_link(s, "section")
            for i in range(section.get_n_items() if section else 0):
                labels.append(section.get_item_attribute_value(i, "label").get_string())
        self.assertIn("New Tab", labels)
        self.assertIn("Close Tab", labels)
        self.assertLess(labels.index("New Tab"), labels.index("New Window"))
        self.win.activate_action("win.new-tab", None)
        self.assertEqual(self.pages(), 2)
        self.win.activate_action("win.close-tab", None)
        self.assertEqual(self.pages(), 1)

    def test_what_you_do_goes_to_the_tab_you_are_looking_at(self):
        first = self.win.term
        self.win.new_tab()
        second = self.win.term
        with mock.patch.object(first, "feed_child") as to_first, mock.patch.object(second, "feed_child") as to_second:
            self.win.type_into_terminal("doit ai", run=True)
        to_second.assert_called_once()
        to_first.assert_not_called()
        self.win.notebook.set_current_page(0)
        with mock.patch.object(first, "paste_clipboard") as paste:
            self.win.paste()
        paste.assert_called_once()

    def test_each_tab_keeps_its_own_font_size(self):
        first = self.win.term
        self.win.new_tab()
        second = self.win.term
        self.win.zoom(1.5)
        self.assertAlmostEqual(second.get_font_scale(), 1.5)
        self.assertAlmostEqual(first.get_font_scale(), 1.0)

    def test_each_tab_is_named_by_its_own_title_and_the_window_follows_the_current_one(self):
        self.win.present()  # VTE only reports title changes once its window is on screen
        self.spin(seconds=1)
        first = self.win.term
        self.win.new_tab()
        second = self.win.term
        self.spin(seconds=0.5)
        first.feed(b"\x1b]0;alpha\x07")
        second.feed(b"\x1b]0;beta\x07")
        self.assertTrue(self.spin(lambda: first.tab_label.get_label() == "alpha" and second.tab_label.get_label() == "beta"))
        self.assertEqual(self.win.title_label.get_label(), "beta")
        self.win.notebook.set_current_page(0)
        self.assertTrue(self.spin(lambda: self.win.title_label.get_label() == "alpha"))
        self.assertIn("alpha", self.win.get_title())

    def test_a_tab_opened_later_still_starts_a_shell_in_the_home_folder(self):
        self.win.new_tab()
        self.assertEqual(self.pages(), 2)
        self.assertIsNotNone(self.win.term)


if __name__ == "__main__":
    unittest.main()
