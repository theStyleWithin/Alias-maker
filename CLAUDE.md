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
- The engine is tested. The window runs on Ubuntu 24.04 (GTK 4.14, VTE 0.76, fish 3.7) under Xvfb but hasn't been tried on CachyOS yet. To test the window in a sandbox: `apt-get install gir1.2-gtk-4.0 gir1.2-vte-3.91 fish xdotool`, run it with `python3.12` (the system PyGObject) and `GSK_RENDERER=cairo` under `xvfb-run`, and screenshot with `import -window root`.
- Releases: bump `VERSION` in `src/aliasmaker_core.py`; on `main`, `.github/workflows/release.yml` tests, builds and publishes the installer, pacman package, AppImages (app + Debug) and AUR files, and pushes to the AUR when the `AUR_SSH_PRIVATE_KEY` secret exists. Don't commit built files.
- AppImages use the host's Python/GTK 4/VTE (nothing bundled). From an AppImage, one-word fish commands call `$APPIMAGE doit` (`doit_command()`), since the AppImage's own folder vanishes when it closes.
- Flatpak/Flathub isn't done: the sandbox would need `flatpak-spawn --host` for the shell, the scan and doit.
- Known gaps: commands run through `sh` (`subprocess.run(..., shell=True)`), not fish, so fish aliases/syntax fail; the forced "ask first" check only looks for the word `sudo` (misses `doas`, `pkexec`, `run0`, `&&sudo`).

## Rules
- Never delete or change the real program a command points to; deleting only edits `~/.config/alias-maker/custom.json`.
- Never write a shortcut that hides a real program, fish built-in or CachyOS alias.
- Always show the real command before running it, and never run an unknown phrase on a guess.
- Keep user-facing text in plain words for someone new to Linux.
- Update the Status table in `docs/DESIGN.md` when something gets built or tested.
