#!/bin/sh
# Compila o RNNoise (Xiph, licenca BSD-3, versao 0.1.1) como DLL de 64 bits para o
# microfone sem ruido do OpenBokeh. Usa o Zig 0.13 (cross-compile a partir do Linux/WSL).
set -e
cd "$(dirname "$0")"
ZIG="${ZIG:-$HOME/.local/zig/zig-linux-x86_64-0.13.0/zig}"
mkdir -p build
"$ZIG" cc -target x86_64-windows-gnu -O2 -shared -DRNNOISE_BUILD -DDLL_EXPORT -Iinclude -Isrc \
    src/denoise.c src/rnn.c src/rnn_data.c src/rnn_reader.c src/pitch.c src/kiss_fft.c src/celt_lpc.c \
    -o build/rnnoise.dll -s
rm -f build/*.lib build/*.pdb
echo "ok: build/rnnoise.dll"
