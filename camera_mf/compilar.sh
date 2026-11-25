#!/bin/sh
# Compila a camera do Windows 11 (fonte de midia Media Foundation, 64 bits) com o Zig.
# Uso: ./compilar.sh [caminho/do/zig]
set -e
cd "$(dirname "$0")"
ZIG="${1:-zig}"
mkdir -p build
"$ZIG" c++ -target x86_64-windows-gnu -shared -O2 -static -Wno-everything \
  -o build/OpenBokehMF.dll OpenBokehMF.cpp OpenBokehMF.def \
  -lmfplat -lmf -lmfuuid -lole32 -loleaut32 -luuid -ladvapi32 -lgdi32 -luser32
rm -f build/*.lib build/*.pdb
echo "ok: build/OpenBokehMF.dll"
