#!/usr/bin/env bash
# Makes dist/alias-maker-<version>-installer.run: one file that installs Alias Maker on
# CachyOS. It carries the PKGBUILD and the source; on the user's PC it runs makepkg.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"
version=$(python3 -c "import sys; sys.path.insert(0, '$repo/src'); import aliasmaker_core as c; print(c.VERSION)")
dist="$repo/dist"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# The source as committed (so the installer matches a known commit).
git -C "$repo" archive --format=tar.gz --prefix="alias-maker-$version/" -o "$work/alias-maker-$version.tar.gz" \
    HEAD src data LICENSE README.md
sha=$(sha256sum "$work/alias-maker-$version.tar.gz" | cut -d' ' -f1)
sed -e "s/@VERSION@/$version/" -e "s/@SHA256@/$sha/" "$here/arch/PKGBUILD" > "$work/PKGBUILD"

mkdir -p "$dist"
out="$dist/alias-maker-$version-installer.run"
sed "s/@VERSION@/$version/g" "$here/installer-head.sh" > "$out"
tar -czf - -C "$work" PKGBUILD "alias-maker-$version.tar.gz" >> "$out"
chmod +x "$out"
echo "$out  (commit $(git -C "$repo" rev-parse --short HEAD))"
