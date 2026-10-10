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

Then use it for real:

| Type | What happens |
|---|---|
| `doit` | Asks "Do what? I am waiting..." and waits for you |
| `doit turn off` | Shuts down (no question asked) |
| `doit install brave` | Shows where the installer comes from, then asks before running |
| `doit list` | Everything doit knows how to do |
| `doit show me what you did` | Your command history, if logging is on |
| `doit logging on` / `off` | Turn the command log on or off |
| `doit answer strict` | Saying yes needs the full word "yes" (`doit answer easy` goes back to y/yes) |
| `doit answer word <word>` | Pick your own yes word |

To remove it: `rm ~/.local/bin/doit`. Settings live in `~/.config/doit` and the log in `~/.local/share/doit`.

Design notes and what's next: [docs/DESIGN.md](docs/DESIGN.md). Part of the [Do It OS](https://github.com/theStyleWithin/Doit-os) project.

To run the tests: `python3 -m unittest discover -s tests`
