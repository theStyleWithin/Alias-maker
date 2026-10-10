# Alias Maker: design notes

Alias Maker is its own terminal app (`aliasmaker`): a window like Konsole that runs the user's normal shell, with **Database**, **Custom Commands** and **Create Command** added to its ☰ menu. Inside it, you type `doit` followed by plain words and it runs the real Linux command. `doit` is only the prefix; the tool is called Alias Maker.

## How it's built

| File | What it is |
|---|---|
| `src/aliasmaker` | The terminal window: GTK 4 with the VTE terminal widget (the engine many Linux terminals use). Needs `vte4` and `python-gobject`. |
| `src/doit` | The command typed inside the terminal. A thin launcher for the engine. |
| `src/aliasmaker_core.py` | The shared engine: easy commands, custom commands, the scan, search, logging and settings. Both of the above use it, so a phrase saved in the window works with `doit` straight away. |
| `data/commands.json` | The easy commands. |

The window puts `src/` first on the shell's `PATH`, so `doit` works inside Alias Maker even if it isn't installed anywhere else. It was split out of [Doit-os](https://github.com/theStyleWithin/Doit-os) so the tool can be built and proven on a regular CachyOS install first. If it's stable there, it becomes Do It OS's selling point; if the distro never ships, this tool still stands on its own.

## Status

| Part | Status |
|---|---|
| Wrapper: plain-English phrases run real commands | Built (`src/doit`) |
| "Do what? I am waiting..." prompt | Built |
| Third-party install flow (show source URL, ask first) | Built |
| Command logging (asked once, toggle later, history) | Built |
| Yes-word settings (easy / strict / custom) | Built |
| Custom commands (user picks their own phrases) | Built |
| Create, Edit and Delete Command (delete removes the alias only) | Built |
| Database: scan of every program on this PC, with search | Built |
| Alias Maker terminal window with ☰ menu: Database, Custom Commands | Built, untested on real hardware |
| Konsole-style menu items and shortcuts (New Window, Copy, Paste, Full Screen, font size) | Built, untested on real hardware |
| Text menu (`doit menu`) | Built, kept as a backup outside the window |
| Tabs, split view, find, profiles | Not yet |
| Plain-English explanation for every scanned program | Stretch goal |
| Automatic rescan whenever pacman installs something | Later (needs a one-time admin setup) |
| Bare phrases without the `doit` prefix | Later, optional |

Tested in a Linux sandbox only so far, not yet on CachyOS or the fish shell. The engine has 55 automated tests; the scanner's manual and pacman lookups were tested with stand-ins that print the same format as the real tools. The window couldn't be opened in the sandbox (no GTK or VTE there), so its logic was checked headless with stand-in GTK widgets (52 checks) and its GTK and VTE calls were reviewed by hand. The least certain part is how the shell is started (`spawn_async`), because Python's VTE bindings have changed shape between versions; the code tries both known forms.

## Wrapper

- Typed with the `doit` prefix: `doit turn off`. Typing `doit` alone doesn't run anything, since the computer doesn't know what you want yet. It asks "Do what? I am waiting..." and keeps waiting (blank lines and unknown phrases ask again; "never mind" or Ctrl-D leaves).
- Matches exact phrases from the command index. Casual typing is tolerated: capitals, extra spaces, trailing `!`/`?`, and a "please".
- Unknown phrases get "Did you mean" suggestions but never run on a guess.
- Always shows the real command before running it.
- Translation works whether or not logging is on.

## Third-party install flow

For apps like Brave, the wrapper calls the vendor's own official install command instead of reimplementing it. Before running it:

1. Show the full source URL, highlighted.
2. Say plainly that this is the vendor's official installer, not something changed by Alias Maker.
3. Show any warning, then ask for confirmation.

Piping a remote script into a shell trusts that URL on every run, so the URL is always shown and the run is logged (when logging is on).

## Settings

- **Command logging:** asked once, the first time `doit` runs a command. Saying no still translates commands; it only skips the log file. `doit logging on|off` changes it later, and logging starts from when it's turned on. `doit show me what you did` shows the history.
- **Yes wording:** by default both `y` and `yes` work. `doit answer strict` requires the full word; `doit answer word <word>` sets a custom one.

## The window and its menu

Opening Alias Maker starts the user's login shell (fish on CachyOS) in a terminal, like Konsole. It understands `--workdir DIR` and `-e COMMAND`, the options KDE passes to a default terminal, and installs an app-launcher entry in the TerminalEmulator category so it can be picked as the default terminal.

The ☰ menu, top to bottom:

```
Database                 every program on this PC
Custom Commands  ▸       only appears once the user has made a command
    Custom Command List
    Create Command
    Edit Command
    Delete Command
Create Command
──────────
New Window               Ctrl+Shift+N
Copy                     Ctrl+Shift+C
Paste                    Ctrl+Shift+V
──────────
Full Screen Mode         F11
Enlarge Font             Ctrl++
Reset Font Size          Ctrl+Alt+0
Shrink Font              Ctrl+-
──────────
About Alias Maker
```

The menu is rebuilt each time it opens and after every create, edit or delete, so Custom Commands appears with the first command (even one made with `doit add` in the shell) and disappears again when the last one is deleted.

Copy and Paste buttons also sit in the title bar, as in Konsole. Plain Ctrl+C still goes to the shell (it stops the running program).

**Database window:** a search box, a Rescan button, and the list of programs with their descriptions. Before the first scan it shows an empty state with a "Scan My Installed Software" button. For a picked program: **Make Custom Command** (pre-fills its name so options can be added), **Read Manual** (runs `man <name>` in the terminal), **Type Into Terminal** (types the name at the prompt without running it). Shows up to 300 programs at a time; typing more words narrows it.

**Custom Commands window:** a second database that lists only the user's own commands and what they run. Buttons: **Create Command**, **Edit**, **Delete**, **Run in Terminal** (types `doit '<phrase>'` and presses Enter; the quotes keep fish and bash from treating `*`, `$` and the like specially). Opened from Edit Command or Delete Command in the menu, it shows a "pick the command you want to edit/delete" hint, and double-clicking a command does that action.

**Create/Edit dialog:** what to type, what it runs, and "Ask before running it every time" (forced on for `sudo` commands). Alias Maker's own words are refused; a phrase that's already taken shows what it runs now and needs a second Save to replace it. When editing, the command's own phrase doesn't count as a clash. Editing keeps the command's place in the list.

**Delete dialog:** says plainly that only the alias is deleted and that the program it points to stays on the computer, unchanged. Cancel has the focus, so Enter never deletes by accident.

### Deleting never touches real commands

Custom commands are entries in Alias Maker's own list (`~/.config/alias-maker/custom.json`). Deleting one removes that entry and nothing else: no program, package or system file is deleted, uninstalled or changed. An automated test checks that every other file is byte-for-byte the same after a delete. Aliases also only run after `doit`, so one can never shadow or replace a real command: an alias named `ls` leaves `ls` alone. `doit forget <phrase>` says the same thing before deleting.

**When the scan happens:** the first time the window opens (in the background, with "Scanning your installed software for the Database…" under the title), on Rescan, and after Alias Maker's own installs. `doit` never scans on its own; `doit rescan` scans on request.

The text menu (`doit menu`) still exists as a backup for terminals other than Alias Maker.

## Database: every program on this PC

The first time the Alias Maker window opens (and on Rescan, or `doit rescan`), it builds a list of every program the terminal can run, so it only lists commands that will actually work on this machine.

1. **Programs:** every runnable file in the folders listed in `PATH`.
2. **Descriptions from manuals:** each program's one-line summary from its manual page, via `whatis` (sections 1, 8 and 6 only, so C library functions with the same name are skipped).
3. **Fallback from pacman:** which package owns each program, and that package's description, for programs with no manual.

It only reads; it never runs the programs (asking each one for `--help` would mean launching thousands of programs). Without manual pages installed (`sudo pacman -S man-db man-pages`), descriptions come only from packages and are vaguer. The list is saved to `~/.local/share/alias-maker/library.json` and refreshed after Alias Maker's own installs.

**Search** matches every word against names, descriptions and package names. Exact name matches come first. It understands plurals and a small set of plain words: for example "drives" also searches for disk, block and partition, so `lsblk` ("list block devices") turns up. Easy commands that match are shown above the programs.

## Custom commands

The user picks their own phrase for any command, including profane or silly ones, with no content restrictions. `doit <their phrase>` then runs the real command, still showing it first.

- Made from the window's Custom Commands or Database, or with `doit add`. The command can come from a search of this PC (with options added, like `lsblk` + `-f`), from the easy commands, or typed by hand.
- Saved in `~/.config/alias-maker/custom.json`, separate from the shipped index, so an index update never wipes them.
- Saved as phrases inside Alias Maker, not as symlinks: a symlink can't carry options like `-f`, and a phrase with spaces can't be a single command name. Symlinks stay for one-word renames of a program (not built yet).
- Alias Maker's own words (`menu`, `list`, `search ...`, `forget ...` and so on) are reserved.
- Clashes ask first: reusing one of your phrases asks to replace it; reusing an easy-command phrase asks, and yours wins if you say yes.
- Commands using `sudo` always ask before running; others ask only if the user chose that.
- A command can have several phrases. `doit my commands` lists them; `doit forget <phrase>` removes one.
- Still to do: check custom phrases in the fish shell (special characters like `!` and `$` in a phrase), and export/share phrase packs.

## Command index

`data/commands.json` holds the easy commands: the hand-written, plain-English tier shown above the scanned programs. It's shared with a future help app and the companion book. Each entry has:

| Field | Meaning |
|---|---|
| `id` | stable identifier |
| `category` | grouping for browsing |
| `phrases` | default plain-English triggers |
| `command` | the real command that runs |
| `explanation` | plain-English description |
| `needs_root` | whether it needs elevated rights |
| `confirm` | whether to ask before running |
| `source_url` | for third-party installers, the vendor URL shown before running |
| `warning` | optional plain-English caution shown before running |

The seed entries are drafts. Verify each against the book before relying on it.

## Open questions

- **Matching strictness:** stay with exact phrases, or add loose keyword matching?
- **Teaching moments:** show the real command every time, or only the first few times a phrase is used?
- **Brave entry:** Brave's installer falls back to an AUR helper and runs `pacman -Sy --noconfirm` when Brave isn't in the regular repos. The wrapper warns about this; a better approach is still needed.
