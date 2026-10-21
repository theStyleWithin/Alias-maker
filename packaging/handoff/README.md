# Alias Maker: hand-off kits for the AUR and Flathub

**Wanted: someone to package Alias Maker for the AUR and/or Flathub.**

The author of Alias Maker doesn't publish on the AUR or Flathub and won't be maintaining
packages there. These kits are a head start for anyone who wants to. You maintain the
package under your own account; you don't need to ask first.

- **Permission:** Alias Maker is under the Apache License 2.0 (see `LICENSE`). You may
  package, rebuild and redistribute it, including adjusting the package description to
  fit a platform's rules, as long as you keep the license and credit the project.
- **Upstream:** https://github.com/theStyleWithin/Alias-maker. Every release there carries
  ready-made kits filled in for that version:
  - `alias-maker-aur-handoff.tar.gz`: a working PKGBUILD and .SRCINFO, plus `AUR.md`
  - `alias-maker-flathub-handoff.tar.gz`: a Flatpak manifest, metainfo, desktop file and
    icon, plus `PORTING.md`
- **Bugs:** report Alias Maker bugs upstream (GitHub issues, with a report from Alias Maker
  Debug). Packaging bugs are yours.

| Platform | State of the kit |
|---|---|
| AUR | Ready. The PKGBUILD is the one upstream builds and installs with, pointed at the release's source tarball. Put your name in the Maintainer line and push. |
| Flathub | Needs work. The manifest builds the app, but Alias Maker is a terminal for the real system, so it needs a few code changes to run its shell and commands outside the Flatpak sandbox. `PORTING.md` lists them. |

The templates live in `packaging/handoff/` in the repo; `packaging/build-handoff.sh` fills in
the version and checksum for each release.
