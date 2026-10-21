#!/usr/bin/env bash
# Run on Arch (the Release workflow uses an archlinux container) after build-installer.sh.
# Makes dist/alias-maker-<version>-1-any.pkg.tar.zst (install with: sudo pacman -U <file>)
# and dist/aur/: the AUR hand-off kit (PKGBUILD + .SRCINFO, source from the GitHub release).
# makepkg won't run as root, so as root this hands the work to a "builder" user.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist="$(dirname "$here")/dist"
version=$(sed -n 's/^pkgver=//p' "$dist/PKGBUILD")

run() {
    if [ "$(id -u)" = 0 ]; then
        id builder >/dev/null 2>&1 || useradd -m builder
        chown -R builder "$dist"
        su builder -c "$*"
    else
        bash -c "$*"
    fi
}

# The pacman package. -d: the PKGBUILD has nothing to build, so its dependencies aren't needed here.
run "cd '$dist' && PKGDEST='$dist' makepkg -d -f --noconfirm >/dev/null"

# The AUR's PKGBUILD downloads the same source from the GitHub release.
mkdir -p "$dist/aur"
{
    echo "# Maintainer: Your Name <you@example.com>"
    echo "# Upstream: theStyleWithin, https://github.com/theStyleWithin/Alias-maker (doesn't maintain this AUR package)"
    echo
    sed -e '1,/^$/d' \
        -e 's|^source=.*|source=("$pkgname-$pkgver.tar.gz::$url/releases/download/v$pkgver/$pkgname-$pkgver.tar.gz")|' \
        "$dist/PKGBUILD"
} > "$dist/aur/PKGBUILD"
run "cd '$dist/aur' && makepkg --printsrcinfo > .SRCINFO"
cp "$here/handoff/AUR.md" "$here/handoff/README.md" "$(dirname "$here")/LICENSE" "$dist/aur/"
ls "$dist"/alias-maker-"$version"-*.pkg.tar.zst
