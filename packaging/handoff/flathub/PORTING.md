# Porting Alias Maker to Flatpak

The manifest builds Alias Maker, but as-is it would run fish, doit and the user's commands
**inside** the sandbox, where the user's real programs aren't. Alias Maker is a terminal for
the real system, so these places need to reach the host. Like other Flathub terminals, use
`flatpak-spawn --host` (allowed by `--talk-name=org.freedesktop.Flatpak`). Detect the
sandbox with `os.path.exists("/.flatpak-info")`.

Line numbers are for version @VERSION@.

1. **Starting the shell** (`src/aliasmaker`: `user_shell()` around line 82, `shell_argv()`
   around line 93, the spawn around line 625). Find the host shell with
   `flatpak-spawn --host getent passwd $USER`, then start it as
   `flatpak-spawn --host --watch-bus --directory=<folder> --env=TERM=xterm-256color
   --env=PATH=<host PATH plus the folder from step 2> <shell> ...`. Check job control and
   window resizing in a real session.

2. **Files the host shell uses.** The fish script (`FISH_TITLE_SCRIPT`, line 67), `doit` and
   the engine live in `/app`, which the host can't see. Copy `src/` once per version to a
   host-visible folder (e.g. `~/.local/share/alias-maker/host/`), and use that copy for the
   `--init-command` path and for the `PATH` set around line 597. They're plain Python and
   run with the host's `python3`.

3. **One-word commands** (`src/aliasmaker_core.py`, `doit_command()` around line 463). The
   fish file must point at the host copy from step 2, not `/app/...`.

4. **Running commands** (`run_entry()`, the `subprocess.run(..., shell=True)` around line
   2000). This only runs on the host once steps 1–2 are done (doit then runs on the host).
   Make sure no code path runs doit inside the sandbox.

5. **The Database scan** (`scan_library()` around line 810, the PATH walk around line 685,
   `whatis` around line 710, `pacman` around line 783; Ubuntu uses `dpkg_package_info()`). Run these with
   `flatpak-spawn --host`, or read programs from `/run/host/usr/bin`.

6. **Alias Maker Debug's health check** (`src/aliasmaker_crash.py`, `health_check()`) checks
   the sandbox's GTK, VTE and fish. Report the host's fish instead.

Upstream's own tests: `python3 -m unittest discover -s tests`. If you'd like these changes
upstream, open a pull request on GitHub.

Before submitting, follow https://docs.flathub.org/docs/for-app-authors/submission:
replace the empty `<screenshots>` in the metainfo with real ones, pin the vte source to a
commit, and run `flatpak run --command=flathub-build org.flatpak.Builder --install
io.github.thestylewithin.AliasMaker.yml` plus the linter. Flathub reviewers will ask about
`--talk-name=org.freedesktop.Flatpak` and `--filesystem=home`: both are needed because it's
a terminal for the host, like other terminals on Flathub.
