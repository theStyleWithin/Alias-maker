#!/usr/bin/env bash
# After build-installer.sh: makes dist/alias-maker-flathub-handoff.tar.gz from
# packaging/handoff/, filled in for this version. (The AUR kit is made by build-arch.sh.)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dist="$(dirname "$here")/dist"
version=$(sed -n 's/^pkgver=//p' "$dist/PKGBUILD")
sha=$(sha256sum "$dist/alias-maker-$version.tar.gz" | cut -d' ' -f1)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

kit="$work/alias-maker-flathub-handoff"
mkdir -p "$kit"
for file in "$here"/handoff/flathub/*; do
    sed -e "s/@VERSION@/$version/g" -e "s/@SHA256@/$sha/g" -e "s/@DATE@/$(date -u +%F)/g" \
        "$file" > "$kit/$(basename "$file")"
done
cp "$here/handoff/README.md" "$kit/README.md"
cp "$here/appimage/alias-maker.svg" "$kit/alias-maker.svg"
cp "$(dirname "$here")/LICENSE" "$kit/LICENSE"
tar -czf "$dist/alias-maker-flathub-handoff.tar.gz" -C "$work" alias-maker-flathub-handoff
echo "$dist/alias-maker-flathub-handoff.tar.gz"
