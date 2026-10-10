# Alias Maker: design notes

Alias Maker is a terminal wrapper: you type `doit` followed by plain words, and it runs the real Linux command. `doit` is only the prefix; the tool is called Alias Maker. It was split out of [Doit-os](https://github.com/theStyleWithin/Doit-os) so the tool can be built and proven on a regular CachyOS install first. If it's stable there, it becomes Do It OS's selling point; if the distro never ships, this tool still stands on its own.

## Status

| Part | Status |
|---|---|
| Wrapper: plain-English phrases run real commands | Built (`src/doit`) |
| "Do what? I am waiting..." prompt | Built |
| Third-party install flow (show source URL, ask first) | Built |
| Command logging (asked once, toggle later, history) | Built |
| Yes-word settings (easy / strict / custom) | Built |
| Custom commands (user picks their own phrases) | Built |
| Database: scan of every program on this PC, with search | Built |
| In-terminal menu (`doit menu`) | Built |
| Plain-English explanation for every scanned program | Stretch goal |
| Window app with a clickable ☰ menu | Later (planned as the help app) |
| Automatic rescan whenever pacman installs something | Later (needs a one-time admin setup) |
| Bare phrases without the `doit` prefix | Later, optional |

Tested in a Linux sandbox only so far (46 automated tests plus real-terminal runs), not yet on CachyOS or the fish shell. The scanner's manual and pacman lookups were tested with stand-ins that print the same format as the real tools.

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

## Menu

`doit menu`, or typing `menu` at the "Do what? I am waiting..." prompt, opens a numbered menu. Konsole's own ☰ menu can't be extended by a terminal program, so the menu lives inside the terminal for now.

```
1) Database
   1) Easy commands (plain English)    browse, run, or make your own phrase for one
   2) Every command on this PC         search, read the manual, or make a custom command
   3) Custom commands (yours)          make new, run, remove
   4) Rescan this PC
2) Settings                            log on/off, yes word
3) History
```

Enter goes back a level; Ctrl-D leaves the menu entirely.

## Database: every program on this PC

On install (and on first use, and with `doit rescan`), Alias Maker builds a list of every program the terminal can run, so it only lists commands that will actually work on this machine.

1. **Programs:** every runnable file in the folders listed in `PATH`.
2. **Descriptions from manuals:** each program's one-line summary from its manual page, via `whatis` (sections 1, 8 and 6 only, so C library functions with the same name are skipped).
3. **Fallback from pacman:** which package owns each program, and that package's description, for programs with no manual.

It only reads; it never runs the programs (asking each one for `--help` would mean launching thousands of programs). Without manual pages installed (`sudo pacman -S man-db man-pages`), descriptions come only from packages and are vaguer. The list is saved to `~/.local/share/alias-maker/library.json` and refreshed after Alias Maker's own installs.

**Search** matches every word against names, descriptions and package names. Exact name matches come first. It understands plurals and a small set of plain words: for example "drives" also searches for disk, block and partition, so `lsblk` ("list block devices") turns up. Easy commands that match are shown above the programs.

## Custom commands

The user picks their own phrase for any command, including profane or silly ones, with no content restrictions. `doit <their phrase>` then runs the real command, still showing it first.

- Made with `doit add` or from the menu. The command can come from a search of this PC (with options added, like `lsblk` + `-f`), from the easy commands, or typed by hand.
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
