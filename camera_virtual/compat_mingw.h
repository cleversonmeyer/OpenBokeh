/* Compatibilidade para compilar com Zig/clang (alvo x86_64-windows-gnu, MinGW).
   O codigo original usa anotacoes SAL, exclusivas do compilador da Microsoft;
   aqui elas viram nada. Incluido automaticamente com -include. */
#pragma once
#ifndef _MSC_VER
#define __deref_in
#define __deref_inout_opt
#define __deref_out
#define __deref_out_opt
#define __field_ecount_opt(x)
#define __format_string
#define __in
#define __in_bcount(x)
#define __in_bcount_opt(x)
#define __in_ecount(x)
#define __in_ecount_opt(x)
#define __in_opt
#define __inout
#define __inout_ecount_full(x)
#define __inout_opt
#define __out
#define __out_bcount(x)
#define __out_ecount(x)
#define __out_ecount_part(x, y)
#define __out_opt
#endif

#ifndef _MSC_VER
#define __control_entrypoint(x)

/* min/max como funcoes (o windows.h do MSVC define como macros).
   ATENCAO: o retorno precisa ser um VALOR. Uma versao anterior usava
   decltype(a > b ? a : b), que vira referencia para o parametro local:
   com otimizacao, o resultado era lixo (o redimensionamento saia preto). */
#ifdef __cplusplus
#include <type_traits>
template <class A, class B> static inline typename std::common_type<A, B>::type max(A a, B b) { return a > b ? a : b; }
template <class A, class B> static inline typename std::common_type<A, B>::type min(A a, B b) { return a < b ? a : b; }
#endif

/* macros do amvideo.h da Microsoft que nao existem no MinGW */
#define WIDTHBYTES(bits) ((DWORD)(((bits)+31) & (~31)) / 8)
#define DIBWIDTHBYTES(bi) (DWORD)WIDTHBYTES((DWORD)(bi).biWidth * (DWORD)(bi).biBitCount)
#define _DIBSIZE(bi) (DIBWIDTHBYTES(bi) * (DWORD)(bi).biHeight)
#define DIBSIZE(bi) ((bi).biHeight < 0 ? (-1)*(_DIBSIZE(bi)) : _DIBSIZE(bi))
#define SIZE_MASKS (iMASK_COLORS * sizeof(DWORD))
#define SIZE_PALETTE (iPALETTE_COLORS * sizeof(RGBQUAD))
#define SIZE_PREHEADER (FIELD_OFFSET(VIDEOINFOHEADER, bmiHeader))
#define SIZE_VIDEOHEADER (sizeof(BITMAPINFOHEADER) + SIZE_PREHEADER)
#define PALETTISED(pbmi) ((pbmi)->bmiHeader.biBitCount <= iPALETTE)
#define PALETTE_ENTRIES(pbmi) ((DWORD) 1 << (pbmi)->bmiHeader.biBitCount)
#define TRUECOLOR(pbmi) ((TRUECOLORINFO *)(((LPBYTE)&((pbmi)->bmiHeader)) + (pbmi)->bmiHeader.biSize))
#define COLORS(pbmi) ((RGBQUAD *)(((LPBYTE)&((pbmi)->bmiHeader)) + (pbmi)->bmiHeader.biSize))
#define BITMASKS(pbmi) ((DWORD *)(((LPBYTE)&((pbmi)->bmiHeader)) + (pbmi)->bmiHeader.biSize))
#endif
