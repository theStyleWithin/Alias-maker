#!/usr/bin/env bash
# Fills an AppDir with everything Alias Maker needs to run on a PC that has none of it:
# Python, PyGObject, GTK 4, VTE and fish, from this machine's Ubuntu 24.04 packages. The PC
# only has to provide what a desktop always has: the C library, the graphics stack (OpenGL,
# X11/Wayland), fonts and fontconfig.
#
# Libraries are found through a relative RUNPATH, not LD_LIBRARY_PATH, so nothing leaks
# into the programs you start from the terminal.
#
#   make-bundle.sh APPDIR
#
# Needs: python3 python3-gi gir1.2-gtk-4.0 gir1.2-vte-3.91 librsvg2-common adwaita-icon-theme
#        fish patchelf libglib2.0-bin libgdk-pixbuf2.0-bin libgtk-4-common binutils
set -euo pipefail

dir="$(mkdir -p "$1" && realpath "$1")"
lib=/usr/lib/x86_64-linux-gnu
# the Python PyGObject (python3-gi) was built for: the system's own, whatever python3 on PATH is
gi_so=$(ls /usr/lib/python3/dist-packages/gi/_gi.cpython-3*-x86_64-linux-gnu.so | head -1)
pyv=$(sed -E 's/.*cpython-3([0-9]+)-.*/3.\1/' <<<"$gi_so")
mkdir -p "$dir/usr/bin" "$dir/usr/lib" "$dir/usr/share"

# What the PC provides itself: never copied.
EXCLUDE='^(ld-linux[^ ]*|linux-vdso[^ ]*|libc|libm|libdl|libpthread|librt|libutil|libresolv|libnsl|libanl|libBrokenLocale|libthread_db|libnss_[a-z]+)\.so'
EXCLUDE+='|^(libGL|libGLX|libGLdispatch|libEGL|libOpenGL|libGLES[a-zA-Z0-9_]*|libgbm|libdrm[a-z_-]*|libvulkan)\.so'
EXCLUDE+='|^(libX11|libX11-xcb|libXau|libXdmcp|libXext|libXrender|libXi|libXcursor|libXfixes|libXrandr|libXinerama|libXdamage|libXcomposite|libXtst|libXxf86vm|libxshmfence|libSM|libICE)\.so'
EXCLUDE+='|^libxcb\.so|^libwayland-[a-z-]+\.so|^(libfontconfig|libfreetype)\.so'

declare -A seen=()

add_libs_of() {  # copy the shared libraries each given file needs (the closure ldd reports)
    local f name path
    for f in "$@"; do
        while read -r name path; do
            [[ -n "${seen[$name]:-}" ]] && continue
            seen[$name]=1
            [[ "$name" =~ $EXCLUDE ]] && continue
            cp -L "$path" "$dir/usr/lib/$name"
        done < <(ldd "$f" 2>/dev/null | awk '$2 == "=>" && $3 ~ /^\// {print $1, $3}')
    done
}

lib_path() {  # lib_path SONAME -> where this machine keeps it
    ldconfig -p | awk -v n="$1" '$1 == n && /x86-64/ {print $NF; exit}'
}

# ---------- Python ----------
cp -L "/usr/bin/python$pyv" "$dir/usr/bin/python$pyv"
ln -sf "python$pyv" "$dir/usr/bin/python3"
tar -C /usr/lib -cf - \
    --exclude='__pycache__' --exclude="python$pyv/test" --exclude="python$pyv/idlelib" \
    --exclude="python$pyv/tkinter" --exclude="python$pyv/turtledemo" --exclude="python$pyv/ensurepip" \
    --exclude="python$pyv/lib2to3" --exclude="python$pyv/config-*" "python$pyv" | tar -C "$dir/usr/lib" -xf -
for module in _tkinter _curses _curses_panel _dbm _gdbm readline _sqlite3 _ctypes_test _testcapi \
              _testbuffer _testimportmultiple _testmultiphase _xxtestfuzz xxlimited xxlimited_35; do
    rm -f "$dir/usr/lib/python$pyv/lib-dynload/$module".*.so
done

# ---------- PyGObject ----------
mkdir -p "$dir/usr/lib/python3/dist-packages"
tar -C /usr/lib/python3/dist-packages -cf - --exclude='__pycache__' gi | tar -C "$dir/usr/lib/python3/dist-packages" -xf -
[[ -d /usr/lib/python3/dist-packages/cairo ]] &&
    tar -C /usr/lib/python3/dist-packages -cf - --exclude='__pycache__' cairo | tar -C "$dir/usr/lib/python3/dist-packages" -xf -

# ---------- GTK 4, VTE and what GObject introspection loads by name ----------
mkdir -p "$dir/usr/lib/girepository-1.0"
cp "$lib"/girepository-1.0/*.typelib "$dir/usr/lib/girepository-1.0/"

# ---------- pixbuf loaders (symbolic icons are SVG) ----------
loaders_dir="$lib/gdk-pixbuf-2.0/2.10.0/loaders"
mkdir -p "$dir/usr/lib/gdk-pixbuf-2.0/loaders"
cp "$loaders_dir"/*.so "$dir/usr/lib/gdk-pixbuf-2.0/loaders/"

# ---------- fish ----------
cp -L /usr/bin/fish "$dir/usr/bin/fish"
mkdir -p "$dir/usr/share"
tar -C /usr/share -cf - --exclude='man' fish | tar -C "$dir/usr/share" -xf -

# ---------- libraries ----------
extra=()
for soname in libgtk-4.so.1 libvte-2.91-gtk4.so.0 libgirepository-1.0.so.1 libpangocairo-1.0.so.0 \
              libpangoft2-1.0.so.0 libcairo-gobject.so.2 libgdk_pixbuf-2.0.so.0 libgraphene-1.0.so.0 \
              libgmodule-2.0.so.0 libgio-2.0.so.0 libharfbuzz-gobject.so.0 librsvg-2.so.2; do
    path=$(lib_path "$soname")
    [[ -n "$path" ]] && extra+=("$path")
done
mapfile -t elfs < <(find "$dir/usr/bin" "$dir/usr/lib/python$pyv/lib-dynload" "$dir/usr/lib/python3/dist-packages" \
                         "$dir/usr/lib/gdk-pixbuf-2.0/loaders" -type f \( -name '*.so' -o -name '*.so.*' -o -path '*/usr/bin/*' \))
add_libs_of "${elfs[@]}" "${extra[@]}"
for path in "${extra[@]}"; do
    name=$(basename "$path")
    [[ -e "$dir/usr/lib/$name" ]] || cp -L "$path" "$dir/usr/lib/$name"
done
# the libraries libgtk, libvte and the loaders themselves need were reported by ldd above;
# a second pass catches what the freshly copied libraries need
mapfile -t libs < <(find "$dir/usr/lib" -maxdepth 1 -type f -name '*.so*')
add_libs_of "${libs[@]}"

# ---------- point everything at the bundle ----------
set_rpath() {
    local rel
    rel=$(realpath --relative-to="$(dirname "$1")" "$dir/usr/lib")
    patchelf --set-rpath "\$ORIGIN/$rel" "$1" 2>/dev/null || true
}
while IFS= read -r f; do
    [[ "$(head -c4 "$f" | tr -d '\0')" == $'\x7fELF' ]] || continue
    strip --strip-unneeded "$f" 2>/dev/null || true
    set_rpath "$f"
done < <(find "$dir/usr" -type f \( -name '*.so' -o -name '*.so.*' -o -path '*/usr/bin/*' \))

# ---------- data GTK looks for ----------
mkdir -p "$dir/usr/share/glib-2.0/schemas"
cp /usr/share/glib-2.0/schemas/org.gtk.gtk4.Settings.*.gschema.xml \
   /usr/share/glib-2.0/schemas/org.gtk.Settings.*.gschema.xml "$dir/usr/share/glib-2.0/schemas/" 2>/dev/null || true
glib-compile-schemas "$dir/usr/share/glib-2.0/schemas"
rm -f "$dir"/usr/share/glib-2.0/schemas/*.xml

mkdir -p "$dir/usr/share/icons/Adwaita"
cp /usr/share/icons/Adwaita/index.theme "$dir/usr/share/icons/Adwaita/"
cp -a /usr/share/icons/Adwaita/symbolic "$dir/usr/share/icons/Adwaita/"
mkdir -p "$dir/usr/share/icons/hicolor" && cp /usr/share/icons/hicolor/index.theme "$dir/usr/share/icons/hicolor/"

# the pixbuf loader list: just the file names, found through GDK_PIXBUF_MODULEDIR (see AppRun)
"$lib/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders" "$dir"/usr/lib/gdk-pixbuf-2.0/loaders/*.so |
    sed "s|$dir/usr/lib/gdk-pixbuf-2.0/loaders/||" > "$dir/usr/lib/gdk-pixbuf-2.0/loaders.cache"
grep -q 'svg' "$dir/usr/lib/gdk-pixbuf-2.0/loaders.cache" || { echo "make-bundle: the pixbuf loader list is empty" >&2; exit 1; }

du -sh "$dir" | cut -f1
