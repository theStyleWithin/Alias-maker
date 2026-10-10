# Alias-maker
a simplified terminal wrapper. A terminal wrapper that takes over your terminal it carries over an existing database of commands points the user to what does what allows the user to easily seemlessly revise the command to their preferred terminogy that they understand to get the fucking job done! 

## Try it

Works on a regular CachyOS install. No root needed to install.

```
git clone https://github.com/theStyleWithin/Alias-maker.git
cd Alias-maker
./install.sh
```

The repo is private, so `git clone` will ask you to sign in to GitHub. You can also use **Code → Download ZIP** on the repo page and unzip it.

Practice safely first. With `--dry-run`, doit shows what it would run without running anything:

```
doit --dry-run
```

Then use it for real. Everything starts with `doit`:

| Type | What happens |
|---|---|
| `doit` | Asks "Do what? I am waiting..." and waits for you |
| `doit menu` | The menu: database, custom commands, settings, history |
| `doit turn off` | Shuts down (no question asked) |
| `doit install brave` | Shows where the installer comes from, then asks before running |
| `doit search drives` | Finds programs on this PC by what they do |
| `doit add` | Make your own phrase for any command |
| `doit my commands` | The phrases you've made |
| `doit forget <phrase>` | Remove one of your phrases |
| `doit list` | The easy commands |
| `doit rescan` | Look at what's installed again (after installing new software) |
| `doit show me what you did` | Your command history, if logging is on |
| `doit logging on` / `off` | Turn the command log on or off |
| `doit answer strict` | Saying yes needs the full word "yes" (`doit answer easy` goes back to y/yes) |
| `doit answer word <word>` | Pick your own yes word |

### Custom commands

Name any command whatever you like, with no restrictions. For example, `doit add`, then pick `lsblk` from the search, add `-f`, and call it `just check my fucking drives`. From then on, `doit just check my fucking drives` runs `lsblk -f`, and it still shows you the real command first.

### The database

When you install it, Alias Maker looks at every program on your PC and takes each one's short description from its manual. It only reads; it never runs them. Descriptions are much better with manual pages installed:

```
sudo pacman -S man-db man-pages
doit rescan
```

To remove it: `rm ~/.local/bin/doit`. Your settings and custom commands live in `~/.config/alias-maker`, and the program list and log in `~/.local/share/alias-maker`.

Design notes and what's next: [docs/DESIGN.md](docs/DESIGN.md). Part of the [Do It OS](https://github.com/theStyleWithin/Doit-os) project.

To run the tests: `python3 -m unittest discover -s tests`
