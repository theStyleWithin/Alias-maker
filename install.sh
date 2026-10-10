#!/usr/bin/env bash
# Installs the doit prototype for the current user only. No root needed.
# Uninstall: rm ~/.local/bin/doit   (settings: ~/.config/doit, log: ~/.local/share/doit)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="$HOME/.local/bin"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Do It needs python3. Install it with: sudo pacman -S python"
    exit 1
fi

mkdir -p "$bin_dir"
chmod +x "$repo/src/doit"
ln -sf "$repo/src/doit" "$bin_dir/doit"
echo "Installed: $bin_dir/doit -> $repo/src/doit"
echo "(Keep this folder where it is. The doit command runs from it.)"

case ":$PATH:" in
    *":$bin_dir:"*)
        echo
        echo "Done. Try it safely first with:  doit --dry-run"
        ;;
    *)
        echo
        echo "One more step: your terminal doesn't look in $bin_dir yet."
        echo "  If you use fish (CachyOS's default):  fish_add_path ~/.local/bin"
        echo "  If you use bash:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        echo "Then open a new terminal and try:  doit --dry-run"
        ;;
esac
