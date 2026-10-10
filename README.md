# Alias-maker
a simplified terminal wrapper. A terminal wrapper that takes over your terminal it carries over an existing database of commands points the user to what does what allows the user to easily seemlessly revise the command to their preferred terminogy that they understand to get the fucking job done! 

## What it is

Alias Maker is its own terminal app, a window like Konsole running your normal shell. Its ☰ menu adds two entries:

- **Database:** every program installed on your PC, searchable by what it does ("drives", "wifi", "battery"). It's empty until Alias Maker scans your installed software, which happens the first time you open it. Pick a program to read its manual, type it into the terminal, or make a custom command for it.
- **Custom Commands:** your own phrases for any command, with no word restrictions. Make `just check my fucking drives` run `lsblk -f`, then type `doit just check my fucking drives` in the terminal. It always shows the real command first.

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
