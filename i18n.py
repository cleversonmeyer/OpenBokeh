"""
Traducao da interface do OpenBokeh.

Os textos do codigo estao em portugues; `_("texto")` devolve a versao no
idioma escolhido. Idioma: configuracao "idioma" (auto | pt | en). Em "auto",
segue o idioma do Windows: portugues -> portugues; qualquer outro -> ingles.
A troca vale ao reiniciar o app (os textos sao montados ao abrir).
"""

import ctypes
import json
import os
import sys

IDIOMAS = [("auto", "Automático (Windows)"), ("pt", "Português (Brasil)"), ("en", "English")]


def idioma_do_windows():
    try:
        lang = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "pt" if (lang & 0x3FF) == 0x16 else "en"     # 0x16 = LANG_PORTUGUESE
    except Exception:
        return "pt"


def _arquivo_config():
    if getattr(sys, "frozen", False):
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "OpenBokeh", "config.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _escolhido():
    try:
        with open(_arquivo_config(), encoding="utf-8") as f:
            valor = json.load(f).get("idioma", "auto")
    except Exception:
        valor = "auto"
    return valor if valor in ("pt", "en") else idioma_do_windows()


IDIOMA = _escolhido()

if IDIOMA == "en":
    from traducoes_en import EN as _TABELA
else:
    _TABELA = {}


def _(texto):
    """Texto no idioma da interface (sem traducao cadastrada: fica como esta)."""
    return _TABELA.get(texto, texto)
