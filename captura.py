"""
O que gravar: tela inteira, uma regiao ou uma janela (Chrome, VS Code...).

A gravacao sempre captura o monitor (Desktop Duplication, na placa de video) e recorta
a area escolhida. No modo janela, a area acompanha a janela quando ela se move ou muda
de tamanho; ela precisa estar visivel (o que estiver por cima dela aparece no video).
"""

import ctypes
import os
from ctypes import wintypes

_u = ctypes.windll.user32
_k = ctypes.windll.kernel32
_dwm = ctypes.windll.dwmapi

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
GW_OWNER = 4
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.IsWindowVisible.argtypes = [wintypes.HWND]
_u.IsIconic.argtypes = [wintypes.HWND]
_u.IsWindow.argtypes = [wintypes.HWND]
_u.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
_u.GetWindow.restype = wintypes.HWND
_u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def _titulo(h):
    n = _u.GetWindowTextLengthW(h)
    if n <= 0:
        return ""
    b = ctypes.create_unicode_buffer(n + 1)
    _u.GetWindowTextW(h, b, n + 1)
    return b.value


def _exe(h):
    pid = wintypes.DWORD()
    _u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    hp = _k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not hp:
        return "", pid.value
    try:
        b = ctypes.create_unicode_buffer(520)
        n = wintypes.DWORD(520)
        if _k.QueryFullProcessImageNameW(hp, 0, b, ctypes.byref(n)):
            return os.path.basename(b.value).lower(), pid.value
        return "", pid.value
    finally:
        _k.CloseHandle(hp)


def _escondida(h):
    v = ctypes.c_int(0)
    _dwm.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v))
    return v.value != 0          # janelas "fantasma" de apps da Store, outras areas de trabalho...


def retangulo(h):
    """(esquerda, topo, direita, base) da janela em pixels reais, sem a sombra; ou None."""
    if not h or not _u.IsWindow(h) or _u.IsIconic(h):
        return None
    r = wintypes.RECT()
    if _dwm.DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not _u.GetWindowRect(h, ctypes.byref(r)):
            return None
    if r.right - r.left < 16 or r.bottom - r.top < 16:
        return None
    return r.left, r.top, r.right, r.bottom


def listar_janelas():
    """Janelas de apps abertas, como na barra de tarefas: [{hwnd, titulo, exe}]."""
    proprio = os.getpid()
    lista = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(h, _l):
        try:
            if not _u.IsWindowVisible(h) or _u.GetWindow(h, GW_OWNER) or _escondida(h):
                return True
            if _u.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            t = "".join(ch for ch in _titulo(h) if ord(ch) <= 0xFFFF).strip()   # o Tk nao mostra emoji
            if not t or t in ("Program Manager", "Windows Input Experience"):
                return True
            exe, pid = _exe(h)
            if pid == proprio:
                return True
            lista.append({"hwnd": int(h), "titulo": t, "exe": exe, "minimizada": bool(_u.IsIconic(h))})
        except Exception:
            pass
        return True

    _u.EnumWindows(cada, 0)
    return lista


def achar_janela(info):
    """A janela salva nas opcoes ({hwnd, exe, titulo}): a mesma, se ainda existir; senao a
    primeira do mesmo programa (o hwnd muda quando o app e reaberto)."""
    if not info or not info.get("exe"):
        return None
    h = info.get("hwnd")
    if h and _u.IsWindow(h) and _exe(h)[0] == info["exe"]:
        return h
    candidatas = [j for j in listar_janelas() if j["exe"] == info["exe"]]
    for j in candidatas:
        if j["titulo"] == info.get("titulo"):
            return j["hwnd"]
    return candidatas[0]["hwnd"] if candidatas else None


def monitor_da_area(r, monitores):
    """Monitor que contem a maior parte do retangulo (esq, topo, dir, base)."""
    melhor, area = None, 0
    for m in monitores:
        x0, y0 = max(r[0], m["x"]), max(r[1], m["y"])
        x1, y1 = min(r[2], m["x"] + m["largura"]), min(r[3], m["y"] + m["altura"])
        a = max(0, x1 - x0) * max(0, y1 - y0)
        if a > area:
            melhor, area = m, a
    return melhor


def no_monitor(r, m):
    """Retangulo da area (coordenadas da area de trabalho) -> (x, y, w, h) dentro do monitor."""
    x0, y0 = max(r[0], m["x"]), max(r[1], m["y"])
    x1, y1 = min(r[2], m["x"] + m["largura"]), min(r[3], m["y"] + m["altura"])
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    return x0 - m["x"], y0 - m["y"], (x1 - x0) & ~1, (y1 - y0) & ~1
