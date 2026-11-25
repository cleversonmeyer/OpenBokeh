#!/bin/sh
# Compila o gravador de tela (D3D11 + Desktop Duplication + Media Foundation, 64 bits) com o Zig.
set -e
cd "$(dirname "$0")"
ZIG="${ZIG:-$HOME/.local/zig/zig-linux-x86_64-0.13.0/zig}"
mkdir -p build
"$ZIG" c++ -target x86_64-windows-gnu -shared -O2 -static -Wno-everything \
  -o build/OpenBokehGravador.dll OpenBokehGravador.cpp OpenBokehGravador.def \
  -ld3d11 -ldxgi -lmfplat -lmfreadwrite -lmfuuid -lole32 -loleaut32 -luuid -luser32 -s
rm -f build/*.lib build/*.pdb
echo "ok: build/OpenBokehGravador.dll"
