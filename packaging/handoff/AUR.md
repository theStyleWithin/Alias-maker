# Publishing Alias Maker on the AUR

This folder has a working `PKGBUILD` and `.SRCINFO` for the Alias Maker version it came with.
The PKGBUILD downloads the source tarball attached to that GitHub release, and installs to
`/usr/lib/alias-maker` with `aliasmaker`, `doit` and `aliasmaker-debug` in `/usr/bin`.

## First time

1. Make an account on https://aur.archlinux.org and add your SSH public key (My Account).
2. Check the name is free: https://aur.archlinux.org/packages/alias-maker
3. Edit the first line of `PKGBUILD` to your name and email, then refresh `.SRCINFO`:

       makepkg --printsrcinfo > .SRCINFO

4. Test it in a clean chroot if you can (`extra-x86_64-build` from devtools), or at least:

       makepkg -si && namcap PKGBUILD *.pkg.tar.zst

5. Publish:

       git clone ssh://aur@aur.archlinux.org/alias-maker.git
       cp PKGBUILD .SRCINFO alias-maker/
       cd alias-maker && git add PKGBUILD .SRCINFO && git commit -m "Initial upload" && git push

## Each new version

Upstream publishes a release whenever the version changes, with a new
`alias-maker-aur-handoff.tar.gz`. Either copy its PKGBUILD (keeping your Maintainer line) or
bump `pkgver`, run `updpkgsums`, and refresh `.SRCINFO`. To get told about new releases, watch
the GitHub repo (Watch → Custom → Releases).

## Notes

- `arch=('any')`: Alias Maker is Python, with nothing compiled.
- Dependencies: python, python-gobject, gtk4, vte4. fish, fastfetch, man-db, man-pages and
  xdg-utils are optional extras (listed in `optdepends`).
- Users' own commands and settings live in `~/.config/alias-maker` and
  `~/.local/share/alias-maker`, plus `~/.config/fish/conf.d/alias-maker.fish`. The package
  never touches them, and removing it leaves them alone.
