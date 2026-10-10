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
```

- **Database:** every program installed on your PC in a spreadsheet-style table (Command, What it does, Package, Location), searchable by what it does ("drives", "wifi", "battery"). Click a column title to sort by it. It's empty until Alias Maker scans your installed software, which happens the first time you open it. Pick a program to read its manual, type it into the terminal, or make a custom command for it. It opens in its own window, the table builds up row by row, and it's read-only.
- **Create Command:** make your own phrase for any command, with no word restrictions. Make `just check my fucking drives` run `lsblk -f`, then type `doit just check my fucking drives` in the terminal. It always shows the real command first.
- **Custom Commands:** appears once you've made your first command. It's a second database, in the same kind of table (You type, It runs, Asks first, Made on), that lists only the commands you made, with Create, Edit and Delete. It's the one table you can edit directly: click a cell and type (Enter saves, Esc undoes), or tick and untick Asks first.

**Deleting a command only deletes your alias.** The real command it points to is never deleted or changed, so nothing on your computer can break. Your aliases only work after `doit`, so they can't replace or interfere with your computer's real commands either: an alias called `ls` doesn't change `ls`.

**It's yours, so it says so:** where other terminals show `fish ~`, Alias Maker says **Let'sdostuff~**, both in the title and on the line where you type:

```
Let'sdostuff~ ❯
Let'sdostuff~/Games ❯
```

The folder after it still tells you where you are (`~` is your home folder), and the ❯ turns red when the last command failed. It's still the same fish underneath, with all your settings, and only inside Alias Maker.

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

Everything you type normally still works. `doit` adds plain-English commands:

| Type | What happens |
|---|---|
| `doit` | Asks "Do what? I am waiting..." and waits for you |
| `doit turn off` | Shuts down (no question asked) |
| `doit install brave` | Shows where the installer comes from, then asks before running |
| `doit <your phrase>` | Runs one of your custom commands |
| `doit search drives` | Searches the Database from the terminal |
| `doit list` | The easy commands |
| `doit show me what you did` | Your command history, if logging is on |
| `doit logging on` / `off` | Turn the command log on or off |
| `doit answer strict` | Saying yes needs the full word "yes" (`doit answer easy` goes back to y/yes) |
| `doit answer word <word>` | Pick your own yes word |

`doit add`, `doit my commands`, `doit forget <phrase>`, `doit rescan` and a text menu (`doit menu`) also exist as backups for when you're not in the Alias Maker window.

Practice safely: `doit --dry-run <phrase>` shows what would run without running it.

To remove it: `rm ~/.local/bin/aliasmaker ~/.local/bin/doit ~/.local/share/applications/aliasmaker.desktop`. Your settings and custom commands live in `~/.config/alias-maker`, and the Database and log in `~/.local/share/alias-maker`.

Design notes and what's next: [docs/DESIGN.md](docs/DESIGN.md). Part of the [Do It OS](https://github.com/theStyleWithin/Doit-os) project.

To run the tests: `python3 -m unittest discover -s tests`
