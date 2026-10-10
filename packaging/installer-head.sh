#!/usr/bin/env bash
# Alias Maker @VERSION@ installer for CachyOS (and other Arch-based systems).
#
# Run it from a terminal:   bash alias-maker-@VERSION@-installer.run
# Uninstall later:          bash alias-maker-@VERSION@-installer.run --uninstall
#                           (or: sudo pacman -R alias-maker)
#
# It builds Alias Maker into a normal pacman package and installs it, so pacman
# knows about every file and can remove it cleanly. Your own commands and settings
# (~/.config/alias-maker, ~/.local/share/alias-maker) are never touched.
set -euo pipefail

VERSION="@VERSION@"
PKG="alias-maker"

say()  { printf '%s\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }
ask_yes() {  # ask_yes "question" -> true for y/yes/Enter
    local answer
    read -r -p "$1 [Y/n] " answer || return 1
    case "${answer,,}" in ""|y|yes) return 0 ;; *) return 1 ;; esac
}

if [[ "${1:-}" == "--uninstall" ]]; then
    if ! pacman -Q "$PKG" >/dev/null 2>&1; then
        say "Alias Maker isn't installed, so there's nothing to remove."
        exit 0
    fi
    bold "Removing Alias Maker. Your own commands and settings stay where they are."
    sudo pacman -R "$PKG"
    say "Done. Alias Maker is uninstalled."
    exit 0
fi

[[ $EUID -ne 0 ]] || fail "Run this as yourself, not with sudo. It asks for your password when it needs it."
command -v pacman >/dev/null 2>&1 || fail "This installer is for CachyOS and other Arch-based systems (it needs pacman)."
command -v makepkg >/dev/null 2>&1 || fail "makepkg is missing. It comes with pacman: sudo pacman -S pacman"

bold "Alias Maker $VERSION"
if installed=$(pacman -Q "$PKG" 2>/dev/null); then
    say "Already installed: $installed. This will replace it with $VERSION."
fi
say "This will:"
say "  1. Install what Alias Maker needs from CachyOS's own repos (GTK 4, VTE, PyGObject),"
say "     plus the package-building tools if they're missing"
say "  2. Build Alias Maker into a pacman package and install it"
say "You'll be asked for your password. Nothing else on your PC is changed."
say
ask_yes "Install Alias Maker?" || { say "Okay, nothing was installed."; exit 0; }

extras=()
for p in fish fastfetch man-db man-pages xdg-utils; do
    pacman -Q "$p" >/dev/null 2>&1 || extras+=("$p")
done
if ((${#extras[@]})); then
    say
    say "Recommended, not installed yet: ${extras[*]}"
    say "(fish gives the Let'sdostuff~ prompt and /clippy; man pages fill in the Database's descriptions)"
    ask_yes "Install those too?" || extras=()
fi

needs=()
pacman -Q base-devel >/dev/null 2>&1 || command -v fakeroot >/dev/null 2>&1 || needs+=(base-devel)
needs+=("${extras[@]}")
if ((${#needs[@]})); then
    say
    bold "Installing: ${needs[*]}"
    sudo pacman -S --needed --noconfirm "${needs[@]}"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
line=$(awk '/^__ALIAS_MAKER_PAYLOAD__$/ { print NR + 1; exit }' "$0")
tail -n +"$line" "$0" | tar -xz -C "$work"

say
bold "Building and installing Alias Maker..."
(cd "$work" && makepkg --syncdeps --install --noconfirm --clean)

# An older copy from install.sh (in ~/.local/bin) would be found before this one.
for name in aliasmaker doit; do
    if [[ -L "$HOME/.local/bin/$name" ]]; then
        say
        say "Note: an older Alias Maker from install.sh is still in ~/.local/bin and would run instead."
        say "Remove it with: rm ~/.local/bin/aliasmaker ~/.local/bin/doit ~/.local/share/applications/aliasmaker.desktop"
        break
    fi
done

say
bold "Alias Maker $VERSION is installed."
say "Open \"Alias Maker\" from your app launcher, or type: aliasmaker"
say "The first time it opens, it scans your installed software to fill the Database."
say "To make it your default terminal: System Settings → Default Applications → Terminal emulator → Alias Maker"
say "To uninstall: bash $(basename "$0") --uninstall   (or: sudo pacman -R alias-maker)"
exit 0
__ALIAS_MAKER_PAYLOAD__
