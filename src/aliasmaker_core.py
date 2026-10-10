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
  doit list             the easy commands
  doit --dry-run ...    show what would run, without running anything
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

APP = "Alias Maker"
VERSION = "0.4.0"
DIR_NAME = "alias-maker"
OLD_DIR_NAME = "doit"
DEFAULT_SETTINGS = {"logging": None, "yes_words": ["y", "yes"]}
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


def find_index():
    """Look for the easy-command index: env override, next to this script, then installed copies."""
    candidates = []
    if os.environ.get("DOIT_COMMANDS"):
        candidates.append(Path(os.environ["DOIT_COMMANDS"]))
    candidates.append(Path(__file__).resolve().parent.parent / "data" / "commands.json")
    candidates.append(data_dir() / "commands.json")
    candidates.append(Path("/usr/share/alias-maker/commands.json"))
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"Couldn't find commands.json. Is {APP} installed correctly?")


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


def load_index(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    phrase_map = {}
    for entry in data["commands"]:
        for phrase in entry["phrases"]:
            key = normalize(phrase)
            if key in phrase_map:
                print(f"Note: \"{phrase}\" is listed twice in commands.json; "
                      f"using {phrase_map[key]['id']}.", file=sys.stderr)
                continue
            phrase_map[key] = entry
    return data["commands"], phrase_map


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


def save_custom_command(phrase, command, confirm):
    """Save one custom command, replacing any existing one with the same phrase."""
    norm = normalize(phrase)
    custom = [c for c in load_custom() if normalize(c["phrase"]) != norm]
    custom.append({"phrase": phrase.strip(), "command": command.strip(), "confirm": bool(confirm),
                   "added": datetime.now().isoformat(timespec="seconds")})
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


def phrase_problem(norm, custom_map, phrase_map):
    """Why a phrase can't simply be used. Returns (problem, detail); problem is None if it's free.

    "empty" and "reserved" are hard stops. "custom-clash" and "easy-clash" mean the
    phrase is taken and the user must agree to replace it; detail is the command it runs now.
    """
    if not norm:
        return "empty", None
    if match_builtin(norm) or norm in NEVER_MIND:
        return "reserved", None
    if norm in custom_map:
        return "custom-clash", custom_map[norm]["command"]
    if norm in phrase_map:
        return "easy-clash", phrase_map[norm]["command"]
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


def package_info(wanted_paths):
    """Which package owns each program file, and each package's description, via pacman."""
    if not shutil.which("pacman"):
        return {}, {}
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
    library = {
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "has_manuals": bool(shutil.which("whatis")),
        "has_pacman": bool(shutil.which("pacman")),
        "programs": entries,
    }
    write_json(library_path(), library)
    return library


def expand_word(word):
    """A search word plus simple variations: word endings and common synonyms.

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
    for form in list(forms):
        forms.update(SYNONYMS.get(form, []))
    return forms


def search_library(programs, query, limit=20):
    """Programs whose name, description or package match every word. Name matches first."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return 0, []
    scored = []
    for program in programs:
        name = program["name"].lower()
        haystack = " ".join([name, program["description"].lower(), (program["package"] or "").lower()])
        if not all(any(form in haystack for form in expand_word(w)) for w in words):
            continue
        if name == words[0]:
            score = 0
        elif name.startswith(words[0]):
            score = 1
        elif all(w in name for w in words):
            score = 2
        elif all(w in haystack for w in words):
            score = 3
        else:
            score = 4  # matched only through a synonym
        scored.append((score, len(name), name, program))
    scored.sort(key=lambda item: item[:3])
    return len(scored), [item[3] for item in scored[:limit]]


def search_easy(commands, query):
    words = [w for w in query.lower().split() if w]
    found = []
    for entry in commands:
        haystack = " ".join(entry["phrases"] + [entry["explanation"], entry["command"]]).lower()
        if words and all(any(form in haystack for form in expand_word(w)) for w in words):
            found.append(entry)
    return found


# ---------- /clippy: look things up instead of running them ----------

HELPER_NAME = "clippy"  # the slash command: /clippy chrooting
CACHYOS_WIKI = os.environ.get("ALIASMAKER_CACHYOS_WIKI", "https://wiki.cachyos.org").rstrip("/")
ARCH_WIKI_API = os.environ.get("ALIASMAKER_ARCH_WIKI_API", "https://wiki.archlinux.org/api.php")
WIKI_MAX_AGE_DAYS = 7
USER_AGENT = f"AliasMaker/{VERSION} (+https://github.com/theStyleWithin/Alias-maker)"
LANGUAGE_PREFIX = re.compile(r"^[a-z]{2}(-[a-z]{2,4})?$")  # /bg/, /de/, /zh/: translated pages
STOP_WORDS = {"how", "do", "i", "a", "an", "the", "to", "my", "is", "what", "can", "you", "me",
              "with", "in", "on", "of", "for", "and", "it", "does", "about", "please", "help",
              "use", "using", "make", "get", "into", "from", "this", "that"}


def wiki_index_path():
    return data_dir() / "cachyos-wiki.json"


def fetch_text(url, timeout=8):
    """Download a page. Raises OSError (including URLError) if it can't."""
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


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


def page_details(url):
    """Title and one-line description from a wiki page (falls back to its address)."""
    import html
    try:
        page = fetch_text(url)
    except (OSError, ValueError):
        return {"url": url, "title": title_from_url(url), "description": ""}
    title = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    description = (re.search(r'<meta\s+name="description"\s+content="([^"]*)"', page, re.I)
                   or re.search(r'<meta\s+content="([^"]*)"\s+name="description"', page, re.I))
    title = html.unescape(title.group(1)).strip() if title else title_from_url(url)
    title = re.sub(r"\s*\|\s*CachyOS\s*$", "", title)
    return {"url": url, "title": title,
            "description": html.unescape(description.group(1)).strip() if description else ""}


def refresh_wiki_index():
    """Download the list of English CachyOS wiki pages with their titles. Raises OSError offline."""
    from concurrent.futures import ThreadPoolExecutor
    root = fetch_text(f"{CACHYOS_WIKI}/sitemap-index.xml")
    urls = []
    if "<sitemapindex" in root:
        for sitemap in sitemap_urls(root):
            urls += sitemap_urls(fetch_text(sitemap))
    else:
        urls = sitemap_urls(root)
    urls = sorted({u for u in urls if english_page(u)})
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = list(pool.map(page_details, urls))
    index = {"fetched_at": datetime.now().isoformat(timespec="seconds"),
             "source": CACHYOS_WIKI, "pages": pages}
    write_json(wiki_index_path(), index)
    return index


def wiki_index(quiet=False):
    """The saved wiki index, refreshed when it's a week old. Returns (index or None, online)."""
    index = read_json(wiki_index_path(), None)
    fresh = False
    if index and index.get("source") == CACHYOS_WIKI:
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
        print("Getting the CachyOS wiki's list of pages (only once a week, a few seconds)...")
    try:
        return refresh_wiki_index(), True
    except (OSError, ValueError):
        return index, False


def meaningful_words(query):
    words = [w for w in re.findall(r"[a-z0-9][a-z0-9+._-]*", query.lower())]
    kept = [w for w in words if w not in STOP_WORDS]
    return kept or words


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


def search_arch_wiki(query, limit=3):
    """Best effort: the Arch Wiki's own search. Returns [] if it can't be reached."""
    from urllib.parse import urlencode
    words = meaningful_words(query)
    if not words:
        return []
    stems = sorted(expand_word(words[0]) - {words[0]}, key=len)
    term = " ".join([stems[0] if stems and words[0].endswith(("ing", "ed")) else words[0]] + words[1:])
    url = f"{ARCH_WIKI_API}?" + urlencode({"action": "opensearch", "search": term,
                                             "limit": limit, "format": "json"})
    try:
        data = json.loads(fetch_text(url, timeout=6))
        return [{"title": t, "url": u, "description": ""} for t, u in zip(data[1], data[3])][:limit]
    except (OSError, ValueError, IndexError, TypeError):
        return []


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
    """/clippy <topic>: show helpful links about a topic. It never runs the command."""
    query = query.strip()
    if not query:
        print(f"Tell me what you want to know about, for example: /{HELPER_NAME} chrooting")
        return 1
    print(f"/{HELPER_NAME}: Here's what I found about \"{query}\". "
          "(I'm only looking it up, not running anything.)\n")
    index, online = wiki_index()
    choices = []

    wiki_pages = search_wiki(index["pages"], query) if index else []
    if wiki_pages:
        print("CachyOS wiki")
        for page in wiki_pages:
            choices.append(("link", page["url"]))
            line = page["title"] + (f" - {page['description']}" if page["description"] else "")
            print(f"  {len(choices)}) {line}\n     {page['url']}")
        print()

    arch_pages = search_arch_wiki(query) if online is not False else []
    if arch_pages:
        print("Arch Wiki")
        for page in arch_pages:
            choices.append(("link", page["url"]))
            print(f"  {len(choices)}) {page['title']}\n     {page['url']}")
        print()

    library = state.library()
    if library and library.get("programs"):
        words = meaningful_words(query)
        _, local = search_library(library["programs"], " ".join(words[:1]), limit=3)
        local = [p for p in local if p["source"] == "manual"]
        if local:
            print("On this PC (manual pages, work without internet)")
            for program in local:
                choices.append(("manual", program["name"]))
                print(f"  {len(choices)}) {program['name']} - {program['description']}"
                      f"   (manual: man {program['name']})")
            print()

    if online is False:
        note = ("You seem to be offline, so I can't refresh the wiki list or open web pages."
                if index else "You seem to be offline, so I can't look anything up on the wiki.")
        print(note)
    if not choices:
        print(f"I didn't find anything about \"{query}\". Try a different word, "
              "or search the Database in the Alias Maker window (☰ → Database).")
        return 1
    if not interactive():
        return 0
    number = ask(f"Open one? Type a number 1-{len(choices)} (Enter to skip): ")
    number = (number or "").strip()
    if not number.isdigit() or not 1 <= int(number) <= len(choices):
        return 0
    kind, target = choices[int(number) - 1]
    if state.dry_run:
        print(f"[dry run] Would open: {'man ' + target if kind == 'manual' else target}")
        return 0
    if kind == "manual":
        return read_manual_page(target)
    return 0 if open_link(target) else 1


def read_manual_page(name):
    if not shutil.which("man"):
        print("Manual pages aren't installed. Install them with: sudo pacman -S man-db man-pages")
        return 1
    return subprocess.run(["man", name]).returncode


# ---------- the session ----------

class State:
    def __init__(self, commands, phrase_map, settings, dry_run):
        self.commands = commands
        self.phrase_map = phrase_map
        self.settings = settings
        self.dry_run = dry_run
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
    words = custom["command"].split()
    if words and words[0] == "sudo":
        words = words[1:]
    if words:
        program = state.program(words[0])
        if program and program["description"]:
            explanation = f"Your own command. ({program['name']}: {program['description']})"
    return {"id": "custom", "category": "custom", "command": custom["command"],
            "explanation": explanation, "confirm": custom.get("confirm", False),
            "source_url": None, "warning": None}


# ---------- built-in words ----------

def match_builtin(norm):
    """Returns (name, argument) if this is one of Alias Maker's own words, else None."""
    words = norm.split()
    if not words:
        return None
    if norm in ("list", "help", "what can you do", "what do you know"):
        return ("list", None)
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
    if name == "list":
        show_list(state.commands)
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


def show_list(commands):
    print("Here are the easy commands. Type: doit <phrase>\n")
    by_category = {}
    for entry in commands:
        by_category.setdefault(entry["category"], []).append(entry)
    for category, entries in by_category.items():
        print(f"{category}:")
        for entry in entries:
            phrases = ", ".join(f'"{p}"' for p in entry["phrases"])
            print(f"  {phrases}")
            print(f"      {entry['explanation']}")
        print()
    print("More: doit create, doit forget <phrase>, /clippy <topic>. "
          "The full Database is in the Alias Maker window (☰ → Database).")


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
    """Print search results for both tiers. Returns the list of programs shown (numbered)."""
    easy = search_easy(state.commands, query)
    if easy:
        print("Easy commands:")
        for entry in easy:
            print(f"  doit {entry['phrases'][0]}  ->  {entry['explanation']}")
        print()
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
    problem, detail = phrase_problem(normalize(phrase), state.custom_map, state.phrase_map)
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
    if problem == "easy-clash":
        print(f"\"{phrase}\" is already an easy command (it runs: {detail}).")
        answer = ask_or_leave(f"Use it for yours instead? Yours will win. "
                              f"(type {yes_hint(state.settings)} for yes) ")
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


def pick_easy(state):
    for number, entry in enumerate(state.commands, 1):
        print(f"  {number:>2}) {entry['phrases'][0]}  ->  {entry['command']}")
    number = choose(len(state.commands))
    return state.commands[number - 1] if number else None


def add_custom(state, command=None, program=None):
    """Walk the user through making their own phrase for a command."""
    print("\nLet's make your own command.")
    if command is None and program is None:
        print("\nWhat should it run?")
        print("  1) Search the programs on this PC")
        print("  2) Pick one of the easy commands")
        print("  3) Type the command myself")
        how = choose(3)
        if how == 0:
            return 0
        if how == 1:
            program = pick_program(state)
            if not program:
                return 0
        elif how == 2:
            entry = pick_easy(state)
            if not entry:
                return 0
            command = entry["command"]
        else:
            command = ask_or_leave("Type the command exactly: ").strip()
            if not command:
                return 0
    if program:
        extra = ask_or_leave(f"Add anything after \"{program}\"? For example -f. "
                             f"(Enter for nothing) ").strip()
        command = f"{program} {extra}".strip()
    print(f"\nIt will run: {command}")

    while True:
        phrase = ask_or_leave("What do you want to type for it, after 'doit'? ").strip()
        if check_phrase(state, phrase):
            break

    if "sudo" in command.split():
        confirm = True
        print("It needs admin rights (sudo), so I'll always ask before running it.")
    else:
        answer = ask_or_leave(f"Ask before running it every time? "
                              f"(type {yes_hint(state.settings)} for yes, anything else for no) ")
        confirm = is_yes(answer, state.settings)

    print(f"\n  doit {phrase}  ->  {command}" + ("  (asks first)" if confirm else ""))
    answer = ask_or_leave(f"Save this? (type {yes_hint(state.settings)} for yes) ")
    if not is_yes(answer, state.settings):
        print("Okay, not saved.")
        return 1
    state.custom = save_custom_command(phrase, command, confirm)
    print(f"Saved. Now \"doit {phrase}\" runs: {command}")
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
    elif entry.get("category", "").startswith("install") and library_path().is_file():
        state._library = scan_library()  # new software: refresh the list quietly
    return code


def run_entry_flow(entry, phrase, state):
    first_run_logging(state.settings)
    if not explain_and_confirm(entry, state.settings):
        print("Okay, not doing it.")
        return 1
    return run_entry(entry, phrase, state)


def handle(text, state):
    """Returns an exit code, or None if the phrase wasn't recognised."""
    norm = normalize(text)
    builtin = match_builtin(norm)
    if builtin:
        return run_builtin(*builtin, state)
    custom = state.custom_map.get(norm)
    entry = custom_entry(custom, state) if custom else state.phrase_map.get(norm)
    if entry is None:
        print(f"I don't know how to \"{text.strip()}\" yet.")
        known = list(state.custom_map) + list(state.phrase_map)
        guesses = difflib.get_close_matches(norm, known, n=3, cutoff=0.6)
        if guesses:
            print("Did you mean: " + ", ".join(f'"{g}"' for g in guesses) + "?")
        else:
            print("Type 'doit list' to see the easy commands, or open the Database in the "
                  "Alias Maker window (☰ → Database).")
        return None
    return run_entry_flow(entry, norm, state)


def main(argv):
    dry_run = "--dry-run" in argv or os.environ.get("DOIT_DRY_RUN") == "1"
    args = [a for a in argv if a != "--dry-run"]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if args and args[0] == "--version":
        print(f"{APP} {VERSION}")
        return 0

    migrate_old_dirs()
    try:
        commands, phrase_map = load_index(find_index())
    except (OSError, ValueError, KeyError) as err:
        print(f"{APP} couldn't load its command list: {err}", file=sys.stderr)
        return 2
    state = State(commands, phrase_map, load_settings(), dry_run)

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
        norm = normalize(text)
        if not norm:
            continue
        if norm in NEVER_MIND:
            print("Okay, never mind.")
            return 0
        code = handle(text, state)
        if code is not None:
            return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
