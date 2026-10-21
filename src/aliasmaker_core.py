#!/usr/bin/env python3
"""Alias Maker: plain-English commands for Linux (prototype).

This is the shared engine behind both the Alias Maker terminal window
(src/aliasmaker) and the doit command (src/doit).

Type doit, then what you want:
  doit                  asks "Do what? I am waiting..." and waits for you
  doit turn off         runs a command by its plain-English phrase
  /clippy chrooting     look a topic up (in the Alias Maker window; or: doit clippy ...)
  doit create           make your own phrase for any command
  doit forget <phrase>  delete one of your phrases (only the alias, never the real command)
  doit help             what doit understands, and example commands to make
  doit --dry-run ...    show what would run, without running anything
"""

import difflib
import json
import shlex
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

APP = "Alias Maker"
VERSION = "1.1.1"
DIR_NAME = "alias-maker"
OLD_DIR_NAME = "doit"
DEFAULT_SETTINGS = {"logging": None, "yes_words": ["y", "yes"], "clippy_web": None}
NEVER_MIND = {"nothing", "never mind", "nevermind", "cancel", "quit", "exit", "stop"}
EMPTY_DATABASE = ("The database is empty. It fills up the first time you open the Alias Maker "
                  "terminal app.")

# Plain words people search with, mapped to words that show up in program descriptions.
SYNONYMS = {
    "drive": ["disk", "block", "partition", "storage", "filesystem", "mount"],
    "disk": ["drive", "block", "partition", "storage", "filesystem"],
    "storage": ["disk", "block", "partition", "filesystem"],
    "wifi": ["wireless", "wlan", "network", "802.11"],
    "internet": ["network", "connection", "dns", "http"],
    "network": ["wireless", "connection", "interface"],
    "sound": ["audio", "volume", "pulse", "pipewire", "alsa", "mixer"],
    "audio": ["sound", "volume", "pulse", "pipewire", "alsa"],
    "volume": ["audio", "sound", "mixer"],
    "battery": ["power", "acpi", "upower", "charge"],
    "power": ["battery", "acpi", "shutdown", "suspend"],
    "file": ["files", "directory", "folder"],
    "folder": ["directory"],
    "picture": ["image", "photo", "screenshot"],
    "screenshot": ["screen", "capture"],
    "memory": ["ram", "mem", "swap"],
    "process": ["task", "processes", "kill"],
    "bluetooth": ["bt", "bluez"],
    "usb": ["device"],
    "download": ["fetch", "transfer", "url"],
    "zip": ["archive", "compress"],
    "time": ["date", "clock"],
    "user": ["account", "login"],
    "password": ["passwd", "credentials"],
}


class LeaveMenu(Exception):
    """Raised when the user presses Ctrl-D inside a menu or a question."""


# ---------- where things live ----------

def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / DIR_NAME


def data_dir():
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / DIR_NAME


def migrate_old_dirs():
    """Earlier versions stored things under 'doit'. Move them once, if present."""
    for new in (config_dir(), data_dir()):
        old = new.parent / OLD_DIR_NAME
        if old.is_dir() and not new.exists():
            try:
                old.rename(new)
            except OSError:
                pass


def find_examples():
    """Look for the example commands: env override, next to this script, then installed copies."""
    candidates = []
    if os.environ.get("DOIT_EXAMPLES"):
        candidates.append(Path(os.environ["DOIT_EXAMPLES"]))
    candidates.append(Path(__file__).resolve().parent.parent / "data" / "examples.json")
    candidates.append(data_dir() / "examples.json")
    candidates.append(Path("/usr/share/alias-maker/examples.json"))
    for path in candidates:
        if path.is_file():
            return path
    return None


def log_path():
    return data_dir() / "command-log.tsv"


def library_path():
    return data_dir() / "library.json"


def custom_path():
    return config_dir() / "custom.json"


# ---------- text and questions ----------

def normalize(text):
    """Lowercase, trim punctuation at the ends, squash spaces, drop a polite 'please'."""
    text = " ".join(text.lower().split())
    text = text.strip(" !?.,")
    for polite in ("please ", "pls "):
        if text.startswith(polite):
            text = text[len(polite):]
    for polite in (" please", " pls"):
        if text.endswith(polite):
            text = text[: -len(polite)]
    return text.strip(" !?.,")


def clean_phrase(text):
    """What someone typed, without the things that aren't part of the phrase: quotes around it
    and a "doit" at the start (typed again at the "Do what?" prompt)."""
    text = text.strip()
    for _ in range(3):
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
            text = text[1:-1].strip()
        words = text.split(None, 1)
        if len(words) == 2 and words[0].lower() == "doit":
            text = words[1].strip()
        else:
            break
    return text


def highlight(text):
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return f"\033[1;33m{text}\033[0m"
    return text


def ask(prompt):
    """Read a line from the user. Returns None if they hit Ctrl-C or Ctrl-D."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def ask_or_leave(prompt):
    """Like ask(), but Ctrl-D leaves the whole menu or question."""
    answer = ask(prompt)
    if answer is None:
        raise LeaveMenu
    return answer


def choose(count, prompt="Pick a number (Enter to go back): "):
    """Ask for a number 1..count. Returns the number, or 0 to go back."""
    while True:
        answer = ask_or_leave(prompt).strip().lower()
        if answer in ("", "0", "b", "back"):
            return 0
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print(f"Type a number from 1 to {count}, or press Enter to go back.")


def interactive():
    return sys.stdin.isatty()


def is_yes(answer, settings):
    if answer is None:
        return False
    return normalize(answer) in {w.lower() for w in settings["yes_words"]}


def yes_hint(settings):
    return " or ".join(f"'{w}'" for w in settings["yes_words"])


# ---------- saved data ----------

def read_json(path, default):
    if not path.is_file():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        print(f"Note: {path.name} couldn't be read, so I'm ignoring it.", file=sys.stderr)
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def detect_os():
    """This PC's OS, from /etc/os-release. "ids" holds its ID and the IDs it's based on:
    CachyOS and SteamOS -> {"cachyos"/"steamos", "arch"}, Ubuntu -> {"ubuntu", "debian"}."""
    text = read_text_file(os.environ.get("ALIASMAKER_OS_RELEASE", "/etc/os-release"))
    fields = dict(re.findall(r'^([A-Z_]+)="?([^"\n]*?)"?\s*$', text, re.M))
    ids = {fields.get("ID", "").lower(), *fields.get("ID_LIKE", "").lower().split()} - {""}
    return {"id": fields.get("ID", "linux").lower(), "ids": ids,
            "name": fields.get("PRETTY_NAME") or fields.get("NAME") or "Linux"}


def example_fits(example, this_os):
    """Whether an example suits this PC: its OS ("os", "not_os") and the programs it needs."""
    if example.get("os") and not set(example["os"]) & this_os["ids"]:
        return False
    if set(example.get("not_os", [])) & this_os["ids"]:
        return False
    return all(shutil.which(program) for program in example.get("needs", []))


def load_examples(path=None, every=False):
    """Example commands a user can make, only those that suit this PC (unless every=True).
    Nothing runs from these on its own."""
    path = path or find_examples()
    if path is None:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            examples = json.load(f).get("examples", [])
    except (OSError, ValueError):
        print(f"Note: {APP}'s example commands couldn't be read.", file=sys.stderr)
        return []
    if every:
        return examples
    this_os = detect_os()
    return [example for example in examples if example_fits(example, this_os)]


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings.update(read_json(config_dir() / "settings.json", {}))
    return settings


def save_settings(settings):
    write_json(config_dir() / "settings.json", settings)


def load_custom():
    return read_json(custom_path(), {"commands": []}).get("commands", [])


def save_custom(custom):
    write_json(custom_path(), {"version": 1, "commands": custom})
    write_shortcuts(custom)  # keep the real terminal commands in step


# Notes a command can carry when it was made from an example (e.g. Brave's installer link).
EXAMPLE_NOTES = ("explanation", "source_url", "warning")


def example_notes(example):
    """The notes worth keeping from an example, if it has any."""
    if not example:
        return {}
    return {key: example[key] for key in EXAMPLE_NOTES if example.get(key)}


def save_custom_command(phrase, command, confirm, notes=None):
    """Save one custom command, replacing any existing one with the same phrase.

    notes: explanation / source_url / warning carried over from an example.
    """
    norm = normalize(phrase)
    custom = [c for c in load_custom() if normalize(c["phrase"]) != norm]
    entry = {"phrase": phrase.strip(), "command": command.strip(), "confirm": bool(confirm),
             "added": datetime.now().isoformat(timespec="seconds")}
    entry.update(notes or {})
    custom.append(entry)
    save_custom(custom)
    return custom


def update_custom_command(old_phrase, phrase, command, confirm):
    """Change an existing custom command in place (its phrase, command or ask-first setting).

    If the new phrase belongs to a different custom command, that one is replaced:
    callers ask the user before getting here.
    """
    old, new = normalize(old_phrase), normalize(phrase)
    custom = load_custom()
    now = datetime.now().isoformat(timespec="seconds")
    index = next((i for i, c in enumerate(custom) if normalize(c["phrase"]) == old), None)
    entry = {"phrase": phrase.strip(), "command": command.strip(), "confirm": bool(confirm),
             "added": custom[index].get("added", now) if index is not None else now, "edited": now}
    if index is not None and custom[index]["command"] == entry["command"]:
        entry.update(example_notes(custom[index]))  # same command: its notes still apply
    if index is None:
        custom.append(entry)
    else:
        custom[index] = entry
    custom = [c for c in custom if c is entry or normalize(c["phrase"]) != new]
    save_custom(custom)
    return custom


def remove_custom_command(phrase):
    """Delete the user's alias only.

    This edits Alias Maker's own list (custom.json) and nothing else. The program the
    alias points to is never deleted, uninstalled or changed, so removing an alias
    can't break the computer.
    """
    norm = normalize(phrase)
    custom = [c for c in load_custom() if normalize(c["phrase"]) != norm]
    save_custom(custom)
    return custom


def target_program(command):
    """The program a command runs, e.g. 'lsblk' for 'sudo lsblk -f'."""
    words = command.split()
    if words and words[0] == "sudo":
        words = words[1:]
    return words[0] if words else command


# ---------- real terminal commands: Alias Maker's fish file ----------
#
# One-word custom commands become real commands in every fish terminal, through a file
# Alias Maker owns: ~/.config/fish/conf.d/alias-maker.fish (fish loads everything in
# conf.d by itself). Nobody edits it by hand: it's rewritten whenever a command is
# created, edited or deleted. Each shortcut runs through doit, so it still shows the
# real command, asks first when set to, and is logged.

SHELL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")
CACHYOS_FISH_CONFIG = os.environ.get("ALIASMAKER_CACHYOS_FISH_CONFIG",
                                     "/usr/share/cachyos-fish-config/cachyos-config.fish")
# fish's own commands and keywords: a shortcut with one of these names would break fish
FISH_WORDS = {
    "abbr", "alias", "and", "argparse", "begin", "bg", "bind", "block", "break", "breakpoint",
    "builtin", "case", "cd", "cdh", "command", "commandline", "complete", "contains", "continue",
    "count", "dirh", "dirs", "disown", "echo", "else", "emit", "end", "eval", "exec", "exit",
    "false", "fg", "for", "funced", "funcsave", "function", "functions", "help", "history", "if",
    "isatty", "jobs", "math", "nextd", "not", "open", "or", "path", "popd", "prevd", "printf",
    "prompt_pwd", "pushd", "pwd", "random", "read", "realpath", "return", "set", "set_color",
    "source", "status", "string", "suspend", "switch", "test", "time", "trap", "true", "type",
    "ulimit", "umask", "vared", "wait", "while", "doit", "aliasmaker",
}
# bash's own keywords and built-in commands (compgen -k -b): a shortcut with one of these names
# would break bash
BASH_WORDS = {
    "!", ".", ":", "[", "[[", "]]", "{", "}", "alias", "bg", "bind", "break", "builtin", "caller",
    "case", "cd", "command", "compgen", "complete", "compopt", "continue", "coproc", "declare",
    "dirs", "disown", "do", "done", "echo", "elif", "else", "enable", "esac", "eval", "exec",
    "exit", "export", "false", "fc", "fg", "fi", "for", "function", "getopts", "hash", "help",
    "history", "if", "in", "jobs", "kill", "let", "local", "logout", "mapfile", "popd", "printf",
    "pushd", "pwd", "read", "readarray", "readonly", "return", "select", "set", "shift", "shopt",
    "source", "suspend", "test", "then", "time", "times", "trap", "true", "type", "typeset",
    "ulimit", "umask", "unalias", "unset", "until", "wait", "while", "doit", "aliasmaker",
}
# Where bash gets its aliases and functions from (read, never run, to see which names are taken)
BASH_CONFIG_FILES = ("/etc/bash.bashrc", "/etc/bashrc", "~/.bashrc", "~/.bash_aliases")
NOT_A_SHELL = {"nologin", "false", "true", "git-shell"}
FILLER_WORDS = {"just", "my", "the", "a", "an", "please", "me", "i", "some", "all", "really",
                "to", "of", "for", "and", "it", "this", "that", "your", "our", "now"}
SHORTCUTS_HEADER = """\
# Made by Alias Maker. Don't edit this file by hand: it's rewritten every time you
# create, edit or delete a command. Change your commands in Alias Maker instead
# (☰ → Custom Commands, or doit create / doit forget in the terminal).
#
# Each one-word command below is a real terminal command. It runs through doit, so it
# still shows the real command, asks first when it's set to, and is logged. Deleting a
# command in Alias Maker only removes it from here, never the program it points to.
"""


def fish_shortcuts_path():
    return config_dir().parent / "fish" / "conf.d" / "alias-maker.fish"


def bash_shortcuts_path():
    return config_dir() / "shortcuts.bash"


def login_shell():
    """The shell this PC gives you in a terminal: the one in your account, then $SHELL.
    ALIASMAKER_SHELL=/path/to/shell picks a different one."""
    candidates = [os.environ.get("ALIASMAKER_SHELL", "")]
    try:
        import pwd
        candidates.append(pwd.getpwuid(os.getuid()).pw_shell)
    except (ImportError, KeyError):
        pass
    candidates += [os.environ.get("SHELL", ""), "/bin/bash", "/bin/sh"]
    for path in candidates:
        if path and os.path.basename(path) not in NOT_A_SHELL and os.access(path, os.X_OK):
            return path
    return "/bin/sh"


def shell_kind(path=None):
    """"bash", "fish", "zsh"...: the shell's name, from its file name."""
    return os.path.basename(path or login_shell())


def shell_info():
    """The login shell and its version, for the scan and the health check."""
    path = login_shell()
    version = ""
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5,
                                env=clean_env())
        version = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr) else ""
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
    return {"path": path, "name": shell_kind(path), "version": version}


def shell_builtins(path):
    """(name, description) for the shell's own commands (cd, export...): not programs, but
    commands this PC understands. Only bash and fish are asked; others add nothing."""
    kind = shell_kind(path)
    try:
        if kind == "bash":
            script = 'for b in $(compgen -b; compgen -k); do help -d "$b" 2>/dev/null || echo "$b -"; done'
            out = subprocess.run([path, "--norc", "--noprofile", "-c", script], capture_output=True,
                                 text=True, timeout=20, env=clean_env()).stdout
            found = []
            for line in out.splitlines():
                name, _, description = line.partition(" - ")
                if name.strip() and " " not in name.strip():
                    found.append((name.strip(), description.strip().rstrip("-").strip()))
            return found
        if kind == "fish":
            out = subprocess.run([path, "--no-config", "-c", "builtin -n"], capture_output=True,
                                 text=True, timeout=20, env=clean_env()).stdout
            return [(name.strip(), "") for name in out.splitlines() if name.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []


def doit_path():
    return Path(__file__).resolve().parent / "doit"


def doit_command():
    """How other terminals start doit. An AppImage's own folder vanishes when it closes,
    so from an AppImage it's the AppImage file itself with 'doit' as its first word."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        return [appimage, "doit"]
    return [str(doit_path())]


def fish_quote(text):
    """Quote text for fish: single quotes, with backslashes and quotes escaped."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def names_in_fish_file(path):
    """Alias, function and abbreviation names defined in a fish config file."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    names = set(re.findall(r"^\s*alias\s+([^\s=]+)\s*=", text, re.M))
    names |= set(re.findall(r"^\s*alias\s+([^\s=]+)\s+['\"]", text, re.M))
    names |= set(re.findall(r"^\s*function\s+([^\s;]+)", text, re.M))
    names |= set(re.findall(r"^\s*abbr\s+(?:-a\s+|--add\s+)?(?:-\S+\s+)*([^\s-][^\s]*)", text, re.M))
    return names


def names_in_bash_file(path):
    """Alias and function names defined in a bash config file."""
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    names = set(re.findall(r"^\s*alias\s+(?:-\S+\s+)*([^\s=]+)=", text, re.M))
    names |= set(re.findall(r"^\s*(?:function\s+)?([A-Za-z0-9_.+-]+)\s*\(\)", text, re.M))
    names |= set(re.findall(r"^\s*function\s+([A-Za-z0-9_.+-]+)", text, re.M))
    return names


def shell_config_names():
    """Names already used by the user's fish or bash setup (CachyOS's fish config included)."""
    fish_dir = config_dir().parent / "fish"
    names = names_in_fish_file(CACHYOS_FISH_CONFIG) | names_in_fish_file(fish_dir / "config.fish")
    functions = fish_dir / "functions"
    if functions.is_dir():
        names |= {f.stem for f in functions.glob("*.fish")}
    for config in BASH_CONFIG_FILES:
        names |= names_in_bash_file(config)
    return names


def shell_name_problem(name):
    """Why this name can't be a command on its own. None if it can.

    Returns (kind, detail): "spaces" (detail: the word the terminal would look for),
    "characters", or "taken" (detail: what already uses the name).
    """
    name = name.strip()
    if " " in name:
        return "spaces", name.split()[0]
    if not SHELL_NAME.match(name):
        return "characters", None
    if name in BASH_WORDS:
        return "taken", "a built-in bash command"
    if name in FISH_WORDS:
        return "taken", "a built-in fish command"
    if name in shell_config_names():
        return "taken", "a shortcut in your shell setup"
    found = shutil.which(name)
    if found:
        return "taken", f"a program on your PC ({found})"
    return None


def works_on_its_own(phrase):
    return shell_name_problem(phrase) is None and not match_builtin(normalize(phrase))


def name_suggestions(phrase):
    """For a name with spaces: (shorter doit phrase, shorter one-word name, full one-word name).

    "just check my fucking drives" -> ("check drives", "check-drives",
    "just-check-my-fucking-drives"). The shorter ones are None when there's nothing to shorten.
    """
    words = [re.sub(r"[^a-z0-9_.+-]", "", w) for w in phrase.lower().split()]
    words = [w for w in words if w]
    full = "-".join(words)
    meaningful = [w for w in words if w not in FILLER_WORDS] or words
    short_words = [meaningful[0], meaningful[-1]] if len(meaningful) >= 2 else meaningful
    short_phrase = " ".join(short_words)
    if len(short_words) < 2 or short_phrase == " ".join(words):
        return None, None, full
    return short_phrase, "-".join(short_words), full


def fish_in_use():
    """Whether fish is on this PC (so its shortcut file is worth writing)."""
    return (config_dir().parent / "fish").is_dir() or bool(shutil.which("fish")) or shell_kind() == "fish"


def write_shortcuts(custom=None):
    """Keep the real terminal commands in step with the saved ones, for bash and for fish."""
    written = write_bash_shortcuts(custom)
    if fish_in_use():
        write_fish_shortcuts(custom)
    return written


def write_bash_shortcuts(custom=None):
    """Rewrite Alias Maker's bash file (read by the Alias Maker window) from the saved commands."""
    custom = load_custom() if custom is None else custom
    written = []
    lines = [SHORTCUTS_HEADER]
    doit = " ".join(shlex.quote(part) for part in doit_command())
    for entry in custom:
        name = entry["phrase"].strip()
        if not works_on_its_own(name):
            continue  # works with doit in front only
        lines += [f"{name}() {{ {doit} --alias {shlex.quote(name)} -- \"$@\"; }}"]
        written.append(name)
    lines.append("")
    path = bash_shortcuts_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".bash.tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(path)
    except OSError as err:
        print(f"Note: couldn't update {path}: {err}", file=sys.stderr)
    return written


def write_fish_shortcuts(custom=None):
    """Rewrite Alias Maker's fish file from the saved commands. Returns the names written."""
    custom = load_custom() if custom is None else custom
    written = []
    lines = [SHORTCUTS_HEADER]
    for entry in custom:
        name = entry["phrase"].strip()
        if not works_on_its_own(name):
            continue  # works with doit in front only
        description = fish_quote(f"Alias Maker: {entry['command']}")
        lines += [f"function {name} --description {description}",
                  f"    {' '.join(fish_quote(part) for part in doit_command())} --alias {fish_quote(name)} -- $argv",
                  "end", ""]
        written.append(name)
    # Alias Maker windows reload this file when it changes, and use this list to remove
    # shortcuts that were deleted or renamed.
    names = " ".join(fish_quote(name) for name in written)
    lines.append(f"set -g __aliasmaker_shortcut_names {names}".rstrip() + "\n")
    path = fish_shortcuts_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".fish.tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(path)
    except OSError as err:
        print(f"Note: couldn't update {path}: {err}", file=sys.stderr)
    return written


def where_shortcuts_work():
    """Where a new one-word command can be used right away."""
    kind = shell_kind()
    if in_alias_maker() and kind == "fish":
        return "(works right away in Alias Maker windows; other terminals need a new window)"
    if kind == "bash":
        return "(works in Alias Maker windows; other terminals only know doit <phrase>)"
    return "(in a new terminal window)"


def phrase_problem(norm, custom_map):
    """Why a phrase can't simply be used. Returns (problem, detail); problem is None if it's free.

    "empty" and "reserved" are hard stops. "custom-clash" means the user already uses the
    phrase and must agree to replace it; detail is the command it runs now.
    """
    if not norm:
        return "empty", None
    if match_builtin(norm) or norm in NEVER_MIND:
        return "reserved", None
    if norm in custom_map:
        return "custom-clash", custom_map[norm]["command"]
    return None, None


# ---------- logging ----------

def first_run_logging(settings):
    """Ask once whether to keep a log. Non-interactive runs never ask and never log."""
    if settings["logging"] is not None or not interactive():
        return
    print("Before we start: want me to keep a log of every command I run,")
    print("so you can look back at what happened later?")
    print("(You can change this anytime with: doit logging on / doit logging off)")
    answer = ask(f"Keep a log? (type {yes_hint(settings)} for yes, anything else for no) ")
    settings["logging"] = is_yes(answer, settings)
    save_settings(settings)
    print("Okay, I'll keep a log." if settings["logging"] else "Okay, no log.")
    print()


def write_log(settings, phrase, command, code):
    if settings.get("logging") is not True:
        return
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{phrase}\t{command}\t{code}\n")


# ---------- scanning this PC ----------

WHATIS_LINE = re.compile(r"^(\S+) \(([^)]+)\)\s+- (.*)$")
SECTION_RANK = {"1": 0, "8": 1, "6": 2}  # user commands, admin commands, games


def find_programs():
    """Every program the terminal can run, from the folders listed in PATH. Read only."""
    programs = {}
    visited = set()
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder or not os.path.isdir(folder):
            continue
        real = os.path.realpath(folder)
        if real in visited:
            continue
        visited.add(real)
        try:
            names = sorted(os.listdir(real))
        except OSError:
            continue
        for name in names:
            if name in programs or name.startswith((".", "-")) or any(c.isspace() for c in name):
                continue
            path = os.path.join(real, name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                programs[name] = path
    return programs


def clean_env():
    return dict(os.environ, LC_ALL="C", LANG="C", MANPAGER="cat", PAGER="cat")


def manual_descriptions(names):
    """One-line summaries from installed manual pages, via whatis. Never runs the programs."""
    if not shutil.which("whatis"):
        return {}
    best = {}
    names = list(names)
    for start in range(0, len(names), 100):
        chunk = names[start:start + 100]
        try:
            result = subprocess.run(["whatis", "-l", "--", *chunk], capture_output=True,
                                    text=True, timeout=60, env=clean_env())
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in result.stdout.splitlines():
            match = WHATIS_LINE.match(line.strip())
            if not match:
                continue
            name, section, description = match.groups()
            rank = SECTION_RANK.get(section[:1])
            if rank is None:
                continue  # library functions and file formats, not commands
            if name not in best or rank < best[name][0]:
                best[name] = (rank, description.strip())
    return {name: desc for name, (_, desc) in best.items()}


def package_tool():
    """The package manager whose records the scan can read: "pacman", "dpkg" or None."""
    if shutil.which("pacman"):
        return "pacman"
    if shutil.which("dpkg-query") and os.path.isdir(DPKG_INFO):
        return "dpkg"
    return None


DPKG_INFO = os.environ.get("ALIASMAKER_DPKG_INFO", "/var/lib/dpkg/info")


def package_info(wanted_paths):
    """Which package owns each program file, and each package's description."""
    tool = package_tool()
    if tool == "pacman":
        return pacman_package_info(wanted_paths)
    if tool == "dpkg":
        return dpkg_package_info(wanted_paths)
    return {}, {}


def dpkg_package_info(wanted_paths):
    """Ubuntu / Debian: owners from dpkg's file lists, descriptions from dpkg-query."""
    owners, descriptions = {}, {}
    for listing in Path(DPKG_INFO).glob("*.list"):
        package = listing.stem.split(":")[0]
        try:
            lines = listing.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for path in lines:
            # dpkg still lists some programs under /bin and /sbin, now links into /usr
            for candidate in (path, "/usr" + path if path.startswith(("/bin/", "/sbin/")) else None):
                if candidate in wanted_paths:
                    owners.setdefault(candidate, package)
    try:
        result = subprocess.run(["dpkg-query", "-W", "-f", "${Package}\t${binary:Summary}\n"],
                                capture_output=True, text=True, timeout=120, env=clean_env())
        for line in result.stdout.splitlines():
            package, _, summary = line.partition("\t")
            if summary:
                descriptions[package] = summary.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return owners, descriptions


def pacman_package_info(wanted_paths):
    """Arch, CachyOS and SteamOS: owners and descriptions via pacman."""
    owners, descriptions = {}, {}
    try:
        files = subprocess.run(["pacman", "-Ql"], capture_output=True, text=True,
                               timeout=120, env=clean_env())
        for line in files.stdout.splitlines():
            package, _, path = line.partition(" ")
            if path in wanted_paths:
                owners[path] = package
        info = subprocess.run(["pacman", "-Qi"], capture_output=True, text=True,
                              timeout=120, env=clean_env())
        name = None
        for line in info.stdout.splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key = key.strip()
            if key == "Name":
                name = value.strip()
            elif key == "Description" and name:
                descriptions[name] = value.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return owners, descriptions


def scan_library():
    """Build and save the list of every program on this PC with a short description."""
    programs = find_programs()
    manuals = manual_descriptions(programs)
    wanted = set(programs.values()) | {os.path.realpath(p) for p in programs.values()}
    owners, package_descriptions = package_info(wanted)
    entries = []
    for name, path in sorted(programs.items()):
        package = owners.get(path) or owners.get(os.path.realpath(path))
        if name in manuals:
            description, source = manuals[name], "manual"
        elif package and package_descriptions.get(package):
            description, source = package_descriptions[package], "package"
        else:
            description, source = "", "none"
        entries.append({"name": name, "path": path, "description": description,
                        "source": source, "package": package})
    shell = shell_info()
    for name, description in shell_builtins(shell["path"]):
        if name not in programs:
            entries.append({"name": name, "path": f"(built into {shell['name']})",
                            "description": description or f"A {shell['name']} built-in command",
                            "source": "shell", "package": shell["name"]})
    entries.sort(key=lambda entry: entry["name"])
    this_os = detect_os()
    library = {
        "shell": shell,
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "os": {"id": this_os["id"], "name": this_os["name"]},
        "has_manuals": bool(shutil.which("whatis")),
        "has_pacman": bool(shutil.which("pacman")),
        "package_tool": package_tool(),
        "folders": program_folders(),
        "programs": entries,
    }
    write_json(library_path(), library)
    return library


def program_folders():
    """Each PATH folder and when it last changed. Installing or removing a program changes
    its folder, so this tells whether the Database is out of date without a full scan."""
    folders = {}
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        real = os.path.realpath(folder) if folder else ""
        if real and real not in folders and os.path.isdir(real):
            try:
                folders[real] = os.stat(real).st_mtime
            except OSError:
                pass
    return folders


def library_outdated(library=None):
    """True if there's no Database yet, or software was installed or removed since the scan."""
    library = read_json(library_path(), None) if library is None else library
    if not library or "folders" not in library:
        return True
    scanned = library["folders"]
    return any(scanned.get(folder) != mtime for folder, mtime in program_folders().items())


def word_forms(word):
    """A search word plus its plain variations (no synonyms).

    drives -> drive, chrooting -> chroot, running -> run, mounted -> mount, updated -> update.
    """
    forms = {word}
    if len(word) > 3 and word.endswith("s"):
        forms.add(word[:-1])
    if word.endswith("ing") and len(word) - 3 >= 3:
        stem = word[:-3]
        forms.add(stem)
        if len(stem) >= 4 and stem[-1] == stem[-2]:
            forms.add(stem[:-1])  # running -> run
    if word.endswith("ed") and len(word) - 2 >= 4:
        forms.update({word[:-2], word[:-1]})  # mounted -> mount, updated -> update
    return forms


def expand_word(word):
    """word_forms plus common synonyms: drive -> disk, block, partition..."""
    forms = word_forms(word)
    for form in list(forms):
        forms.update(SYNONYMS.get(form, []))
    return forms


# The programs most people actually want for a plain word, best first. Only programs that
# are installed show up; this just decides the order. ("drives" should put lsblk on top.)
_DRIVE_PICKS = ["lsblk", "df", "findmnt", "blkid", "fdisk", "partitionmanager", "gparted",
                "udisksctl", "mount", "du", "ncdu", "smartctl"]
_NETWORK_PICKS = ["nmcli", "nmtui", "ip", "ping", "iwctl", "ss", "curl"]
_SOUND_PICKS = ["pavucontrol", "wpctl", "pactl", "alsamixer", "amixer"]
_PROCESS_PICKS = ["btop", "htop", "top", "ps", "kill", "pkill", "killall"]
COMMON_PICKS = {
    "drive": _DRIVE_PICKS, "disk": _DRIVE_PICKS, "storage": _DRIVE_PICKS,
    "partition": _DRIVE_PICKS, "space": ["df", "du", "ncdu", "lsblk"],
    "wifi": ["nmcli", "nmtui", "iwctl", "iw"], "internet": _NETWORK_PICKS,
    "network": _NETWORK_PICKS,
    "sound": _SOUND_PICKS, "audio": _SOUND_PICKS, "volume": _SOUND_PICKS,
    "battery": ["upower", "acpi", "powerprofilesctl"],
    "power": ["poweroff", "reboot", "shutdown", "systemctl", "powerprofilesctl", "upower"],
    "memory": ["free", "btop", "htop", "top", "vmstat"], "ram": ["free", "btop", "htop", "top"],
    "process": _PROCESS_PICKS, "task": _PROCESS_PICKS, "kill": ["kill", "pkill", "killall"],
    "update": ["pacman", "paru", "yay", "checkupdates"],
    "install": ["pacman", "paru", "yay"], "package": ["pacman", "paru", "yay", "pactree"],
    "bluetooth": ["bluetoothctl"], "usb": ["lsusb"],
    "file": ["ls", "find", "cp", "mv", "rm", "dolphin"], "folder": ["ls", "mkdir", "cd", "dolphin"],
    "zip": ["tar", "unzip", "zip", "7z"], "archive": ["tar", "unzip", "zip", "7z"],
    "time": ["date", "timedatectl", "cal"], "date": ["date", "timedatectl", "cal"],
    "user": ["whoami", "id", "useradd", "passwd"], "password": ["passwd"],
    "download": ["curl", "wget", "aria2c"],
    "screenshot": ["spectacle"], "picture": ["gwenview", "spectacle"],
    "cpu": ["lscpu", "btop", "htop", "sensors"], "temperature": ["sensors"],
    "gpu": ["nvidia-smi", "glxinfo", "lspci"], "graphics": ["nvidia-smi", "glxinfo", "lspci"],
    "hardware": ["inxi", "lshw", "lspci", "lsusb", "fastfetch"],
    "log": ["journalctl", "dmesg"], "service": ["systemctl"],
}


def pick_rank(word, name):
    """Where name sits in the common picks for this word (0 is best), or None."""
    best = None
    for form in word_forms(word):
        picks = COMMON_PICKS.get(form, [])
        if name in picks:
            rank = picks.index(name)
            best = rank if best is None else min(best, rank)
    return best


def search_library(programs, query, limit=20):
    """Programs that match every word, best match first.

    Each word scores the program: the name is the word (best), it's one of the common
    picks for that word, the name starts with or contains it, the description says it,
    and last, only a synonym matched. Ties go to the shorter name.
    """
    words = [w for w in query.lower().split() if w]
    if not words:
        return 0, []
    scored = []
    for program in programs:
        name = program["name"].lower()
        about = " ".join([program["description"].lower(), (program["package"] or "").lower()])
        about_words = set(re.findall(r"[a-z0-9.+-]+", about))
        total = 0
        for word in words:
            forms = word_forms(word)
            rank = pick_rank(word, name)
            if name in forms:
                points = 100
            elif rank is not None:
                points = 90 - 3 * rank
            elif any(name.startswith(form) for form in forms):
                points = 60
            elif any(form in name for form in forms):
                points = 45
            elif forms & about_words:
                points = 30
            elif any(form in about for form in forms):
                points = 20
            elif any(form in name or form in about for form in expand_word(word) - forms):
                points = 10
            else:
                break  # this word doesn't match: leave the program out
            total += points
        else:
            scored.append((-total, len(name), name, program))
    scored.sort(key=lambda item: item[:3])
    return len(scored), [item[3] for item in scored[:limit]]


# ---------- /clippy: look things up instead of running them ----------

HELPER_NAME = "clippy"  # the slash command: /clippy chrooting
DOCS_FILE_NAME = "docs.json"  # which documentation /clippy uses for each operating system
WIKI_MAX_AGE_DAYS = 7
USER_AGENT = f"AliasMaker/{VERSION} (+https://github.com/theStyleWithin/Alias-maker)"
LANGUAGE_PREFIX = re.compile(r"^[a-z]{2}(-[a-z]{2,4})?$")  # /bg/, /de/, /zh/: translated pages
STOP_WORDS = {"how", "do", "i", "a", "an", "the", "to", "my", "is", "what", "can", "you", "me",
              "with", "in", "on", "of", "for", "and", "it", "does", "about", "please", "help",
              "use", "using", "make", "get", "into", "from", "this", "that"}


def find_docs_file():
    """The list of documentation sources: env override, next to this script, then installed copies."""
    candidates = []
    if os.environ.get("ALIASMAKER_DOCS"):
        candidates.append(Path(os.environ["ALIASMAKER_DOCS"]))
    candidates.append(Path(__file__).resolve().parent.parent / "data" / DOCS_FILE_NAME)
    candidates.append(data_dir() / DOCS_FILE_NAME)
    candidates.append(Path("/usr/share/alias-maker") / DOCS_FILE_NAME)
    return next((path for path in candidates if path.is_file()), None)


def docs_for_this_os(this_os=None):
    """The documentation for the operating system this PC runs: {"name", "sources"}, or None.

    The first entry in docs.json whose "os" matches wins, so a specific system (CachyOS, SteamOS,
    Ubuntu) comes before the family it's built on (Arch, Debian)."""
    this_os = this_os or detect_os()
    path = find_docs_file()
    data = read_json(path, {}) if path else {}
    for system in data.get("systems", []):
        if set(system.get("os", [])) & this_os["ids"]:
            return system
    return None


def index_path(source):
    return data_dir() / f"docs-{source['id']}.json"


# Where Arch, Debian, Fedora and openSUSE keep their trusted certificates. A bundled Python
# (the AppImage's) doesn't know where this PC keeps them.
CERT_FILES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
              "/etc/ssl/ca-bundle.pem", "/etc/ssl/cert.pem")


def fetch_text(url, timeout=8):
    """Download a page. Raises OSError (including URLError) if it can't."""
    import ssl
    import urllib.request
    cafile = next((path for path in CERT_FILES if os.path.isfile(path)), None)
    context = ssl.create_default_context(cafile=cafile) if cafile else None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        raw = response.read()
    if raw[:2] == b"\x1f\x8b":  # gzip: the Stack Exchange API always sends it
        import gzip
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def sitemap_urls(xml):
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


def english_page(url):
    """True for the English pages (no language prefix like /bg/ or /de/)."""
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/")
    first = path.split("/", 1)[0] if path else ""
    return not LANGUAGE_PREFIX.match(first)


def title_from_url(url):
    from urllib.parse import urlparse
    slug = urlparse(url).path.strip("/").split("/")[-1] or "home"
    return slug.replace("_", " ").replace("-", " ").capitalize()


def page_details(url, suffix=""):
    """Title and one-line description from a wiki page (falls back to its address).
    suffix: the site's name that its page titles end with ("... | CachyOS"), to trim."""
    import html
    try:
        page = fetch_text(url)
    except (OSError, ValueError):
        return {"url": url, "title": title_from_url(url), "description": ""}
    title = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    description = (re.search(r'<meta\s+name="description"\s+content="([^"]*)"', page, re.I)
                   or re.search(r'<meta\s+content="([^"]*)"\s+name="description"', page, re.I))
    title = html.unescape(title.group(1)).strip() if title else title_from_url(url)
    if suffix:
        title = re.sub(r"\s*\|\s*" + re.escape(suffix) + r"\s*$", "", title)
    return {"url": url, "title": title,
            "description": html.unescape(description.group(1)).strip() if description else ""}


def refresh_index(source):
    """Download the list of English pages of a wiki (from its sitemap) with their titles.
    Raises OSError offline."""
    from concurrent.futures import ThreadPoolExecutor
    base = source["url"].rstrip("/")
    root = fetch_text(f"{base}/sitemap-index.xml")
    urls = []
    if "<sitemapindex" in root:
        for sitemap in sitemap_urls(root):
            urls += sitemap_urls(fetch_text(sitemap))
    else:
        urls = sitemap_urls(root)
    urls = sorted({u for u in urls if english_page(u)})
    suffix = source.get("title_suffix", "")
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = list(pool.map(lambda url: page_details(url, suffix), urls))
    index = {"fetched_at": datetime.now().isoformat(timespec="seconds"),
             "source": base, "pages": pages}
    write_json(index_path(source), index)
    return index


def source_index(source, quiet=False):
    """A wiki's saved page list, refreshed when it's a week old. Returns (index or None, online)."""
    base = source["url"].rstrip("/")
    index = read_json(index_path(source), None)
    fresh = False
    if index and index.get("source") == base:
        try:
            age = datetime.now() - datetime.fromisoformat(index["fetched_at"])
            fresh = age.days < WIKI_MAX_AGE_DAYS
        except (KeyError, ValueError):
            fresh = False
    else:
        index = None
    if fresh:
        return index, None  # None: didn't need to check the internet
    if not quiet:
        print(f"Getting the {source['name']}'s list of pages (only once a week, a few seconds)...")
    try:
        return refresh_index(source), True
    except (OSError, ValueError):
        return index, False


# Words that don't say what the question is about: "I need help", "something is wrong"
VAGUE_WORDS = {"need", "want", "problem", "problems", "issue", "issues", "question", "questions",
               "stuff", "thing", "things", "something", "anything", "everything", "wrong",
               "broken", "trouble", "fix", "work", "works", "working", "linux", "computer", "pc",
               "terminal", "command", "commands", "hi", "hello", "hey", "clippy", "ok", "okay",
               "have", "has", "got", "just", "really", "very", "some", "there", "here", "not"}


def meaningful_words(query):
    words = [w for w in re.findall(r"[a-z0-9][a-z0-9+._-]*", query.lower())]
    specific = [w for w in words if w not in STOP_WORDS and w not in VAGUE_WORDS and len(w) > 1]
    kept = [w for w in words if w not in STOP_WORDS]
    return specific or kept or words


def has_substance(query):
    """Whether there's something specific to look up, not just "I need help"."""
    words = re.findall(r"[a-z0-9][a-z0-9+._-]*", query.lower())
    return any(len(w) > 1 and w not in STOP_WORDS and w not in VAGUE_WORDS for w in words)


def narrow_down(query):
    """Ask what the person needs until there's something specific to look up.
    Returns the question to search, or None if there isn't one."""
    example = f"/{HELPER_NAME} wifi keeps dropping"
    for _ in range(2):
        if has_substance(query):
            return query
        if not interactive():
            print(f"What do you need help with? Tell me a bit more, for example: {example}")
            return None
        answer = ask("What do you need help with? ")
        if answer is None or not answer.strip():
            return None
        query = answer.strip() if has_substance(answer) else f"{query} {answer}".strip()
    if has_substance(query):
        return query
    print(f"I still can't tell what to look up. Try a few more words, for example: {example}")
    return None


def score_text(words, *weighted_fields):
    """How well the words match: each word scores by the best field it appears in."""
    total = 0
    for word in words:
        forms = expand_word(word)
        best = 0
        for weight, text in weighted_fields:
            if any(form in text for form in forms):
                best = max(best, weight)
        total += best
    return total


def search_wiki(pages, query, limit=5):
    words = meaningful_words(query)
    scored = []
    for page in pages:
        score = score_text(words, (3, page["title"].lower()), (2, page["description"].lower()),
                           (1, page["url"].lower().replace("_", " ").replace("-", " ")))
        if score:
            scored.append((-score, page["title"].lower(), page))
    scored.sort(key=lambda item: item[:2])
    return [item[2] for item in scored[:limit]]


def search_mediawiki(api, query, limit=3):
    """Best effort: a MediaWiki site's own search (the Arch Wiki's, for one). [] if it found nothing,
    None if it couldn't be reached."""
    from urllib.parse import urlencode
    words = meaningful_words(query)
    if not words:
        return []
    stems = sorted(expand_word(words[0]) - {words[0]}, key=len)
    term = " ".join([stems[0] if stems and words[0].endswith(("ing", "ed")) else words[0]] + words[1:])
    url = f"{api}?" + urlencode({"action": "opensearch", "search": term,
                                   "limit": limit, "format": "json"})
    try:
        data = json.loads(fetch_text(url, timeout=6))
    except (OSError, ValueError):
        return None  # couldn't reach it (offline, or blocked): not the same as finding nothing
    try:
        return [{"title": t, "url": u, "description": ""} for t, u in zip(data[1], data[3])][:limit]
    except (IndexError, TypeError):
        return []


def search_stackexchange(source, query, limit=3):
    """Questions that have answers, from a Stack Exchange site (Ask Ubuntu, Unix & Linux...), through
    its free public search. [] if nothing, None if it couldn't be reached."""
    import html
    from urllib.parse import urlencode
    topic = " ".join(meaningful_words(query))
    api = source.get("api", "https://api.stackexchange.com/2.3").rstrip("/")
    url = f"{api}/search/advanced?" + urlencode({"order": "desc", "sort": "relevance", "q": topic,
                                                   "site": source["site"], "answers": 1,
                                                   "pagesize": limit})
    try:
        items = json.loads(fetch_text(url, timeout=8)).get("items", [])
    except (OSError, ValueError, AttributeError):
        return None
    found = []
    for item in items[:limit]:
        link = str(item.get("link", ""))
        if not link.startswith("https://"):
            continue  # only real web addresses, never anything else
        answers = int(item.get("answer_count", 0) or 0)
        found.append({"title": html.unescape(str(item.get("title", link))), "url": link,
                      "description": f"{answers} answer{'s' if answers != 1 else ''}, "
                                     f"score {int(item.get('score', 0) or 0)}"})
    return found


def default_sources():
    """What /clippy uses when docs.json has no entry for this system (docs.json's "default")."""
    path = find_docs_file()
    data = read_json(path, {}) if path else {}
    return (data.get("default") or {}).get("sources", [])


def web_search_allowed(state):
    """Whether /clippy may also search question-and-answer sites. Asks once, and only when someone
    is there to answer: it sends their question to stackexchange.com."""
    choice = state.settings.get("clippy_web")
    if choice is None and interactive():
        print("/clippy can also search question-and-answer sites (stackexchange.com: Ask Ubuntu,")
        print("Unix & Linux). That sends your question to them. (Change it later with: doit clippy web off)")
        answer = ask(f"Search there too? (type {yes_hint(state.settings)} for yes, anything else for no) ")
        choice = is_yes(answer, state.settings)
        state.settings["clippy_web"] = choice
        save_settings(state.settings)
        print()
    return bool(choice)


RESULTS_STYLE = """
:root { --bg:#fafafa; --fg:#1d1d1f; --muted:#6b6b72; --link:#0b5fff; --card:#ffffff; --line:#e3e3e8; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161618; --fg:#ececf0; --muted:#9a9aa3; --link:#7aa7ff; --card:#1f1f23; --line:#2e2e34; }
}
body { background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, sans-serif; margin:0; padding:24px 16px; }
main { max-width:46rem; margin:0 auto; }
h1 { font-size:1.4rem; margin:0 0 4px; } h2 { font-size:1.05rem; margin:24px 0 8px; }
p.note { color:var(--muted); margin:0 0 8px; }
ul { list-style:none; padding:0; margin:0; }
li { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 14px; margin:8px 0; }
a { color:var(--link); font-weight:600; } span.d { color:var(--muted); } code { font-size:.95em; }
"""


def write_results_page(query, sections, manuals, offline):
    """A small page of what /clippy found, to open in the browser. Everything shown is escaped and
    only real web addresses become links."""
    import html
    esc = lambda text: html.escape(str(text), quote=True)  # noqa: E731
    body = [f"<h1>{esc(APP)}'s /{HELPER_NAME}: {esc(query)}</h1>",
            "<p class='note'>Here's what I found. I only looked things up: nothing was run. "
            "Read them in your own time.</p>"]
    if offline:
        body.append("<p class='note'>Some sites couldn't be reached, so this list may be shorter than usual.</p>")
    for section in sections:
        body.append(f"<h2>{esc(section['name'])}</h2><ul>")
        for page in section["items"]:
            url = page["url"] if str(page["url"]).startswith(("https://", "http://")) else ""
            title = f"<a href='{esc(url)}'>{esc(page['title'])}</a>" if url else esc(page["title"])
            extra = f" <span class='d'>{esc(page['description'])}</span>" if page.get("description") else ""
            body.append(f"<li>{title}{extra}</li>")
        body.append("</ul>")
    if manuals:
        body.append("<h2>On this PC (manual pages)</h2><ul>")
        for name, description in manuals:
            body.append(f"<li><code>man {esc(name)}</code> <span class='d'>{esc(description)}</span></li>")
        body.append("</ul>")
    page = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{esc(APP)} /{HELPER_NAME}: {esc(query)}</title><style>{RESULTS_STYLE}</style></head>"
            f"<body><main>{''.join(body)}</main></body></html>")
    path = data_dir() / "clippy-results.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path


def open_link(url):
    """Open a web page in the user's browser without tying up the terminal."""
    opener = os.environ.get("ALIASMAKER_OPENER") or shutil.which("xdg-open")
    if not opener:
        print(f"I couldn't find a way to open your browser. Here's the link: {url}")
        return False
    subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return True


def clippy(state, query):
    """/clippy <topic>: a search helper. It looks in the documentation of the operating system this
    PC runs (and, if allowed, question-and-answer sites), lists what it found, and opens a page of
    results in the browser. If the question is too vague it asks what you need help with. It never
    runs the command, and it isn't AI: it only shows real pages."""
    from urllib.parse import quote_plus
    query = query.strip()
    if query.lower() in ("web on", "web off"):
        state.settings["clippy_web"] = query.lower().endswith("on")
        save_settings(state.settings)
        print("Okay, /clippy will search question-and-answer sites too." if state.settings["clippy_web"]
              else "Okay, /clippy will only use your system's own documentation and this PC.")
        return 0
    query = narrow_down(query)
    if query is None:
        return 1
    print(f"/{HELPER_NAME}: Here's what I found about \"{query}\". "
          "(I'm only looking it up, not running anything.)\n")
    this_os = detect_os()
    system = docs_for_this_os(this_os)
    topic = " ".join(meaningful_words(query))
    choices, sections, offline, saved = [], [], False, False

    if system is None:
        print(f"I don't have a documentation source for {this_os['name']} yet, "
              "so I'll only look on this PC.\n")
    sources = list((system or {}).get("sources", [])) if system else default_sources()
    web_on = web_search_allowed(state) if any(s.get("kind") == "stackexchange" for s in sources) else False
    for source in sources:
        kind = source.get("kind")
        open_label = source.get("open_label", "Open the official page")
        if kind == "sitemap":
            index, online = source_index(source)
            saved = saved or bool(index)
            offline = offline or online is False
            pages = search_wiki(index["pages"], query) if index else []
        elif kind == "mediawiki":
            found = [] if offline else search_mediawiki(source["api"], query)
            if found is None:
                offline = True
            pages = found or []
        elif kind == "stackexchange":
            found = [] if (offline or not web_on) else search_stackexchange(source, query)
            if found is None:
                offline = True
            pages = found or []
        elif kind == "search":
            pages = [{"title": f'Search it for "{topic}"', "description": "",
                      "url": source["pattern"].replace("{q}", quote_plus(topic))}]
        elif kind == "link":
            pages = [{"title": open_label, "description": "", "url": source["url"]}]
        else:
            pages = []
        if source.get("home") and kind != "link":  # the front page too, so there's always something to open
            pages.append({"title": open_label, "description": "", "url": source["home"]})
        if not pages:
            continue
        heading = source["name"] + (f" ({source['note']})" if source.get("note") else "")
        print(heading)
        sections.append({"name": heading, "items": pages})
        for page in pages:
            choices.append(("link", page["url"]))
            line = page["title"] + (f" - {page['description']}" if page["description"] else "")
            print(f"  {len(choices)}) {line}\n     {page['url']}")
        print()

    manuals = []
    library = state.library()
    if library and library.get("programs"):
        words = meaningful_words(query)
        _, local = search_library(library["programs"], " ".join(words[:1]), limit=3)
        local = [p for p in local if p["source"] == "manual"]
        if local:
            print("On this PC (manual pages, work without internet)")
            for program in local:
                choices.append(("manual", program["name"]))
                manuals.append((program["name"], program["description"]))
                print(f"  {len(choices)}) {program['name']} - {program['description']}"
                      f"   (manual: man {program['name']})")
            print()

    if offline:
        print("You seem to be offline, so I can't refresh the wiki list or open web pages."
              if saved else "You seem to be offline, so I can't look anything up on the wiki.")
    if not choices:
        print(f"I didn't find anything about \"{query}\". Try a different word, "
              "or search the Database in the Alias Maker window (☰ → Database).")
        return 1
    if not interactive():
        return 0
    number = ask(f"Press Enter to see it all in your browser, or type a number 1-{len(choices)} "
                 "to open just one (n to skip): ")
    answer = (number or "").strip().lower()
    if number is None or answer in ("n", "no", "skip"):
        return 0
    if answer == "":
        page = write_results_page(query, sections, manuals, offline)
        if state.dry_run:
            print(f"[dry run] Would open: {page.as_uri()}")
            return 0
        print("Opening what I found in your browser. It's up to you to read it.")
        return 0 if open_link(page.as_uri()) else 1
    if not answer.isdigit() or not 1 <= int(answer) <= len(choices):
        return 0
    kind, target = choices[int(answer) - 1]
    if state.dry_run:
        print(f"[dry run] Would open: {'man ' + target if kind == 'manual' else target}")
        return 0
    if kind == "manual":
        return read_manual_page(target)
    return 0 if open_link(target) else 1


def man_install_hint():
    """How to get manual pages on this PC, in the words of its own package manager."""
    ids = detect_os()["ids"]
    if "steamos" in ids:
        return "SteamOS keeps its system files locked, so use the online documentation instead."
    if package_tool() == "dpkg":
        return "Install them with: sudo apt install man-db manpages"
    if shutil.which("dnf"):
        return "Install them with: sudo dnf install man-db man-pages"
    return "Install them with: sudo pacman -S man-db man-pages"


def read_manual_page(name):
    if not shutil.which("man"):
        print(f"Manual pages aren't installed. {man_install_hint()}")
        return 1
    return subprocess.run(["man", name]).returncode


# ---------- the welcome: DOIT and your PC's info ----------

def logo_path():
    return Path(__file__).resolve().parent / "shell" / "doit-logo.txt"


def logo_lines():
    try:
        return logo_path().read_text(encoding="utf-8").replace("$1", "").rstrip("\n").splitlines()
    except OSError:
        return ["DOIT"]


def read_text_file(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


TERMINAL_COMMAND = "aliasmaker"  # what the terminal app is called on the PC (and in fastfetch)


def in_alias_maker():
    return os.environ.get("ALIASMAKER") == "1"


def terminal_name(inside=None):
    """The terminal app this runs in, if known. Inside Alias Maker it's "aliasmaker"."""
    if in_alias_maker() if inside is None else inside:
        return TERMINAL_COMMAND
    return os.environ.get("TERM_PROGRAM", "")


def pc_info(inside=None):
    """Basic facts about this PC, read straight from the system (for when fastfetch is missing)."""
    import platform
    import socket
    info = []
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "you"
    info.append(("", f"{user}@{socket.gethostname()}"))
    os_name = re.search(r'^PRETTY_NAME="?([^"\n]*)', read_text_file("/etc/os-release"), re.M)
    info.append(("OS", os_name.group(1) if os_name else platform.system()))
    info.append(("Kernel", platform.release()))
    uptime = read_text_file("/proc/uptime").split()
    if uptime:
        minutes = int(float(uptime[0]) // 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        parts = [f"{days} day{'s' * (days != 1)}"] if days else []
        parts += [f"{hours} hour{'s' * (hours != 1)}"] if hours else []
        parts.append(f"{minutes} min{'s' * (minutes != 1)}")
        info.append(("Uptime", ", ".join(parts)))
    shell = os.environ.get("SHELL", "")
    if shell:
        info.append(("Shell", os.path.basename(shell)))
    terminal = terminal_name(inside)
    if terminal:
        info.append(("Terminal", terminal))
    cpu = re.search(r"^model name\s*:\s*(.+)$", read_text_file("/proc/cpuinfo"), re.M)
    if cpu:
        info.append(("CPU", f"{cpu.group(1).strip()} ({os.cpu_count()})"))
    meminfo = dict(re.findall(r"^(\w+):\s+(\d+) kB", read_text_file("/proc/meminfo"), re.M))
    if "MemTotal" in meminfo and "MemAvailable" in meminfo:
        total, free = int(meminfo["MemTotal"]), int(meminfo["MemAvailable"])
        used = total - free
        info.append(("Memory", f"{used / 1048576:.2f} GiB / {total / 1048576:.2f} GiB "
                               f"({round(100 * used / total)}%)"))
    try:
        disk = shutil.disk_usage("/")
        info.append(("Disk (/)", f"{disk.used / 1073741824:.2f} GiB / {disk.total / 1073741824:.2f} GiB "
                                 f"({round(100 * disk.used / disk.total)}%)"))
    except OSError:
        pass
    return info


# fastfetch's usual list of facts, except that Terminal says "aliasmaker": the app is
# Python underneath, so fastfetch can't tell what it is on its own. (Newer fastfetch only
# takes that through a config file, not an option.)
FASTFETCH_MODULES = ["title", "separator", "os", "host", "kernel", "uptime", "packages", "shell",
                     "display", "de", "wm", "wmtheme", "theme", "icons", "font", "cursor",
                     {"type": "terminal", "format": TERMINAL_COMMAND},
                     "cpu", "gpu", "memory", "swap", "disk", "localip", "battery",
                     "poweradapter", "locale", "break", "colors"]


def fastfetch_config():
    """Alias Maker's fastfetch settings file (written when missing or out of date)."""
    path = data_dir() / "fastfetch-welcome.jsonc"
    text = json.dumps({"modules": FASTFETCH_MODULES}, indent=2) + "\n"
    try:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError:
        return None
    return path


def fastfetch_command(color, inside):
    """How to run fastfetch with the DOIT logo, or None when it isn't installed."""
    fastfetch = shutil.which("fastfetch")
    if not fastfetch or not logo_path().is_file():
        return None
    command = [fastfetch, "--logo", str(logo_path()), "--logo-type", "file",
               "--logo-color-1", "96", "--pipe", "false" if color else "true"]
    config = fastfetch_config() if inside else None
    if config:
        command[1:1] = ["--config", str(config)]
    return command


def show_welcome():
    """Print the welcome. In a real terminal, fastfetch takes this process's place, so it
    sees the shell (fish) as its parent and reports it, not "python3"."""
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    command = fastfetch_command(color, in_alias_maker()) if color else None
    if command:
        sys.stdout.flush()
        try:
            os.execv(command[0], command)
        except OSError:
            pass  # fall back to the welcome below
    sys.stdout.write(welcome_text(color=color))
    return 0


def welcome_text(color=True, inside=None):
    """DOIT with this PC's info beside it. Uses fastfetch when it's installed.

    inside: whether this is the Alias Maker window (None: tell from $ALIASMAKER).
    """
    inside = in_alias_maker() if inside is None else inside
    command = fastfetch_command(color, inside)
    if command:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.rstrip("\n") + "\n"
        except (OSError, subprocess.TimeoutExpired):
            pass
    cyan, bold, reset = ("\033[1;96m", "\033[1;96m", "\033[0m") if color else ("", "", "")
    logo = logo_lines()
    width = max(len(line) for line in logo)
    info = pc_info(inside)
    lines = []
    for row in range(max(len(logo), len(info))):
        left = logo[row] if row < len(logo) else ""
        right = ""
        if row < len(info):
            key, value = info[row]
            right = f"{bold}{key}{reset}: {value}" if key else f"{bold}{value}{reset}"
        lines.append(f"{cyan}{left.ljust(width)}{reset}   {right}".rstrip())
    return "\n".join(lines) + "\n"


# ---------- the session ----------

class State:
    def __init__(self, examples, settings, dry_run):
        self.examples = examples
        self.settings = settings
        self.dry_run = dry_run
        self.suggestion = None  # the one phrase "Did you mean" offered, if any
        self.custom = load_custom()
        self._library = None

    @property
    def custom_map(self):
        return {normalize(c["phrase"]): c for c in self.custom}

    def library(self):
        """The saved list of programs, or None if this PC hasn't been scanned yet.

        doit never scans on its own: the Alias Maker window scans the first time it
        opens, and its Database window has a Rescan button.
        """
        if self._library is None:
            self._library = read_json(library_path(), None)
        return self._library

    def program(self, name):
        library = self.library()
        if not library:
            return None
        for program in library["programs"]:
            if program["name"] == name:
                return program
        return None


def custom_entry(custom, state):
    """Turn a saved custom command into something the runner understands."""
    explanation = "Your own command."
    if custom.get("explanation"):
        explanation = f"Your own command. {custom['explanation']}"
    else:
        program = state.program(target_program(custom["command"]))
        if program and program["description"]:
            explanation = f"Your own command. ({program['name']}: {program['description']})"
    return {"id": "custom", "category": "custom", "command": custom["command"],
            "explanation": explanation, "confirm": custom.get("confirm", False),
            "source_url": custom.get("source_url"), "warning": custom.get("warning")}


# ---------- built-in words ----------

def match_builtin(norm):
    """Returns (name, argument) if this is one of Alias Maker's own words, else None."""
    words = norm.split()
    if not words:
        return None
    if norm in ("help", "list", "what can you do", "what do you know", "examples"):
        return ("help", None)
    if norm in ("history", "show me what you did", "what did you do"):
        return ("history", None)
    if norm in ("create", "create a command", "create command", "make a command", "new command"):
        return ("create", None)
    if norm == "version":
        return ("version", None)
    if words[0] in (HELPER_NAME, "/" + HELPER_NAME):
        return ("clippy", " ".join(words[1:]))
    if words[0] in ("forget", "delete"):
        return ("forget", " ".join(words[1:]))
    if len(words) == 2 and words[0] == "logging" and words[1] in ("on", "off"):
        return ("logging", words[1])
    if len(words) == 2 and words[0] == "answer" and words[1] in ("easy", "strict"):
        return ("answer", words[1])
    if len(words) == 3 and words[0] == "answer" and words[1] == "word":
        return ("answer-word", words[2])
    return None


def run_builtin(name, arg, state):
    if name == "help":
        show_help(state.examples)
        return 0
    if name == "history":
        return show_history(state.settings)
    if name == "version":
        print(f"{APP} {VERSION}")
        return 0
    if name == "logging":
        set_logging(state.settings, arg == "on")
        return 0
    if name == "answer":
        set_yes_words(state.settings, ["y", "yes"] if arg == "easy" else ["yes"])
        return 0
    if name == "answer-word":
        set_yes_words(state.settings, [arg])
        return 0
    if name == "clippy":
        return clippy(state, arg)
    if not interactive():
        print("That one needs you at a terminal to answer questions.")
        return 2
    try:
        if name == "create":
            return add_custom(state)
        if name == "forget":
            return forget_custom(state, arg)
    except LeaveMenu:
        print("\nOkay, never mind.")
        return 0
    return 1


def set_logging(settings, on):
    settings["logging"] = on
    save_settings(settings)
    print("Logging is now on. It starts from now; nothing before this was recorded."
          if on else "Logging is now off.")


def set_yes_words(settings, words):
    settings["yes_words"] = words
    save_settings(settings)
    print(f"To say yes, you'll now type: {yes_hint(settings)}")


def show_help(examples):
    print("doit runs the commands you make. Type: doit <your phrase>\n")
    print("Built in:")
    for words, what in (
            ("doit", "asks \"Do what? I am waiting...\" and waits for you"),
            ("doit create", "make your own command, step by step"),
            ("doit forget <phrase>", "delete one of your commands (also: doit delete)"),
            ("/clippy <topic>", "look a topic up instead of running it (also: doit clippy)"),
            ("doit show me what you did", "your command history, if the log is on"),
            ("doit logging on / off", "turn the command log on or off"),
            ("doit answer easy / strict", "say yes with y or yes, or only with yes"),
            ("doit answer word <word>", "pick your own yes word"),
            ("doit help", "this list")):
        print(f"  {words:<28} {what}")
    if examples:
        print("\nExamples you could make (with doit create, or Create Command in the menu):")
        for example in examples:
            print(f"  doit {example['phrase']:<23} -> {example['command']}")
    print("\nOne-word commands you make also work on their own, without doit.")
    print("Your own commands are listed in the Alias Maker window: ☰ → Custom Commands.")


def read_log():
    """Every logged command, oldest first: dicts with when, phrase, command, code, worked."""
    path = log_path()
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        stamp, phrase, command, code = parts
        entries.append({"when": stamp, "phrase": phrase, "command": command, "code": code,
                        "worked": code == "0"})
    return entries


def log_result(entry):
    return "Worked" if entry["worked"] else f"Failed (code {entry['code']})"


def show_history(settings):
    entries = read_log()
    if settings.get("logging") is not True:
        print("Logging is off, so there's no history. Turn it on with: doit logging on "
              "(or in the Alias Maker window: ☰ → Terminal Settings)")
        if not entries:
            return 0
    if not entries:
        print("Nothing logged yet.")
        return 0
    print("Last commands I ran (newest at the bottom):\n")
    for entry in entries[-20:]:
        print(f"  {entry['when']}  \"{entry['phrase']}\"  ->  {entry['command']}  "
              f"[{log_result(entry).lower()}]")
    return 0


def print_results(state, query):
    """Print matching programs on this PC. Returns the list shown (numbered)."""
    library = state.library()
    if not library or not library.get("programs"):
        print(EMPTY_DATABASE)
        return []
    total, shown = search_library(library["programs"], query)
    if not shown:
        print(f"No programs on this PC matched \"{query}\". Try different or fewer words.")
        return []
    print("Programs on this PC:")
    for number, program in enumerate(shown, 1):
        description = program["description"] or "(no description)"
        print(f"  {number:>2}) {program['name']}  -  {description}")
    if total > len(shown):
        print(f"  ...and {total - len(shown)} more. Add words to narrow it down.")
    return shown


# ---------- custom commands ----------

def check_phrase(state, phrase):
    """True if the phrase can be used, after warning about clashes and asking when needed."""
    problem, detail = phrase_problem(normalize(phrase), state.custom_map)
    if problem == "empty":
        print("That's empty. Type the words you want to use.")
        return False
    if problem == "reserved":
        print(f"\"{phrase}\" is one of {APP}'s own words, so it can't be used. Pick something else.")
        return False
    if problem == "custom-clash":
        print(f"You already use \"{phrase}\" for: {detail}")
        answer = ask_or_leave(f"Replace it? (type {yes_hint(state.settings)} for yes) ")
        return is_yes(answer, state.settings)
    return True


def pick_program(state):
    """Search this PC and pick one program. Returns its name, or None."""
    while True:
        query = ask_or_leave("Search for what? (for example drives, wifi, battery; Enter to go back) ")
        if not query.strip():
            return None
        shown = print_results(state, query.strip())
        if not shown:
            continue
        number = choose(len(shown), "Pick a program by number (Enter to search again): ")
        if number:
            return shown[number - 1]["name"]


def pick_example(state):
    for number, example in enumerate(state.examples, 1):
        print(f"  {number:>2}) {example['phrase']}  ->  {example['command']}")
    number = choose(len(state.examples))
    return state.examples[number - 1] if number else None


def pick_name(state, example=None):
    """Ask for the new command's name and help with names the terminal can't use alone."""
    while True:
        hint = f" (Enter for \"{example['phrase']}\")" if example else ""
        phrase = ask_or_leave(f"Name the new command:{hint} ").strip()
        if not phrase and example:
            phrase = example["phrase"]
        if not check_phrase(state, phrase):
            continue
        problem = shell_name_problem(phrase)
        if problem is None:
            print(f"You'll be able to type it on its own: {phrase}  (or: doit {phrase})")
            return phrase
        kind, detail = problem
        if kind == "taken":
            print(f"\"{phrase}\" is already {detail}, so yours will work as \"doit {phrase}\" "
                  f"only. The real {phrase} stays exactly as it is.")
            return phrase
        if kind == "characters":
            print(f"\"{phrase}\" has characters a terminal command can't use, so it will work as "
                  f"\"doit {phrase}\" only.")
            return phrase
        short_phrase, short_name, full_name = name_suggestions(phrase)
        print(f"\n\"{phrase}\" has spaces, so the terminal can't use it as a command on its own "
              f"(it would look for a program called \"{detail}\"). Pick one:")
        options = []
        if short_phrase:
            options.append((f"doit {short_phrase}", "shorter, type it with doit in front", short_phrase))
        if short_name and works_on_its_own(short_name):
            options.append((short_name, "shorter, works on its own", short_name))
        if full_name and full_name != short_name and works_on_its_own(full_name):
            options.append((full_name, "your words with dashes, works on its own", full_name))
        options.append((f"doit {phrase}", "keep it, type it with doit in front", phrase))
        width = max(len(shown) for shown, _, _ in options)
        for number, (shown, why, _) in enumerate(options, 1):
            print(f"  {number}) {shown:<{width}}   {why}")
        number = choose(len(options), f"Pick 1-{len(options)} (Enter to type a different name): ")
        if not number:
            continue
        chosen = options[number - 1][2]
        if chosen != phrase and not check_phrase(state, chosen):
            continue
        return chosen


def add_custom(state, command=None, program=None):
    """Walk the user through making their own command: what it runs, then its name."""
    print("\nLet's make your own command.")
    example = None
    if command is None and program is None:
        answer = ask_or_leave("What command do you want it to point to? "
                              "(type it, or press Enter to search this PC or use an example) ").strip()
        if answer:
            command = answer
        else:
            print("  1) Search the programs on this PC")
            print("  2) Start from an example")
            how = choose(2)
            if how == 0:
                return 0
            if how == 1:
                program = pick_program(state)
                if not program:
                    return 0
            else:
                example = pick_example(state)
                if not example:
                    return 0
                command = example["command"]
                if example.get("explanation"):
                    print(example["explanation"])
    if program:
        extra = ask_or_leave(f"Add anything after \"{program}\"? For example -f. "
                             f"(Enter for nothing) ").strip()
        command = f"{program} {extra}".strip()
    print(f"It will run: {command}")

    phrase = pick_name(state, example)

    if "sudo" in command.split():
        confirm = True
        print("It needs admin rights (sudo), so I'll always ask before running it.")
    elif example and example.get("confirm"):
        confirm = True
        print("I'll ask before running it, like the example does.")
    else:
        answer = ask_or_leave(f"Ask before running it every time? "
                              f"(type {yes_hint(state.settings)} for yes, anything else for no) ")
        confirm = is_yes(answer, state.settings)

    alone = f"  (also just: {phrase})" if works_on_its_own(phrase) else ""
    print(f"\n  doit {phrase}  ->  {command}" + ("  (asks first)" if confirm else "") + alone)
    answer = ask_or_leave(f"Save this? (type {yes_hint(state.settings)} for yes) ")
    if not is_yes(answer, state.settings):
        print("Okay, not saved.")
        return 1
    state.custom = save_custom_command(phrase, command, confirm, example_notes(example))
    print(f"Saved. Now \"doit {phrase}\" runs: {command}")
    if works_on_its_own(phrase):
        print(f"You can also type just: {phrase}  {where_shortcuts_work()}")
    return 0


def forget_custom(state, phrase):
    if not phrase.strip():
        print("Tell me which one to delete, for example: doit forget just check my drives")
        return 1
    custom = state.custom_map.get(normalize(phrase))
    if not custom:
        print(f"You don't have a custom command called \"{phrase}\". "
              "See yours in the Alias Maker window: ☰ → Custom Commands.")
        return 1
    print(f"This deletes your alias \"doit {custom['phrase']}\" only. The command it points to "
          f"({custom['command']}) is not deleted or changed.")
    answer = ask_or_leave(f"Delete the alias? (type {yes_hint(state.settings)} for yes) ")
    if not is_yes(answer, state.settings):
        print("Okay, kept it.")
        return 1
    state.custom = remove_custom_command(custom["phrase"])
    print(f"Deleted your alias \"doit {custom['phrase']}\". "
          f"{target_program(custom['command'])} itself is still there, untouched.")
    return 0


# ---------- running a command ----------

def explain_and_confirm(entry, settings):
    print(entry["explanation"])
    if entry.get("source_url"):
        print("\nThis downloads and runs a script from:")
        print(f"   {highlight(entry['source_url'])}")
        print(f"That's the vendor's own official installer, not something changed by {APP}.")
    if entry.get("warning"):
        print(f"\nHeads up: {entry['warning']}")
    print(f"\nReal command: {entry['command']}")
    if not entry.get("confirm"):
        return True
    if not interactive():
        print("This one needs a yes from you, so run it in a terminal.")
        return False
    answer = ask(f"Go ahead? (type {yes_hint(settings)} to continue) ")
    return is_yes(answer, settings)


def run_entry(entry, phrase, state):
    if state.dry_run:
        print(f"[dry run] Would run: {entry['command']}")
        return 0
    try:
        code = subprocess.run(entry["command"], shell=True).returncode
    except KeyboardInterrupt:
        code = 130
    write_log(state.settings, phrase, entry["command"], code)
    if code != 0:
        print(f"\nThat didn't work (exit code {code}).")
    return code


SH_WORDS = {"cd", "echo", "printf", "export", "unset", "set", "exit", "true", "false", "test", "read",
            "exec", "eval", "type", "command", "wait", "umask", "ulimit", "alias", "trap", "shift",
            ".", ":", "[", "if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done",
            "case", "esac", "in", "!", "{", "}", "sudo", "doas", "env", "time", "nohup", "xargs"}


def missing_programs(command):
    """Programs a command calls that this PC doesn't have, e.g. ["pacman"] for "sudo pacman -Syu"
    on Ubuntu. Looks at each part of a chain (&&, ||, ;, |) and only names plain program names
    (never paths, variables or anything it can't be sure of)."""
    missing = []
    for part in re.split(r"&&|\|\||;|\|", command):
        words = part.split()
        while words and (words[0] in ("sudo", "doas", "env", "nohup", "time") or "=" in words[0]
                         or words[0].startswith("-")):
            words = words[1:]
        if not words:
            continue
        name = words[0]
        if (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name) and name not in SH_WORDS
                and not shutil.which(name) and name not in missing):
            missing.append(name)
    return missing


def other_way_for_this_pc(phrase):
    """The example command with this phrase that suits this PC's system, if there is one."""
    norm = normalize(phrase)
    return next((e for e in load_examples() if normalize(e["phrase"]) == norm), None)


def check_programs_exist(entry, phrase, state):
    """A saved command can call a program this PC doesn't have (made on another system, or the
    software was removed). Say so in plain words, and offer this system's way of doing the same
    thing if Alias Maker knows it. Returns the entry to run, or None to stop."""
    if entry.get("id") != "custom":
        return entry
    missing = missing_programs(entry["command"])
    if not missing:
        return entry
    this_os = detect_os()
    names = ", ".join(f'"{m}"' for m in missing)
    print(f"This command uses {names}, which "
          f"{'isn' + chr(39) + 't' if len(missing) == 1 else 'aren' + chr(39) + 't'} on this PC "
          f"({this_os['name']}), so it can't work here as it is.")
    better = other_way_for_this_pc(phrase)
    if better and better["command"] != entry["command"] and interactive():
        print(f'On {this_os["name"]}, Alias Maker\'s way to "{better["phrase"]}" is:')
        print(f"   {better['command']}")
        answer = ask(f"Use that for \"{normalize(phrase)}\" from now on? "
                     f"(type {yes_hint(state.settings)} for yes) ")
        if is_yes(answer, state.settings):
            save_custom_command(phrase, better["command"], better.get("confirm", False),
                                example_notes(better))
            write_shortcuts()
            print("Saved. Here it is:\n")
            return custom_entry(next(c for c in load_custom()
                                     if normalize(c["phrase"]) == normalize(phrase)), state)
    elif better and better["command"] != entry["command"]:
        print(f'On {this_os["name"]}, Alias Maker\'s way to "{better["phrase"]}" is: {better["command"]}')
        print("Run doit in a terminal to switch to it, or change it with Edit Command.")
    else:
        print(f"Install the software it needs, or change the command with Edit Command. "
              f"(Try: /clippy {missing[0]})")
    return None


def run_entry_flow(entry, phrase, state):
    entry = check_programs_exist(entry, phrase, state)
    if entry is None:
        return 1
    first_run_logging(state.settings)
    if not explain_and_confirm(entry, state.settings):
        print("Okay, not doing it.")
        return 1
    return run_entry(entry, phrase, state)


def handle(text, state):
    """Returns an exit code, or None if the phrase wasn't recognised."""
    text = clean_phrase(text)
    norm = normalize(text)
    builtin = match_builtin(norm)
    if builtin:
        return run_builtin(*builtin, state)
    custom = state.custom_map.get(norm)
    if custom is None and re.search(r"[-_]", norm):  # check-my-drives: dashes typed for spaces
        norm = normalize(re.sub(r"[-_]+", " ", norm))
        custom = state.custom_map.get(norm)
    state.suggestion = None
    if custom is None:
        print(f"I don't know how to \"{text.strip()}\" yet.")
        guesses = difflib.get_close_matches(norm, list(state.custom_map), n=3, cutoff=0.6)
        if guesses:
            print("Did you mean: " + ", ".join(f'"{g}"' for g in guesses) + "?")
            if len(guesses) == 1:
                state.suggestion = guesses[0]
        else:
            print("Make it a command with: doit create (or Create Command in the menu). "
                  "Type 'doit help' to see what doit understands.")
        return None
    return run_entry_flow(custom_entry(custom, state), norm, state)


def explain_not_found(state, words):
    """The shell couldn't find a command: say why in plain words.
    Returns 0 if it was one of the user's own phrases typed without doit, 1 otherwise."""
    if not words:
        return 1
    typed = " ".join(words)
    if normalize(typed) in state.custom_map:
        print(f'"{typed}" is one of your own commands. Put doit in front of it: doit {typed}')
        return 0
    name = words[0]
    print(f'"{name}" isn\'t a program on this PC. It may be spelled differently, or be part of '
          "software that isn't installed.")
    names = [program["name"] for program in (state.library() or {}).get("programs", [])]
    close = difflib.get_close_matches(name, names, n=3, cutoff=0.75)
    if close:
        print("Programs you have with a similar name: " + ", ".join(close))
    if "steamos" in detect_os()["ids"]:
        print("On SteamOS, add software with Discover (in desktop mode): the system itself is "
              "read-only, so pacman installs don't last.")
    print("To see everything you have: ☰ → Database in the Alias Maker window.")
    return 1


def run_shortcut(state, name, extra):
    """Run a one-word shortcut like doit would, with any extra words added to the command."""
    custom = state.custom_map.get(normalize(name))
    if custom is None:
        print(f"Alias Maker doesn't have a command called \"{name}\" anymore.")
        write_shortcuts()  # tidy the shortcut files; new terminal windows won't have it
        return 127
    entry = custom_entry(custom, state)
    if extra:
        entry["command"] += " " + " ".join(shlex.quote(word) for word in extra)
    return run_entry_flow(entry, normalize(name), state)


def main(argv):
    dry_run = "--dry-run" in argv or os.environ.get("DOIT_DRY_RUN") == "1"
    args = [a for a in argv if a != "--dry-run"]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if args and args[0] == "--version":
        print(f"{APP} {VERSION}")
        return 0
    if args and args[0] == "--welcome":  # what Alias Maker shows when a terminal opens
        return show_welcome()

    migrate_old_dirs()
    state = State(load_examples(), load_settings(), dry_run)

    if args and args[0] == "--not-found":  # from the window's fish_command_not_found
        return explain_not_found(state, args[1:])

    if args and args[0] == "--alias":  # a one-word shortcut from Alias Maker's fish file
        return run_shortcut(state, args[1] if len(args) > 1 else "", args[3:] if args[2:3] == ["--"] else args[2:])

    if args:
        code = handle(" ".join(args), state)
        return 1 if code is None else code

    if not interactive():
        print(__doc__.strip())
        return 2
    while True:
        text = ask("Do what? I am waiting... ")
        if text is None:
            print("\nOkay, never mind.")
            return 0
        text = clean_phrase(text)
        norm = normalize(text)
        if not norm:
            continue
        if norm in NEVER_MIND:
            print("Okay, never mind.")
            return 0
        if state.suggestion and is_yes(text, state.settings):
            text, state.suggestion = state.suggestion, None  # yes: the one thing it asked about
        code = handle(text, state)
        if code is not None:
            return code
        if state.suggestion:
            print(f"Type {yes_hint(state.settings)} to do that, or type something else.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
