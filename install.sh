#!/usr/bin/env bash
# Installs Alias Maker for the current user only. No root needed.
#   aliasmaker  the terminal window (in your app launcher as "Alias Maker")
#   doit        the prefix you type inside it: doit <phrase>
# Uninstall: rm ~/.local/bin/aliasmaker ~/.local/bin/doit ~/.local/share/applications/aliasmaker.desktop
# (your data: ~/.config/alias-maker and ~/.local/share/alias-maker)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="$HOME/.local/bin"
apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Alias Maker needs python3. Install it with: sudo pacman -S python"
    exit 1
fi

mkdir -p "$bin_dir" "$apps_dir"
chmod +x "$repo/src/aliasmaker" "$repo/src/doit"
ln -sf "$repo/src/aliasmaker" "$bin_dir/aliasmaker"
ln -sf "$repo/src/doit" "$bin_dir/doit"

cat > "$apps_dir/aliasmaker.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Alias Maker
GenericName=Terminal
Comment=A terminal with a database of your commands and your own custom commands
Exec="$repo/src/aliasmaker"
Icon=utilities-terminal
Terminal=false
Categories=System;TerminalEmulator;
Keywords=terminal;shell;prompt;command;commandline;alias;doit;
StartupWMClass=io.github.thestylewithin.aliasmaker
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$apps_dir" || true

echo "Installed Alias Maker from: $repo"
echo "(Keep this folder where it is. Alias Maker runs from it.)"

if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Vte", "3.91")' 2>/dev/null; then
    echo
    echo "One more thing: the Alias Maker window needs two packages. Install them with:"
    echo "  sudo pacman -S vte4 python-gobject"
fi

echo
echo "Open \"Alias Maker\" from your app launcher, or type: aliasmaker"
echo "The first time it opens, it scans your installed software to fill the Database."

case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *)
        echo
        echo "To start it by typing 'aliasmaker' in other terminals, add $bin_dir to your PATH:"
        echo "  fish (CachyOS's default):  fish_add_path ~/.local/bin"
        echo "  bash:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        ;;
esac
