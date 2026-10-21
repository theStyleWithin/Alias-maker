#!/usr/bin/env bash
# Makes dist/Alias-Maker-x86_64.AppImage and dist/Alias-Maker-Debug-x86_64.AppImage from the
# last commit. Both carry their own Python, GTK 4, VTE and fish (see appimage/make-bundle.sh),
# so there's nothing to install and nothing to ask. Build on Ubuntu 24.04 (the Release workflow
# does); the packages make-bundle.sh needs are listed there.
# Needs appimagetool (downloaded into dist/ if APPIMAGETOOL isn't set).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"
version=$(python3 -c "import sys; sys.path.insert(0, '$repo/src'); import aliasmaker_core as c; print(c.VERSION)")
dist="$repo/dist"
mkdir -p "$dist"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

tool="${APPIMAGETOOL:-$dist/appimagetool}"
if [ ! -x "$tool" ]; then
    curl -fsSL -o "$tool" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$tool"
fi
export APPIMAGE_EXTRACT_AND_RUN=1  # build machines often have no FUSE

# Everything both AppImages share: the bundle, Alias Maker's files, a doit that brings its Python
bundle="$work/bundle"
bash "$here/appimage/make-bundle.sh" "$bundle" >/dev/null
mkdir -p "$bundle/usr/lib/alias-maker/bin" "$bundle/usr/lib/gio-modules"
git -C "$repo" archive HEAD src data LICENSE | tar -x -C "$bundle/usr/lib/alias-maker"
cat > "$bundle/usr/lib/alias-maker/bin/doit" <<'SHIM'
#!/bin/sh
exec "$(dirname "$(readlink -f "$0")")/../../../../AppRun" doit "$@"
SHIM
chmod +x "$bundle/usr/lib/alias-maker/bin/doit"
# Compiled ahead of time, because the AppImage is read-only: faster to open
"$bundle/usr/bin/python3" -m compileall -q --invalidation-mode unchecked-hash \
    "$bundle/usr/lib/python3.12" "$bundle/usr/lib/python3" "$bundle/usr/lib/alias-maker/src" >/dev/null || true

build() {  # build <file name> <program it opens> <app name> <comment> <categories>
    local dir="$work/$1.AppDir"
    cp -a "$bundle" "$dir"
    sed "s/@DEFAULT@/$2/" "$here/appimage/AppRun" > "$dir/AppRun"
    chmod +x "$dir/AppRun"
    cp "$here/appimage/alias-maker.svg" "$dir/alias-maker.svg"
    cat > "$dir/$2.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$3
Comment=$4
Exec=$2
Icon=alias-maker
Terminal=false
Categories=$5
X-AppImage-Version=$version
DESKTOP
    ARCH=x86_64 VERSION="$version" "$tool" -n --comp zstd "$dir" "$dist/$1-x86_64.AppImage" >/dev/null
    rm -rf "$dir"
    echo "$dist/$1-x86_64.AppImage"
}

build Alias-Maker aliasmaker "Alias Maker" \
    "A terminal with a database of your programs and your own plain-English commands" \
    "System;TerminalEmulator;"
build Alias-Maker-Debug aliasmaker-debug "Alias Maker Debug" \
    "Crash reports and a health check for Alias Maker, to send to the developer" \
    "System;Utility;"
