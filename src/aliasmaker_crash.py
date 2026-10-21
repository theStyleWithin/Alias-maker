"""Alias Maker's crash recorder, shared by the window (aliasmaker), doit and Alias Maker Debug.

When something goes wrong, it saves a plain-text report on this PC, in
~/.local/share/alias-maker/crashes/. Nothing is ever sent anywhere: the tester
decides whether to share a report, and can read every word of it first.

What a report has: what went wrong (the error and where in Alias Maker's code),
the last few things done in the app (menu items opened, not what was typed),
and the PC's basics (Alias Maker version, OS, kernel, desktop, library versions).

What a report never has: anything typed or shown in the terminal. Before a
report is saved it's also scrubbed: the user name, PC name, home folder, email
addresses, IP addresses, password-like values, long tokens and the user's own
custom commands are replaced with <user>, <pc>, ~, <email>, <ip>, <hidden> and
<your command>.

Two kinds of failure are caught:
  Errors   a Python error. In the window, Alias Maker usually keeps running.
  Crashes  Alias Maker closed suddenly (for example a segmentation fault inside GTK
           or VTE). Python can't run code at that moment, so faulthandler writes the
           raw details to a "running" file; the next time Alias Maker or Alias Maker
           Debug starts, that file is turned into a normal, scrubbed report.

This module only uses Python's standard library, so it still works when GTK,
VTE or the rest of Alias Maker can't load.
"""

import faulthandler
import getpass
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

APP = "Alias Maker"
MAX_REPORTS = 50          # oldest reports are deleted past this
MAX_STEPS = 15            # how many recent actions a report lists
ISSUES_URL = "https://github.com/theStyleWithin/Alias-maker/issues/new"

KINDS = {
    "error": "Error (Alias Maker kept running)",
    "crash": "Crash (Alias Maker closed suddenly)",
    "startup": "Startup problem (Alias Maker couldn't open)",
    "test": "Test report (made on purpose to check the crash recorder)",
}

PRIVACY_NOTE = (
    "Privacy: nothing you typed or saw in the terminal is in this report. Your user name,\n"
    "PC name, home folder, email addresses, IP addresses, passwords, long tokens and your\n"
    "own custom commands were replaced with <user>, <pc>, ~, <email>, <ip>, <hidden> and\n"
    "<your command>. This report stays on your PC until you choose to share it."
)


class TestCrash(Exception):
    """Raised on purpose by `doit --test-crash`, to check that reports get saved."""


# ---------- where reports live ----------

def crash_dir():
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "alias-maker" / "crashes"


def custom_file():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "alias-maker" / "custom.json"


def app_version():
    """Read VERSION from aliasmaker_core.py without importing it (it may be what's broken)."""
    try:
        text = (Path(__file__).resolve().parent / "aliasmaker_core.py").read_text(errors="replace")
        found = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
        if found:
            return found.group(1)
    except OSError:
        pass
    return "unknown"


# ---------- scrubbing private details ----------

SECRET_KEY = re.compile(
    r"(?i)\b(password|passwd|passphrase|pass|pwd|token|secret|api[_-]?key|access[_-]?key|auth|"
    r"authorization|cookie|session)\b(\s*[=:]\s*|\s+(?=\S*\d))(\"[^\"]*\"|'[^']*'|\S+)")
SECRET_FLAG = re.compile(r"(?i)(--?(?:password|passwd|pass|token|secret|api[_-]?key|auth))(\s+)(\S+)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
URL_LOGIN = re.compile(r"(\w+://)[^/\s:@]+(:[^/\s@]*)?@")
IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){4,7}[0-9a-fA-F]{1,4}\b")
MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b")
COMMON_WORDS = {"the", "and", "for", "you", "with", "doit", "please", "what", "how", "this", "that"}
HOME_PATH = re.compile(r"/(home|Users|run/media|media|var/home)/[^/\s'\"]+")
LONG_TOKEN = re.compile(r"(?<![\w/.-])(?=[A-Za-z0-9_+=-]*\d)(?=[A-Za-z0-9_+=-]*[A-Za-z])[A-Za-z0-9_+=-]{28,}")


def private_words(typed=None):
    """Words to hide: user name, PC name, and the user's own commands (plus what they typed)."""
    words = {}
    try:
        user = getpass.getuser()
        if len(user) >= 2:
            words[user] = "<user>"
    except Exception:
        pass
    try:
        host = socket.gethostname()
        if len(host) >= 2 and host not in ("localhost",):
            words[host] = "<pc>"
            words[host.split(".")[0]] = "<pc>"
    except OSError:
        pass
    try:
        custom = json.loads(custom_file().read_text())
        for entry in custom.get("commands", []) if isinstance(custom, dict) else []:
            command = entry.get("command")
            if isinstance(command, str) and " " in command.strip():
                # a bare program name ("htop") isn't private; options and paths might be
                words.setdefault(command.strip(), "<your command>")
            phrase = entry.get("phrase")
            if isinstance(phrase, str):
                words.setdefault(phrase.strip(), "<your command>")
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    if typed:
        text = " ".join(typed).strip()
        if text:
            words.setdefault(text, "<what you typed>")
        for word in text.split():  # single words too: an error message may quote one
            if len(word) >= 3 and word.lower() not in COMMON_WORDS and not word.startswith("-"):
                words.setdefault(word, "<what you typed>")
    return {w: r for w, r in words.items() if len(w) >= 3 or r in ("<user>", "<pc>")}


def scrub(text, typed=None):
    """Replace private details in text. Safe to run more than once."""
    if not text:
        return text
    typed = _typed if typed is None else typed
    home = str(Path.home())
    if len(home) > 1:
        text = text.replace(home, "~")
    text = HOME_PATH.sub(lambda m: f"/{m.group(1)}/<user>", text)
    text = URL_LOGIN.sub(r"\1<hidden>@", text)
    text = EMAIL.sub("<email>", text)
    text = SECRET_FLAG.sub(lambda m: f"{m.group(1)}{m.group(2)}<hidden>", text)
    text = SECRET_KEY.sub(lambda m: f"{m.group(1)}{m.group(2)}<hidden>", text)
    text = MAC.sub("<mac>", text)
    text = IPV6.sub("<ip>", text)
    text = IPV4.sub(lambda m: m.group(0) if m.group(0).startswith(("0.", "127.")) else "<ip>", text)
    text = LONG_TOKEN.sub("<hidden>", text)
    for word, replacement in sorted(private_words(typed).items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", replacement, text)
    return text


# ---------- what the app was doing ----------

_part = "unknown"
_typed = None
_steps = []
_versions = {}
_lock = threading.Lock()
_running_file = None


def note(step):
    """Remember something the user did (a menu item, a window opening). Never pass typed text."""
    with _lock:
        _steps.append(f"{datetime.now():%H:%M:%S}  {step}")
        del _steps[:-MAX_STEPS]
        if _running_file is not None:
            try:
                steps_file(os.getpid()).write_text("\n".join(_steps) + "\n")
            except OSError:
                pass


def set_versions(**versions):
    """Record library versions (GTK, VTE, PyGObject) once they're loaded."""
    _versions.update({k: v for k, v in versions.items() if v})


def os_name():
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


# ---------- graphics: keep GTK away from Vulkan ----------
#
# On a Steam Deck in desktop mode, Valve's Gamescope Vulkan layer shows a "Gamescope WSI
# Layer Error" pop-up (a zenity window) whenever GTK 4 draws a window with Vulkan. A
# terminal has no use for Vulkan, so GTK is pointed at OpenGL, and Vulkan is switched off so
# GTK can't fall back to it if OpenGL fails. A renderer the user chose is left alone, and
# the shell inside the window never sees these settings (see graphics_env_fixes).

_graphics_before = {}


def use_opengl_not_vulkan():
    """Call before GTK loads. Returns True if it changed anything."""
    if os.environ.get("GSK_RENDERER") or _graphics_before:
        return False
    for name, value in (("GSK_RENDERER", "ngl"), ("GDK_DEBUG", "vulkan-disable"),
                        ("GDK_DISABLE", "vulkan")):
        before = os.environ.get(name)
        _graphics_before[name] = before
        os.environ[name] = f"{before},{value}" if before else value
    return True


def graphics_env_fixes():
    """(restore, remove) for the shell and the programs started from it: the user's own
    values to put back, and the names to take out again."""
    restore = {name: value for name, value in _graphics_before.items() if value is not None}
    remove = [name for name, value in _graphics_before.items() if value is None]
    return restore, remove


# The AppImage's launcher (packaging/appimage/AppRun) points GTK, Python and friends at its
# own copies. It remembers each variable as ALIASMAKER_ORIG_<NAME>, or ALIASMAKER_WAS_UNSET_<NAME>.
BUNDLE_VARS = ("GI_TYPELIB_PATH", "GDK_PIXBUF_MODULE_FILE", "GSETTINGS_SCHEMA_DIR",
               "GIO_MODULE_DIR", "XDG_DATA_DIRS")


def bundle_env_fixes():
    """(restore, remove) that undo the AppImage launcher's settings; empty outside an AppImage."""
    restore, remove = {}, []
    for name in BUNDLE_VARS:
        if f"ALIASMAKER_ORIG_{name}" in os.environ:
            restore[name] = os.environ[f"ALIASMAKER_ORIG_{name}"]
        elif os.environ.get(f"ALIASMAKER_WAS_UNSET_{name}"):
            remove.append(name)
    return restore, remove


def child_env_fixes():
    """Everything the shell inside the window must get back, from graphics and the AppImage."""
    restore, remove = graphics_env_fixes()
    bundle_restore, bundle_remove = bundle_env_fixes()
    return {**restore, **bundle_restore}, remove + bundle_remove


def system_lines():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or "unknown"
    session = os.environ.get("XDG_SESSION_TYPE") or ("wayland" if os.environ.get("WAYLAND_DISPLAY")
                                                     else "x11" if os.environ.get("DISPLAY") else "none")
    shell = os.path.basename(os.environ.get("SHELL", "")) or "unknown"
    libs = [f"Python {platform.python_version()}"]
    libs += [f"{name} {version}" for name, version in _versions.items()]
    return [
        f"{APP} {app_version()} ({_part})",
        f"OS: {os_name()}",
        f"Kernel: {platform.release()}",
        f"Desktop: {desktop} ({session})",
        f"Graphics: GSK_RENDERER={os.environ.get('GSK_RENDERER') or 'default'}"
        + (", Vulkan switched off" if "vulkan" in (os.environ.get("GDK_DISABLE") or "") else ""),
        f"Shell: {shell}",
        "Libraries: " + ", ".join(libs),
    ]


# ---------- writing reports ----------

def build_report(kind, summary, details, steps=None, part=None, when=None):
    when = when or datetime.now()
    steps = _steps if steps is None else steps
    lines = [
        f"{APP} crash report",
        "=" * 40,
        f"When: {when:%Y-%m-%d %H:%M:%S}",
        f"Kind: {KINDS.get(kind, kind)}",
        f"Part: {part or _part}",
        "",
        "What happened",
        f"  {summary}",
        "",
        "Steps just before (oldest first)",
    ]
    lines += [f"  {s}" for s in steps] or ["  (none recorded)"]
    lines += ["", "This PC"]
    lines += [f"  {s}" for s in system_lines()]
    lines += ["", "Details for the developer", details.rstrip(), "", PRIVACY_NOTE, ""]
    return scrub("\n".join(lines), _typed)


def save_report(text, kind, part=None):
    """Write a report and return its path (None if the folder can't be written)."""
    folder = crash_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = folder / f"{stamp}-{kind}-{part or _part}.txt"
        path.write_text(text)
        for old in list_reports()[MAX_REPORTS:]:
            old.unlink(missing_ok=True)
        return path
    except OSError:
        return None


def record_exception(exc_type, exc, tb, kind="error"):
    """Turn a Python error into a saved report."""
    if isinstance(exc, TestCrash):
        kind = "test"
    summary = "".join(traceback.format_exception_only(exc_type, exc)).strip().splitlines()[-1]
    where = traceback.extract_tb(tb)[-1] if tb else None
    if where:
        summary += f"  (in {os.path.basename(where.filename)}, {where.name}, line {where.lineno})"
    details = "".join(traceback.format_exception(exc_type, exc, tb))
    return save_report(build_report(kind, summary, details), kind)


def record_startup_problem(summary, details=""):
    return save_report(build_report("startup", summary, details or summary), "startup")


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit, BrokenPipeError)):
        return sys.__excepthook__(exc_type, exc, tb)
    try:
        path = record_exception(exc_type, exc, tb)
    except Exception:  # the recorder must never make things worse
        path = None
    if _part != "doit" or os.environ.get("ALIASMAKER_DEBUG"):
        sys.__excepthook__(exc_type, exc, tb)
    if exc_type is TestCrash:
        print("Test crash done. Open Alias Maker Debug to see the report it made.", file=sys.stderr)
    elif path:
        print(f"{APP} hit a problem and saved a crash report. To see it, open "
              "\"Alias Maker Debug\" from your app launcher (or type: aliasmaker-debug).",
              file=sys.stderr)


def _thread_hook(args):
    if args.exc_type is SystemExit:
        return
    _excepthook(args.exc_type, args.exc_value, args.exc_traceback)


# ---------- sudden crashes (faulthandler) ----------

def running_file(pid):
    return crash_dir() / f".running-{pid}.txt"


def steps_file(pid):
    return crash_dir() / f".steps-{pid}.txt"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def collect_sudden_crashes():
    """Turn leftover "running" files from Alias Maker windows that died into reports."""
    folder = crash_dir()
    made = []
    try:
        candidates = list(folder.glob(".running-*.txt"))
    except OSError:
        return made
    for path in candidates:
        try:
            pid = int(path.stem.split("-", 1)[1])
        except ValueError:
            continue
        if pid == os.getpid() or pid_alive(pid):
            continue
        try:
            raw = path.read_text(errors="replace")
            steps = steps_file(pid).read_text(errors="replace").splitlines() if steps_file(pid).exists() else []
            when = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if raw.strip():
            first = next((l for l in raw.splitlines() if l.startswith("Fatal Python error")), "")
            summary = first or "Alias Maker closed suddenly"
            report = build_report("crash", summary, raw, steps=steps, part="window", when=when)
            saved = save_report(report, "crash", part="window")
            if saved:
                made.append(saved)
        path.unlink(missing_ok=True)
        steps_file(pid).unlink(missing_ok=True)
    return made


def _clean_exit():
    global _running_file
    if _running_file is not None:
        try:
            faulthandler.disable()
            _running_file.close()
            running_file(os.getpid()).unlink(missing_ok=True)
            steps_file(os.getpid()).unlink(missing_ok=True)
        except OSError:
            pass
        _running_file = None


def install(part, typed=None, sudden_crashes=False):
    """Start recording. part: "window", "doit" or "debug". typed: what the user typed (hidden in reports).

    sudden_crashes=True also catches hard crashes (for the long-running window), and
    returns the reports made from sudden crashes last time.
    """
    global _part, _typed, _running_file
    made = []
    _part = part
    _typed = list(typed) if typed else None
    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    if sudden_crashes and _running_file is None:
        made = collect_sudden_crashes()
        try:
            crash_dir().mkdir(parents=True, exist_ok=True)
            _running_file = open(running_file(os.getpid()), "w")
            faulthandler.enable(file=_running_file, all_threads=True)
            import atexit
            atexit.register(_clean_exit)
        except OSError:
            _running_file = None
    return made


# ---------- reading reports (for Alias Maker Debug) ----------

def list_reports():
    """Saved reports, newest first."""
    try:
        return sorted((p for p in crash_dir().glob("*.txt") if not p.name.startswith(".")),
                      key=lambda p: p.name, reverse=True)
    except OSError:
        return []


def report_title(path):
    """A one-line description for lists: when, what kind, what went wrong."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return path.name
    when = kind = summary = ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("When: "):
            when = line[6:22]
        elif line.startswith("Kind: "):
            kind = line[6:].split(" (")[0]
        elif line == "What happened" and i + 1 < len(lines):
            summary = lines[i + 1].strip()
    return f"{when}  {kind}: {summary}" if when else path.name


def seen_file():
    return crash_dir() / ".seen"


def unseen_count():
    """Reports made since Alias Maker Debug last showed them."""
    try:
        seen = seen_file().read_text().strip()
    except OSError:
        seen = ""
    return sum(1 for p in list_reports() if p.name > seen)


def mark_seen():
    reports = list_reports()
    if reports:
        try:
            seen_file().write_text(reports[0].name)
        except OSError:
            pass


def delete_report(path):
    Path(path).unlink(missing_ok=True)


# ---------- health check ----------

OK, WARN, BAD = "ok", "warning", "problem"
MARKS = {OK: "✔ OK     ", WARN: "⚠ Check  ", BAD: "✘ Problem"}


def _run(argv, timeout=10):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return done.returncode, (done.stdout + done.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as err:
        return None, str(err)


GI_PROBE = r"""
import gi, sys
print("PyGObject", gi.__version__)
try:
    gi.require_version("Gtk", "4.0"); from gi.repository import Gtk
    print("GTK", f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}")
except Exception as e:
    print("GTK-missing", e)
try:
    gi.require_version("Vte", "3.91"); from gi.repository import Vte
    print("VTE", f"{Vte.get_major_version()}.{Vte.get_minor_version()}.{Vte.get_micro_version()}")
except Exception as e:
    print("VTE-missing", e)
"""


def health_check():
    """Check what Alias Maker needs. Returns a list of (status, what, detail)."""
    results = []
    add = lambda status, what, detail: results.append((status, what, detail))  # noqa: E731

    add(OK, f"{APP} version", app_version())
    py = sys.version_info
    add(OK if py >= (3, 9) else BAD, "Python", platform.python_version()
        + ("" if py >= (3, 9) else " (too old: Alias Maker needs 3.9 or newer)"))

    in_appimage = bool(os.environ.get("ALIASMAKER_BUNDLED_FISH"))
    code, out = _run([sys.executable, "-c", GI_PROBE])
    found = dict(line.split(" ", 1) for line in out.splitlines() if " " in line)
    if in_appimage:
        for key, what in (("GTK", "GTK 4"), ("VTE", "VTE (the terminal part)")):
            if key in found:
                add(OK, what, f"{found[key]} (built into the AppImage)")
            else:
                add(BAD, what, f"the AppImage couldn't load it: {found.get(key + '-missing', out or code)}")
        found = {"PyGObject": found.get("PyGObject", "?"), "GTK": "x", "VTE": "x"}  # reported above
    if in_appimage and "PyGObject" not in found:
        add(BAD, "PyGObject", "the AppImage couldn't load it")
    elif code is None or code < 0:
        add(BAD, "GTK and VTE", f"checking them crashed ({out or code}). Try: sudo pacman -S gtk4 vte4 python-gobject")
    elif "PyGObject" not in found:
        add(BAD, "PyGObject", "missing. Fix: sudo pacman -S python-gobject")
    elif in_appimage:
        add(OK, "PyGObject", f"{found['PyGObject']} (built into the AppImage)")
    else:
        add(OK, "PyGObject", found["PyGObject"])
        add(OK if "GTK" in found else BAD, "GTK 4",
            found.get("GTK") or "missing. Fix: sudo pacman -S gtk4")
        add(OK if "VTE" in found else BAD, "VTE (the terminal part)",
            found.get("VTE") or "missing. Fix: sudo pacman -S vte4")

    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        add(OK, "Screen", "Wayland" if os.environ.get("WAYLAND_DISPLAY") else "X11")
    else:
        add(WARN, "Screen", "no desktop found (fine over SSH; the window needs a desktop)")

    bundled_fish = os.environ.get("ALIASMAKER_BUNDLED_FISH", "")
    fish = shutil.which("fish")
    if bundled_fish and os.access(bundled_fish, os.X_OK):
        _code, out = _run([bundled_fish, "--version"])
        add(OK, "fish shell", f"{out.split('version')[-1].strip()} (built into the AppImage)")
    elif fish:
        _code, out = _run([fish, "--version"])
        add(OK, "fish shell", out.split("version")[-1].strip() or "installed")
    else:
        add(WARN, "fish shell", "not installed: no Let'sdostuff~ prompt, /clippy or one-word commands. "
                                "Fix: sudo pacman -S fish")
    for program, why, package in (("fastfetch", "PC info next to the DOIT logo", "fastfetch"),
                                  ("whatis", "descriptions in the Database", "man-db"),
                                  ("xdg-open", "opening /clippy results", "xdg-utils")):
        add(OK if shutil.which(program) else WARN, program,
            "installed" if shutil.which(program) else f"missing ({why}). Fix: sudo pacman -S {package}")

    here = Path(__file__).resolve().parent
    doit_ok = shutil.which("doit") or (here / "doit").exists()
    add(OK if doit_ok else BAD, "doit command", "found" if doit_ok else "missing: reinstall Alias Maker")

    config = custom_file().parent
    data = crash_dir().parent
    for name, path, what in (("Your custom commands", config / "custom.json", "commands"),
                             ("Settings", config / "settings.json", None),
                             ("Database", data / "library.json", "programs")):
        if not path.exists():
            add(OK, name, "none yet" if name != "Database" else "not scanned yet (opens on first start)")
            continue
        try:
            content = json.loads(path.read_text())
            count = len(content.get(what, [])) if what and isinstance(content, dict) else None
            add(OK, name, f"readable ({count} {what})" if count is not None else "readable")
        except (OSError, ValueError) as err:
            add(BAD, name, f"damaged ({type(err).__name__}). Rename or delete {scrub(str(path))} "
                           "and Alias Maker starts it fresh")
    fish_file = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "fish" / "conf.d" / "alias-maker.fish"
    add(OK, "One-word commands file", "present" if fish_file.exists() else "not made yet")

    reports = list_reports()
    add(OK if not reports else WARN, "Crash reports",
        "none" if not reports else f"{len(reports)} saved ({unseen_count()} new)")
    return results


def health_text(results=None):
    results = health_check() if results is None else results
    lines = [f"{APP} health check ({datetime.now():%Y-%m-%d %H:%M})", ""]
    lines += [f"{MARKS[s]}  {what}: {detail}" for s, what, detail in results]
    problems = sum(1 for s, *_ in results if s == BAD)
    lines += ["", "Everything Alias Maker needs is here." if not problems
              else f"{problems} problem(s) found. The Fix: lines say what to install."]
    return scrub("\n".join(lines))


def everything_text():
    """One file to send the developer: the health check, the PC's basics and every report."""
    parts = [health_text(), "", "This PC"] + [f"  {s}" for s in system_lines()]
    reports = list_reports()
    parts += ["", f"Crash reports: {len(reports)}", ""]
    for path in reports:
        try:
            parts += ["#" * 60, path.read_text(errors="replace")]
        except OSError:
            pass
    return scrub("\n".join(parts))


def save_for_sharing(text, name):
    """Save text where people find it: Downloads if there is one, else the home folder."""
    folder = Path.home() / "Downloads"
    if not folder.is_dir():
        folder = Path.home()
    path = folder / f"{name}-{datetime.now():%Y%m%d-%H%M%S}.txt"
    path.write_text(text)
    return path


def issue_url(title):
    from urllib.parse import quote
    body = ("What were you doing when it happened?\n\n"
            "(Paste the report below. Alias Maker Debug copied it for you: press Ctrl+V.)\n\n")
    return f"{ISSUES_URL}?title={quote(title)}&body={quote(body)}"
