"""Icone do OpenBokeh na bandeja do Windows (ao lado do relogio).

Clique: abre a janela. Botao direito: Volto ja, perfis, sair.
O icone fica acinzentado quando a webcam esta em espera.
"""

import pystray
from PIL import Image, ImageEnhance
from i18n import _


class Bandeja:
    def __init__(self, icone, motor, cfg, mostrar, privacidade, aplicar_perfil, sair, configuracoes=None, microfone=None,
                 gravar=None, gravando=lambda: False):
        self.motor, self.cfg = motor, cfg
        base = Image.open(icone).convert("RGBA")
        self.img_ativo = base
        cinza = ImageEnhance.Color(base).enhance(0.0)
        self.img_espera = ImageEnhance.Brightness(cinza).enhance(0.75)
        self._estado = None

        def perfis():
            return [pystray.MenuItem(nome, (lambda n: lambda: aplicar_perfil(n))(nome))
                    for nome in self.cfg["perfis"]] or [pystray.MenuItem(_("(nenhum perfil)"), None, enabled=False)]

        menu = pystray.Menu(
            pystray.MenuItem(_("Abrir OpenBokeh"), lambda: mostrar(), default=True),
            pystray.MenuItem(lambda _i: _("Volto já  ({atalho})").format(atalho=self.cfg['atalho_privacidade'])
                             if self.cfg["atalho_privacidade"] != "Desativado" else _("Volto já"), lambda: privacidade(),
                             checked=lambda _i: self.motor.privacidade),
            pystray.MenuItem(lambda _i: _("■  Parar gravação") if gravando() else _("●  Gravar tela"),
                             lambda: gravar and gravar(), visible=lambda _i: gravar is not None),
            pystray.MenuItem(_("Microfone sem ruído"), lambda: microfone and microfone(),
                             checked=lambda _i: bool(self.cfg.get("microfone_limpo")),
                             visible=lambda _i: microfone is not None and self.motor.microfone is not None),
            pystray.MenuItem(_("Perfis"), pystray.Menu(perfis)),
            pystray.MenuItem(_("Configurações…"), lambda: configuracoes and configuracoes()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_("Sair do OpenBokeh"), lambda: sair()),
        )
        self.icone = pystray.Icon("OpenBokeh", base, "OpenBokeh", menu)
        self.icone.run_detached()
        self.atualizar()

    def atualizar(self):
        """Troca imagem e dica conforme o estado (chamado pela interface)."""
        if getattr(self.motor, "gravacao", None) is not None:
            estado = ("ativo", _("OpenBokeh · gravando a tela"))
        elif self.motor.privacidade:
            estado = ("ativo", _("OpenBokeh · Volto já ligado"))
        elif self.motor.em_espera:
            estado = ("espera", _("OpenBokeh · em espera (webcam desligada)"))
        else:
            estado = ("ativo", _("OpenBokeh · câmera ativa"))
        if estado != self._estado:
            self._estado = estado
            self.icone.icon = self.img_espera if estado[0] == "espera" else self.img_ativo
            self.icone.title = estado[1]
            self.icone.update_menu()

    def avisar(self, texto):
        if not self.cfg.get("notificacoes", True):
            return
        try:
            self.icone.notify(texto, "OpenBokeh")
        except Exception:
            pass

    def parar(self):
        try:
            self.icone.stop()
        except Exception:
            pass
