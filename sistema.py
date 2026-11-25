"""Integracao com o Windows: iniciar com o Windows e sinal "mostrar janela"."""

import ctypes
import sys
import threading
import winreg
from ctypes import wintypes

CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME_RUN = "OpenBokeh"
EVENTO_MOSTRAR = "Local\\OpenBokeh.MostrarJanela"

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenEventW.restype = wintypes.HANDLE
_k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]


# ---------------------------------------------------------------- iniciar com o Windows
def instalado():
    """So o app instalado (OpenBokeh.exe) pode iniciar com o Windows."""
    return getattr(sys, "frozen", False)


def comando_inicio():
    return f'"{sys.executable}" --bandeja'


def inicio_automatico_ativo():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            valor, _ = winreg.QueryValueEx(k, NOME_RUN)
            return bool(valor)
    except OSError:
        return False


def definir_inicio_automatico(ligar):
    """Liga/desliga para o usuario atual (HKCU: nao precisa de administrador).
    O app abre escondido na bandeja e com a webcam em espera."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, NOME_RUN, 0, winreg.REG_SZ, comando_inicio())
        else:
            try:
                winreg.DeleteValue(k, NOME_RUN)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- sinal entre instancias
def pedir_para_mostrar():
    """Segunda instancia: pede para a primeira aparecer. True se havia alguem ouvindo."""
    h = _k32.OpenEventW(0x0002, False, EVENTO_MOSTRAR)        # EVENT_MODIFY_STATE
    if not h:
        return False
    _k32.SetEvent(h)
    _k32.CloseHandle(h)
    return True


class OuvinteMostrar:
    """Primeira instancia: chama `callback` quando outra instancia pedir."""

    def __init__(self, callback):
        self.callback = callback
        self.h = _k32.CreateEventW(None, False, False, EVENTO_MOSTRAR)
        self.rodando = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.rodando and self.h:
            if _k32.WaitForSingleObject(self.h, 500) == 0:
                try:
                    self.callback()
                except Exception as e:
                    print(f"[aviso] mostrar janela: {e}")

    def parar(self):
        self.rodando = False
