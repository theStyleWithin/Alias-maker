"""Loads the Alias Maker window module once per process for the window tests (GTK can't register its
row type twice). mod is None when there's no display or GTK isn't available."""

import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
mod = None
if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
    mod = sys.modules.get("aliasmaker_window_tests")
    if mod is None:
        try:
            loader = importlib.machinery.SourceFileLoader("aliasmaker_window_tests", str(ROOT / "src" / "aliasmaker"))
            spec = importlib.util.spec_from_loader("aliasmaker_window_tests", loader)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["aliasmaker_window_tests"] = mod
            loader.exec_module(mod)
        except (ImportError, ValueError, SystemExit):
            sys.modules.pop("aliasmaker_window_tests", None)
            mod = None
