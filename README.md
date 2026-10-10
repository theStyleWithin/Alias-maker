# Alias-maker
a simplified terminal app. A terminal app that makes it easy for the most "clinically Linux challenged" person on the planet to use Linux and get the fucking job done!

## What it is

Alias Maker is its own terminal app, a window like Konsole running your normal shell. Its ☰ menu adds:

```
Database
Custom Commands  ▸   Custom Command List
                     Create Command
                     Edit Command
                     Delete Command
Create Command
Terminal Settings
```

- **Database:** every program installed on your PC in a spreadsheet-style table (Command, What it does, Package, Location), searchable by what it does ("drives", "wifi", "battery"). Click a column title to sort by it. It's empty until Alias Maker scans your installed software, which happens the first time you open it. Pick a program to read its manual, type it into the terminal, or make a custom command for it. It opens in its own window, the table builds up row by row, and it's read-only.
- **Create Command:** make your own phrase for any command, with no word restrictions. Make `just check my fucking drives` run `lsblk -f`, then type `doit just check my fucking drives` in the terminal. It always shows the real command first.
- **Custom Commands:** appears once you've made your first command. It's a second database, in the same kind of table (You type, It runs, Asks first, Made on), that lists only the commands you made, with Create, Edit and Delete. It's the one table you can edit directly: click a cell and type (Enter saves, Esc undoes), or tick and untick Asks first.

- **Terminal Settings:** turn the command log on or off, and open the **Command Log**: a table of every command doit ran (when, what you typed, the real command, whether it worked), newest first. If something gets messed up, this is where you check what happened. You also choose how to say yes here: "y or yes", only "yes", or your own word.

**Deleting a command only deletes your alias.** The real command it points to is never deleted or changed, so nothing on your computer can break. Your aliases only work after `doit`, so they can't replace or interfere with your computer's real commands either: an alias called `ls` doesn't change `ls`.

**It's yours, so it says so:** where other terminals show `fish ~`, Alias Maker says **Let'sdostuff~**, both in the title and on the line where you type:

```
Let'sdostuff~ ❯
Let'sdostuff~/Games ❯
```

Every Alias Maker window opens with a big DOIT and your PC's info next to it (from fastfetch when it's installed, as on CachyOS, or Alias Maker's own when it isn't):

```
██████╗   ██████╗  ██╗ ████████╗   you@your-pc
██╔══██╗ ██╔═══██╗ ██║ ╚══██╔══╝   OS: CachyOS
██║  ██║ ██║   ██║ ██║    ██║      CPU: …
██║  ██║ ██║   ██║ ██║    ██║      Memory: …
██████╔╝ ╚██████╔╝ ██║    ██║      Shell: fish
╚═════╝   ╚═════╝  ╚═╝    ╚═╝      Terminal: Alias Maker
```

The folder after it still tells you where you are (`~` is your home folder), and the ❯ turns red when the last command failed. It's still the same fish underneath, with all your settings, and only inside Alias Maker.

**/clippy, the helper:** type `/clippy` and what you're wondering about, and it looks it up instead of running anything:

```
Let'sdostuff~ ❯ /clippy chrooting
/clippy: Here's what I found about "chrooting". (I'm only looking it up, not running anything.)

CachyOS wiki
  1) CachyOS chroot Helper - Helper tool to make it easier to chroot into systems
     https://wiki.cachyos.org/features/cachy_chroot/

Arch Wiki
  2) Chroot
     https://wiki.archlinux.org/title/Chroot

On this PC (manual pages, work without internet)
  3) chroot - run command or interactive shell with special root directory   (manual: man chroot)

Open one? Type a number 1-3 (Enter to skip):
```

Pick a number and the page opens in your browser, or the manual opens right in the terminal. Plain questions work too: `/clippy how do I set up gaming`. Without internet it still shows what's on your PC (and wiki pages it saw before). It's not AI: it only shows real pages. `doit clippy chrooting` does the same thing.

The rest of the menu works like Konsole's: New Window, Copy, Paste, Full Screen, and font size, with the same shortcuts.

## Install

Works on a regular CachyOS install. First, the two packages the window needs (from CachyOS's official repos), plus manual pages so the Database has good descriptions:

```
sudo pacman -S vte4 python-gobject man-db man-pages
```

Then:

```
git clone https://github.com/theStyleWithin/Alias-maker.git
cd Alias-maker
./install.sh
```

The repo is private, so `git clone` will ask you to sign in to GitHub. You can also use **Code → Download ZIP** on the repo page and unzip it.

Open **Alias Maker** from your app launcher (or type `aliasmaker`). To make it your default terminal: System Settings → Default Applications → Terminal emulator → Alias Maker.

## Inside the terminal

Everything you type normally still works. `doit` runs the commands **you** make. It comes with a few built-in words so it knows how to help:

| Type | What happens |
|---|---|
| `doit` | Asks "Do what? I am waiting..." and waits for you |
| `doit <your phrase>` | Runs one of your commands |
| `<your one-word command>` | One-word commands also work on their own, like `check-drives` (see below) |
| `doit create` | Creates a command from the terminal, step by step (same as Create Command in the menu) |
| `doit forget <phrase>` or `doit delete <phrase>` | Deletes one of your commands, e.g. `doit forget just check my fucking drives`. Only your alias is deleted, never the real command |
| `/clippy <topic>` | Looks a topic up instead of running it |
| `doit help` | What doit understands, plus the example commands |
| `doit show me what you did` | Your command history, if logging is on (the full log is in ☰ → Terminal Settings) |
| `doit logging on` / `off` | Turn the command log on or off |
| `doit answer strict` | Saying yes needs the full word "yes" (`doit answer easy` goes back to y/yes) |
| `doit answer word <word>` | Pick your own yes word |

### Your commands are real terminal commands

The old-fashioned way to make a shortcut on CachyOS is to edit fish's config file by hand and add lines like `alias update='…'`. Alias Maker does that part for you: it keeps its own file, `~/.config/fish/conf.d/alias-maker.fish`, and rewrites it every time you create, edit or delete a command. Fish loads it in every terminal window, Konsole included. Your own `config.fish` and CachyOS's settings are never touched, and you never need to open the file.

One rule: **a terminal command can't have spaces.** The terminal reads the first word as the command, so `just check my fucking drives` would make it look for a program called `just`. When you name a command with spaces, Alias Maker offers one-word versions:

```
Let'sdostuff~ ❯ doit create
What command do you want it to point to? lsblk -f
Name the new command: just check my fucking drives

"just check my fucking drives" has spaces, so the terminal can't use it as a command
on its own (it would look for a program called "just"). Pick one:
  1) doit check drives                    shorter, type it with doit in front
  2) check-drives                         shorter, works on its own
  3) just-check-my-fucking-drives         your words with dashes, works on its own
  4) doit just check my fucking drives    keep it, type it with doit in front
```

- **One-word names** (like `check-drives`) work on their own and with `doit` in front.
- **Names with spaces** work with `doit` in front.
- **Names that are already taken** (a program like `ls`, a fish command like `cd`, or one of CachyOS's shortcuts like `update`) work as `doit <name>` only, so the real one is never hidden.

Shortcuts still go through Alias Maker: they show the real command first, ask before running when set to, and are logged. Extra words are passed along, so `check-drives /dev/sda` runs `lsblk -f /dev/sda`. Open a new terminal window after making a command to use it on its own.

### Example commands you can make

Alias Maker doesn't come with ready-made commands. These are examples to get you started: pick one in **Create Command** (or `doit create`), name it whatever you like, and save it.

| Example phrase | What it would run | What it does |
|---|---|---|
| `doit turn off` | `systemctl poweroff` | Shuts the computer down |
| `doit restart` | `systemctl reboot` | Restarts the computer |
| `doit disk space` | `df -h` | Shows how full each drive is |
| `doit update my system` | refreshes the signing keys, then updates everything | Updates your whole system (asks first) |
| `doit take a snapshot` | `snapper create` | Saves a restore point (asks first) |
| `doit install brave` | the installation command from Brave's own guide | Points to the Brave browser installation command in the Brave browser guide and installs Brave easily. Shows where the installer comes from and asks first |

`doit create` and `doit forget` are for anyone who'd rather get used to the terminal than use the menu. Browsing and searching the Database, and editing commands, happen in the window (☰ → Database, ☰ → Custom Commands).

Practice safely: `doit --dry-run <phrase>` shows what would run without running it.

To remove it: `rm ~/.local/bin/aliasmaker ~/.local/bin/doit ~/.local/share/applications/aliasmaker.desktop`. Your settings and custom commands live in `~/.config/alias-maker`, and the Database and log in `~/.local/share/alias-maker`.

Design notes and what's next: [docs/DESIGN.md](docs/DESIGN.md). Part of the [Do It OS](https://github.com/theStyleWithin/Doit-os) project.

To run the tests: `python3 -m unittest discover -s tests`
