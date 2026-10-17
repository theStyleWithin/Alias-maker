# Alias Maker

A beginner-friendly terminal app (GTK 4 + VTE window) plus the `doit` command, for CachyOS with fish. Python 3, no third-party packages beyond PyGObject/VTE.

Current goal: get it working and usable on a real CachyOS PC. Prefer fixing and finishing what exists over adding features.

## Layout
- `src/aliasmaker_core.py`: the engine (custom commands, fish shortcut file, Database scan/search, /clippy, logging, settings). Both the window and `doit` use it.
- `src/aliasmaker`: the GTK 4/VTE window and its ☰ menu.
- `src/doit`: thin launcher for the engine.
- `src/shell/lets-do-stuff.fish`: prompt, title, welcome and /clippy inside the window.
- `packaging/`: installer `.run` builder and Arch PKGBUILD.
- `docs/DESIGN.md`: full design and status. Read only the sections the task needs.

## Commands
- Tests: `python3 -m unittest discover -s tests` (fish tests skip if fish isn't installed)
- Try the engine safely: `src/doit --dry-run <phrase>`

## Status
- The engine is tested. The window has never run on real hardware (no GTK/VTE in the sandbox), so treat window code as unverified. The shell start (`spawn_async`) is the least certain part.
- Known gaps: commands run through `sh` (`subprocess.run(..., shell=True)`), not fish, so fish aliases/syntax fail; the forced "ask first" check only looks for the word `sudo` (misses `doas`, `pkexec`, `run0`, `&&sudo`).

## Rules
- Never delete or change the real program a command points to; deleting only edits `~/.config/alias-maker/custom.json`.
- Never write a shortcut that hides a real program, fish built-in or CachyOS alias.
- Always show the real command before running it, and never run an unknown phrase on a guess.
- Keep user-facing text in plain words for someone new to Linux.
- Update the Status table in `docs/DESIGN.md` when something gets built or tested.
