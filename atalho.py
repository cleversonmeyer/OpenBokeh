"""
Atalhos de teclado globais (funcionam com o OpenBokeh minimizado ou com o
Meet em primeiro plano), via RegisterHotKey do Windows. Sem bibliotecas extras.

Combinacoes escritas como texto: "Ctrl+Alt+B", "Ctrl+Shift+F9", "Desativado".
"""

import ctypes
import threading
from ctypes import wintypes

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
DESATIVADO = "Desativado"

# opcoes oferecidas nas Configuracoes (evitamos combinacoes comuns em outros apps,
# como Ctrl+Shift+P do VS Code, e Ctrl+Alt+letra que vira AltGr em teclados ABNT2
# so para letras que tem simbolo no AltGr: Q, W, E, /, ?)
OPCOES = ["Ctrl+Alt+B", "Ctrl+Alt+N", "Ctrl+Alt+R", "Ctrl+Alt+P", "Ctrl+Alt+S", "Ctrl+Alt+V", "Ctrl+Shift+B", "Ctrl+Shift+F9", "Ctrl+Shift+F10",
          "Ctrl+Alt+F9", "Ctrl+Alt+F10", DESATIVADO]

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32")


def interpretar(combo):
    """'Ctrl+Alt+B' -> (modificadores, codigo_da_tecla) ou None."""
    if not combo or combo == DESATIVADO:
        return None
    mods, vk = 0, None
    for parte in combo.replace(" ", "").split("+"):
        p = parte.lower()
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p == "win":
            mods |= MOD_WIN
        elif len(p) >= 2 and p[0] == "f" and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
            vk = 0x70 + int(p[1:]) - 1
        elif len(p) == 1 and p.isalnum():
            vk = ord(p.upper())
        else:
            return None
    return (mods, vk) if vk is not None and mods else None


class AtalhoGlobal:
    def __init__(self, callback, combo="Ctrl+Alt+B"):
        self.callback = callback
        self.descricao = combo
        self.ok = False
        self._thread_id = None
        self._pronto = threading.Event()
        tecla = interpretar(combo)
        if tecla is None:
            return
        self.mods, self.vk = tecla
        threading.Thread(target=self._loop, daemon=True).start()
        self._pronto.wait(2.0)

    def _loop(self):
        # o atalho pertence a thread que o registra; ela precisa ficar
        # lendo a fila de mensagens do Windows
        self._thread_id = _k32.GetCurrentThreadId()
        self.ok = bool(_user32.RegisterHotKey(None, 1, self.mods | MOD_NOREPEAT, self.vk))
        self._pronto.set()
        if not self.ok:
            return
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    self.callback()
                except Exception as e:
                    print(f"[aviso] atalho: {e}")
        _user32.UnregisterHotKey(None, 1)

    def parar(self):
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread_id = None
