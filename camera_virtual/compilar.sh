#!/bin/sh
# Compila a camera virtual "OpenBokeh Camera" (DLL DirectShow, 64 bits) com o Zig.
# Zig: https://ziglang.org (testado com 0.13.0). Uso: ./compilar.sh [caminho/do/zig]
set -e
cd "$(dirname "$0")"
ZIG="${1:-zig}"
mkdir -p build
# 64 bits (Chrome, Zoom, Teams, OBS...) e 32 bits (programas antigos)
for alvo in "x86_64-windows-gnu:64" "x86-windows-gnu:32"; do
  triplo="${alvo%%:*}"; bits="${alvo##*:}"
  "$ZIG" c++ -target "$triplo" -shared -O2 -fms-extensions -static \
    -include compat_mingw.h -Wno-everything \
    -o "build/OpenBokehCamera$bits.dll" \
    OpenBokehCamera.cpp streams.cpp compat_mingw.cpp OpenBokehCamera.def \
    -lole32 -loleaut32 -luuid -lwinmm -lstrmiids -lgdi32 -luser32 -ladvapi32
  echo "ok: build/OpenBokehCamera$bits.dll"
done
rm -f build/OpenBokehCamera.lib build/*.pdb
