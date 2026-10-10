# Alias Maker: design notes

Alias Maker is its own terminal app (`aliasmaker`): a window like Konsole that runs the user's normal shell, with **Database**, **Custom Commands** and **Create Command** added to its ☰ menu. Inside it, you type `doit` followed by plain words and it runs the real Linux command. `doit` is only the prefix; the tool is called Alias Maker.

## Goals

**Now: make Linux easy for the average person.** The target is someone who has never opened a terminal and won't read instructions. Before anything else, Alias Maker has to clearly lower that bar. Planned, in order:

1. **First-run welcome** in the window: instead of a blank prompt, a short "here's what you can do" with things to click.
2. **Task first, not command first:** start Create Command with "What do you want to do?" and a list of plain tasks ("turn off my PC", "check my drives"), each backed by an example.
3. **Plain-words pass** on every label and message (alias, phrase, "doit only" and similar mean nothing to a beginner).
4. **More examples,** written in plain English from the companion book.
5. **Install options:** let people pick the way that suits them. `git clone` and `./install.sh` stay; easier choices can be added alongside, such as a package from the app store or an AppImage (a single file you download and run).
6. **A real test:** watch one person with no Linux experience use it unaided, and fix where they get stuck.

**Later: the default terminal in Do It OS,** shipped instead of Konsole. That will also need what people expect from a main terminal and Alias Maker doesn't have yet: tabs, split view, find, and appearance settings (font, colors). KDE's "Open Terminal Here" and similar already work through `--workdir` and `-e`, and the app-launcher entry is in the TerminalEmulator category.

## How it's built

| File | What it is |
|---|---|
| `src/aliasmaker` | The terminal window: GTK 4 with the VTE terminal widget (the engine many Linux terminals use). Needs `vte4` and `python-gobject`. |
| `src/doit` | The command typed inside the terminal. A thin launcher for the engine. |
| `src/aliasmaker_core.py` | The shared engine: custom commands, examples, the scan, search, /clippy, logging and settings. Both of the above use it, so a phrase saved in the window works with `doit` straight away. |
| `data/examples.json` | Example commands users can start from. None of them run on their own. |
| `~/.config/fish/conf.d/alias-maker.fish` | Written by Alias Maker (not in the repo): the user's one-word commands as real fish commands. |
| `src/shell/lets-do-stuff.fish` | Inside the window: fish's title and prompt say Let'sdostuff~, the welcome shows the DOIT logo, and `/clippy` is caught and sent to Alias Maker. |
| `src/shell/doit-logo.txt` | The DOIT logo shown when a terminal opens. |

The window puts `src/` first on the shell's `PATH`, so `doit` works inside Alias Maker even if it isn't installed anywhere else. It was split out of [Doit-os](https://github.com/theStyleWithin/Doit-os) so the tool can be built and proven on a regular CachyOS install first. If it's stable there, it becomes Do It OS's selling point; if the distro never ships, this tool still stands on its own.

## Status

| Part | Status |
|---|---|
| Wrapper: plain-English phrases run real commands | Built (`src/doit`) |
| Installer: one `.run` file that builds and installs a pacman package (`packaging/`) | Built; the package layout, the installed copy and the installer's steps were tested, but pacman and makepkg themselves only run on a real Arch/CachyOS PC |
| Six ready-made commands turned into examples (no built-in phrases) | Built |
| One-word commands become real fish commands (Alias Maker's conf.d file), with naming help; they work at once in open Alias Maker windows | Built; the fish side tested with real fish 4.0 |
| "Do what? I am waiting..." prompt | Built |
| Third-party install flow (show source URL, ask first) | Built |
| Command logging (asked once, toggle later, history) | Built |
| Yes-word settings (easy / strict / custom) | Built |
| Custom commands (user picks their own phrases) | Built |
| Create, Edit and Delete Command (delete removes the alias only) | Built |
| Spreadsheet-style tables for the Database and Custom Command List | Built, untested on real hardware |
| Tables open in their own window and build up gradually | Built, untested on real hardware |
| Edit Custom Commands directly in the table (Database stays read-only) | Built, untested on real hardware |
| Title and prompt say Let'sdostuff~ instead of fish ~ (fish only) | Built, untested on real hardware |
| /clippy lookups: CachyOS wiki, Arch Wiki (best effort), manual pages | Built; tested against a stand-in wiki and with real fish 4.0, untested against the real sites |
| Database: scan of every program on this PC, with search | Built |
| Alias Maker terminal window with ☰ menu: Database, Custom Commands | Built, untested on real hardware |
| Konsole-style menu items and shortcuts (New Window, Copy, Paste, Full Screen, font size) | Built, untested on real hardware |
| Text menu (`doit menu`), terminal search (`doit search`), `doit my commands`, `doit rescan` | Removed: the window's ☰ menu and Database replace them |
| Terminal Settings in the ☰ menu: command log switch, Command Log table, yes word | Built, untested on real hardware |
| Terminal commands kept for people learning the terminal: `doit create`, `doit forget`/`doit delete` | Built |
| Tabs, split view, find, profiles | Not yet |
| Plain-English explanation for every scanned program | Stretch goal |
| Automatic rescan whenever pacman installs something | Later (needs a one-time admin setup) |
| Bare phrases without the `doit` prefix | Later, optional |

Tested in a Linux sandbox only so far, not yet on CachyOS or the fish shell. The engine has 71 automated tests; the scanner's manual and pacman lookups were tested with stand-ins that print the same format as the real tools. The window couldn't be opened in the sandbox (no GTK or VTE there), so its logic was checked headless with stand-in GTK widgets (122 checks) and its GTK and VTE calls were reviewed by hand. The least certain part is how the shell is started (`spawn_async`), because Python's VTE bindings have changed shape between versions; the code tries both known forms.

## Wrapper

- Typed with the `doit` prefix: `doit <your phrase>`. Alias Maker ships with no ready-made phrases; `doit` runs only the commands the user made, plus its own built-in words (`create`, `forget`/`delete`, `help`, `clippy`, `logging`, `answer`, `show me what you did`). Typing `doit` alone doesn't run anything, since the computer doesn't know what you want yet. It asks "Do what? I am waiting..." and keeps waiting (blank lines and unknown phrases ask again; "never mind" or Ctrl-D leaves).
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

**Let'sdostuff~ instead of fish ~.** "fish ~" means nothing to someone new to Linux, so inside Alias Maker the terminal says Let'sdostuff instead, in the title and on the prompt line. When the shell is fish, Alias Maker starts it with `--init-command "source src/shell/lets-do-stuff.fish"`. Fish runs that after the user's own config, and it defines these:

- `fish_title`: `Let'sdostuff~` in the home folder, `Let'sdostuff~/Games` elsewhere, `Let'sdostuff~ : htop` while a program runs.
- `fish_prompt`: `Let'sdostuff~ ❯ ` with the full folder after the name; the ❯ turns red after a failed command. This replaces the user's fish prompt inside Alias Maker only.

- `fish_greeting`: shows Alias Maker's welcome (`doit --welcome`) instead of CachyOS's plain `fastfetch`.

Everything else about fish (settings, functions, right-hand prompt) is unchanged, and other terminals are unaffected. The name comes from `$ALIASMAKER_NAME`, which the window sets, so it could become a setting later. Other shells (bash, zsh) start as they are for now. The window reads the title through VTE's older `window-title-changed` signal or the newer `termprop-changed` one, whichever exists. Fish couldn't be run in the build sandbox, so the script was checked by hand.

**The DOIT welcome.** Every Alias Maker window opens with a big block-letter DOIT (`src/shell/doit-logo.txt`) and the PC's info beside it, the way CachyOS shows its logo. `doit --welcome` makes it: with fastfetch installed (CachyOS ships it) it runs `fastfetch --logo doit-logo.txt --logo-type file --logo-color-1 96`, so the logo is swapped and fastfetch's full info stays. Inside the window it also passes `--config` with Alias Maker's own module list (`fastfetch-welcome.jsonc` in the data folder) whose Terminal line says `aliasmaker`: the app is Python underneath, so fastfetch would otherwise say `python3`, and newer fastfetch only takes that through a config file. `doit --welcome` replaces itself with fastfetch so fastfetch sees fish as its parent and reports the right shell. The window also names its own process `aliasmaker` (for btop, htop and ps) and sets `TERM_PROGRAM=aliasmaker`; without fastfetch, or if it fails, Alias Maker prints its own info next to DOIT: user@host, OS, kernel, uptime, shell, terminal, CPU, memory and disk, read from `/etc/os-release` and `/proc`. With fish, the welcome comes from `fish_greeting`; with other shells, the window writes it before starting the shell, so it's shown once either way. Konsole keeps the CachyOS logo.

Mockup: [welcome.png](mockups/welcome.png)

**/clippy.** Typing `/clippy <topic>` in the Alias Maker window looks the topic up and never runs it. `/clippy` is a fish abbreviation (`abbr --position command --regex '^/clippy$'`, fish 3.6 and newer): it turns into `doit clippy` when space or Enter is pressed, and fish colors it as a known command instead of red. As a backup for older fish, `fish_command_not_found` also catches `/clippy` and runs `doit clippy <topic>`, and passes anything else to the handler that was there before (CachyOS's or fish's own). Fish function names can't contain `/`, so a function isn't possible. The slash word is one setting (`HELPER_NAME`).

Mockups: [clippy-typing.png](mockups/clippy-typing.png), [clippy.png](mockups/clippy.png)

What it searches:

1. **CachyOS wiki.** Alias Maker keeps a list of the wiki's English pages (title and one-line description) in `~/.local/share/alias-maker/cachyos-wiki.json`. It builds it from the wiki's sitemap (translated pages under `/bg/`, `/de/` and so on are skipped) and refreshes it when it's a week old. Matching uses titles, descriptions and page addresses, not the full page text.
2. **Arch Wiki,** best effort, through its search API. The Arch Wiki is behind bot protection, which blocked lookups from the build sandbox, so this may come back empty; it fails quietly.
3. **Manual pages on this PC,** from the Database (needs a scan with manual pages installed).

Words are matched forgivingly: endings are trimmed (chrooting → chroot, mounted → mount), the Database's synonyms apply (drives → disk, partition…), and filler words like "how do I" are ignored. Results are numbered; picking a web page opens it with `xdg-open`, picking a manual runs `man`. Offline, it says so and still shows saved wiki pages and manuals. It's not AI and never invents an answer.

The name `/clippy` was the author's choice. Microsoft owns the Clippy character and trademark; the command uses only the word, with no Clippy artwork.

The ☰ menu, top to bottom. Custom Commands opens to the side of the menu, like Konsole's submenus (a `Gtk.PopoverMenu` with the NESTED flag), instead of GTK's default of sliding the whole menu over (mockup: [menu.png](mockups/menu.png)):

```
Database                 every program on this PC
Custom Commands  ▸       only appears once the user has made a command; opens to the side
    Custom Command List
    Create Command
    Edit Command
    Delete Command
Create Command
Terminal Settings        the command log and how to say yes
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

The menu is rebuilt each time it opens and after every create, edit or delete, so Custom Commands appears with the first command (even one made with `doit create` in the shell) and disappears again when the last one is deleted.

Copy and Paste buttons also sit in the title bar, as in Konsole. Plain Ctrl+C still goes to the shell (it stops the running program).

**Database window:** a search box, a Rescan button, and every program on this PC in a spreadsheet-style table. Before the first scan it shows an empty state with a "Scan My Installed Software" button. For a picked program: **Make Custom Command** (pre-fills its name so options can be added), **Read Manual** (runs `man <name>` in the terminal), **Type Into Terminal** (types the name at the prompt without running it). Double-clicking a program also makes a custom command.

Mockup: [database.png](mockups/database.png)

**Tables.** The Database and the Custom Command List are GTK column views drawn like a spreadsheet: a border around the table, a line between every row and every column, bold column titles and even padding in each cell. Rows are all the same height: long text ends in "…" and hovering shows all of it. Columns can be resized, and clicking a title sorts by that column. The table only draws the rows on screen, so all ~2,000 programs are listed with no cap.

| Table | Columns |
|---|---|
| Database | Command · What it does · Package · Location |
| Custom Command List | You type (after doit) · It runs · Asks first · Made on |

With no search, the Database is listed A to Z; with a search, best matches come first (until a column title is clicked).

**Opening and filling.** The Database and the Custom Command List each open in their own window (not pinned on top of the terminal). Every time one opens, its table builds up gradually: rows arrive in steps over about 1.2 seconds whatever their number (a short list appears one row at a time, about 90 ms apart; ~2,000 programs arrive in about 40 batches), with "Loading 1,200 of 1,863…" under the table. Searches and edits update instantly. If the desktop's animations are turned off, rows appear at once.

**Only Custom Commands can be edited.** The Database is read-only: its cells are plain labels. In the Custom Command List, the "You type" and "It runs" cells are text cells: click one and type, then Enter or clicking away saves and Esc undoes. "Asks first" is a checkbox. Each change follows the same rules as the Edit dialog: empty values, Alias Maker's own words and phrases already in use are refused, with the old value put back and a message saying why; a `sudo` command always asks first, so typing one ticks the box and unticking it is refused. "Made on" can't be edited.

**Custom Commands window:** a second database, in the same kind of table, that lists only the user's own commands and what they run. Buttons: **Create Command**, **Edit**, **Delete**, **Run in Terminal** (types `doit '<phrase>'` and presses Enter; the quotes keep fish and bash from treating `*`, `$` and the like specially). Opened from Edit Command or Delete Command in the menu, it shows a "pick the command you want to edit/delete" hint, and double-clicking a command does that action.

Mockup: [custom-commands.png](mockups/custom-commands.png)

**Create/Edit dialog:** what to type, what it runs, and "Ask before running it every time" (forced on for `sudo` commands). Alias Maker's own words are refused; a phrase that's already taken shows what it runs now and needs a second Save to replace it. When editing, the command's own phrase doesn't count as a clash. Editing keeps the command's place in the list.

Mockup: [create-command.png](mockups/create-command.png)

**Terminal Settings window:** a switch for the command log ("On: commands are being recorded" / "Off" / "Off (not chosen yet)"), a **View Command Log** button, and how to say yes: "y or yes", "Only the full word yes", or "My own word" (one word, no spaces). Settings are read fresh each time it opens, since `doit logging` and `doit answer` in the terminal change the same file. Turning the log off keeps what's already recorded.

Mockup: [terminal-settings.png](mockups/terminal-settings.png)

**Command Log window:** the log (`~/.local/share/alias-maker/command-log.tsv`) as a read-only table, newest first: When · You typed · Real command · Result ("Worked" or "Failed (code 3)"). It builds up gradually when it opens, like the other tables; the footer counts commands and failures and shows the file's location. **Open Log File** opens the raw file; **Refresh** reloads. With the log off and nothing recorded, it says where to turn it on. The point is troubleshooting: if something goes wrong, users can see exactly what ran.

Mockup: [command-log.png](mockups/command-log.png)

**Delete dialog:** says plainly that only the alias is deleted and that the program it points to stays on the computer, unchanged. Cancel has the focus, so Enter never deletes by accident.

Mockup: [delete-command.png](mockups/delete-command.png)

### Deleting never touches real commands

Custom commands are entries in Alias Maker's own list (`~/.config/alias-maker/custom.json`). Deleting one removes that entry and nothing else: no program, package or system file is deleted, uninstalled or changed. An automated test checks that every other file is byte-for-byte the same after a delete. Aliases also only run after `doit`, so one can never shadow or replace a real command: an alias named `ls` leaves `ls` alone. `doit forget <phrase>` (or `doit delete <phrase>`) says the same thing before deleting.

**When the scan happens:** the first time the window opens (in the background, with "Scanning your installed software for the Database…" under the title), on Rescan (a button in the Database window), and after Alias Maker's own installs. `doit` never scans.

There's no text menu and no `doit search`: the window's ☰ menu and Database search box are the way in.

## Database: every program on this PC

The first time the Alias Maker window opens (and on Rescan in the Database window), it builds a list of every program the terminal can run, so it only lists commands that will actually work on this machine.

1. **Programs:** every runnable file in the folders listed in `PATH`.
2. **Descriptions from manuals:** each program's one-line summary from its manual page, via `whatis` (sections 1, 8 and 6 only, so C library functions with the same name are skipped).
3. **Fallback from pacman:** which package owns each program, and that package's description, for programs with no manual.

It only reads; it never runs the programs (asking each one for `--help` would mean launching thousands of programs). Without manual pages installed (`sudo pacman -S man-db man-pages`), descriptions come only from packages and are vaguer. The list is saved to `~/.local/share/alias-maker/library.json` and refreshed after Alias Maker's own installs.

**Search** matches every word against names, descriptions and package names, and ranks the results. Each word scores a program: the name is the word (best); it's one of the usual picks for that word (`COMMON_PICKS`: "drives" → lsblk, df, findmnt, blkid…; "wifi" → nmcli, nmtui, iwctl…); the name starts with or contains it; the description says it; and last, only a synonym matched. Best total first, then shorter names. It understands plurals and a small set of plain words: for example "drives" also searches for disk, block and partition. A new search goes back to best-first even if a column was clicked before.

## Real terminal commands (the fish file)

On CachyOS, shortcuts are normally made by hand: `~/.config/fish/config.fish` loads CachyOS's own `/usr/share/cachyos-fish-config/cachyos-config.fish`, which is full of lines like `alias update='sudo cachyos-rate-mirrors && sudo pacman -Syu'`. Alias Maker replaces that hand-editing.

- It owns `~/.config/fish/conf.d/alias-maker.fish`. Fish loads every file in `conf.d` on its own, so the user's `config.fish` and CachyOS's file are never touched.
- The file is rewritten from the saved commands every time one is created, edited or deleted (anything that saves `custom.json`, from the window or `doit`), and whenever the window opens. Its header says it's made by Alias Maker and shouldn't be edited by hand.
- Each one-word command becomes a fish function that runs `doit --alias <name> -- $argv` (by its full path, so it works even if `doit` isn't on `PATH`). So it still shows the real command, asks first when set to, and is logged, and extra words are passed along, safely quoted.
- **Names with spaces** can't be terminal commands (the first word would be taken as the program), so they work with `doit` in front only. `doit create` and the Create Command window offer one-word versions: a shorter one (first and last meaningful word, filler like "just" and "my" dropped: `check-drives`) and the full phrase with dashes (`just-check-my-fucking-drives`), plus a shorter `doit` phrase or keeping it as typed.
- **Names already taken** are never written, so nothing real is hidden: programs on `PATH`, fish's own commands and keywords, names defined in CachyOS's fish config or the user's `config.fish`, and functions in `~/.config/fish/functions/`. Those commands work as `doit <name>`. (Fish loads `conf.d` before `config.fish`, so CachyOS's aliases would win anyway.)
- Deleting a command removes its function from the file; the program it pointed to is untouched.
- **Works right away in Alias Maker.** The file ends with `set -g __aliasmaker_shortcut_names ...`. Before each prompt, the window's fish script checks whether the file changed and, if so, erases the old names and loads it again, so a command made, renamed or deleted (in the window or with `doit create`) takes effect in every open Alias Maker window. If the command is typed at a prompt that was already waiting, the not-found handler reloads and runs it. Other terminals pick it up in a new window, and `doit create` says which applies.

  Mockup: [doit-create.png](mockups/doit-create.png)
- The Custom Commands table shows this in a "Works on its own" column (the name, or "doit only").

`doit create` now asks "What command do you want it to point to?" first (type it, or press Enter to search this PC or start from an example), then "Name the new command:".

## Custom commands

The user picks their own phrase for any command, including profane or silly ones, with no content restrictions. `doit <their phrase>` then runs the real command, still showing it first.

- Made from the window's Custom Commands or Database, or with `doit create` in the terminal. The command can come from a search of this PC (with options added, like `lsblk` + `-f`), from an example, or typed by hand.
- Saved in `~/.config/alias-maker/custom.json`, separate from the shipped index, so an index update never wipes them.
- Saved as phrases inside Alias Maker, not as symlinks: a symlink can't carry options like `-f`, and a phrase with spaces can't be a single command name. Symlinks stay for one-word renames of a program (not built yet).
- Alias Maker's own words (`menu`, `list`, `search ...`, `forget ...` and so on) are reserved.
- Clashes ask first: reusing one of your phrases asks to replace it.
- Commands using `sudo` always ask before running; others ask only if the user chose that.
- A command can have several phrases. The window's Custom Commands lists them; `doit forget <phrase>` or `doit delete <phrase>` removes one from the terminal.
- Still to do: check custom phrases in the fish shell (special characters like `!` and `$` in a phrase), and export/share phrase packs.

## Example commands

Alias Maker ships with no ready-made commands: `doit turn off` does nothing until the user makes it. `data/examples.json` holds examples instead, offered as starting points in the Create Command window ("Start from an example" dropdown) and in `doit create`, and listed by `doit help` and the README:

| Example | Command |
|---|---|
| turn off | `systemctl poweroff` |
| restart | `systemctl reboot` |
| disk space | `df -h` |
| update my system | `sudo pacman -Sy --needed archlinux-keyring cachyos-keyring && sudo pacman -Su` |
| take a snapshot | `sudo snapper create --description "alias maker snapshot"` |
| install brave | `curl -fsS https://dl.brave.com/install.sh \| sh` |

Picking one fills in the phrase, the command and "Ask before running it"; the user can rename it or change anything. Each example has `id`, `phrase`, `command`, `explanation`, `confirm`, and optionally `source_url` and `warning`. A command made from an example keeps the example's explanation, source link and warning (so the Brave installer's address and AUR warning are still shown before it runs) as long as its command stays the same; changing the command drops them. Example phrases aren't reserved: they're free for the user to take.

The examples are drafts. Verify each against the book before relying on it.

## Open questions

- **Matching strictness:** stay with exact phrases, or add loose keyword matching?
- **Teaching moments:** show the real command every time, or only the first few times a phrase is used?
- **Brave entry:** Brave's installer falls back to an AUR helper and runs `pacman -Sy --noconfirm` when Brave isn't in the regular repos. The wrapper warns about this; a better approach is still needed.
