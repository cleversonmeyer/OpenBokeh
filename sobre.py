"""Janela "Sobre": versao, privacidade, creditos e licenca."""

import os
import sys
import webbrowser

import versao as V
from i18n import _

CREDITOS = [
    ("Robust Video Matting", _("Peter Lin e colaboradores (ByteDance)"), _("Modelo de IA que recorta a pessoa"), "GPL-3.0",
     "https://github.com/PeterL1n/RobustVideoMatting"),
    ("Unity Capture", "Bernhard Schelling", _("Base da câmera virtual (adaptada)"), "MIT",
     "https://github.com/schellingb/UnityCapture"),
    ("ONNX Runtime + DirectML", "Microsoft", _("Executa a IA na placa de vídeo"), "MIT", "https://onnxruntime.ai"),
    ("OpenCV", "OpenCV team", _("Captura e processamento de imagem e vídeo"), "Apache-2.0", "https://opencv.org"),
    ("NumPy", "NumPy developers", _("Cálculos com imagens"), "BSD-3-Clause", "https://numpy.org"),
    ("CustomTkinter", "Tom Schimansky", _("Interface moderna"), "MIT", "https://github.com/TomSchimansky/CustomTkinter"),
    ("Pillow", _("Jeffrey A. Clark e colaboradores"), _("Imagens e textos da interface"), "MIT-CMU", "https://python-pillow.org"),
    ("pygrabber / comtypes", "A. Schiavinato / comtypes team", _("Lista de webcams"), "MIT",
     "https://github.com/andreaschiavinato/python_grabber"),
    ("pystray", "Moses Palmér", _("Ícone na bandeja do Windows"), "LGPL-3.0", "https://github.com/moses-palmer/pystray"),
    ("RNNoise", "Jean-Marc Valin, Xiph.Org, Mozilla", _("IA que tira o ruído do microfone"), "BSD-3-Clause",
     "https://github.com/xiph/rnnoise"),
    ("PortAudio + sounddevice", _("PortAudio e Matthias Geier"), _("Leitura e envio de áudio"), "MIT",
     "https://github.com/spatialaudio/python-sounddevice"),
    ("Python", "Python Software Foundation", _("Linguagem do aplicativo"), "PSF", "https://www.python.org"),
    ("PyInstaller", "PyInstaller team", _("Empacotamento"), _("GPL-2.0+ (exceção bootloader)"), "https://pyinstaller.org"),
]

MARCAS = (_("AMD e Radeon são marcas da Advanced Micro Devices, Inc.; NVIDIA é marca da NVIDIA Corporation; "
          "Intel é marca da Intel Corporation; Google Meet é marca da Google LLC; Zoom é marca da Zoom Video "
          "Communications, Inc.; OBS Studio é marca do OBS Project. O OpenBokeh é um projeto independente, "
          "sem vínculo com essas empresas."))


def _arquivo(nome):
    """Arquivo de texto empacotado junto do app (LICENSE, PRIVACIDADE.md)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for pasta in (base, os.path.join(base, "docs")):
        caminho = os.path.join(pasta, nome)
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                return f.read()
    return _("({nome} não encontrado)").format(nome=nome)


def abrir(root, cores, logo_caminho=None, info_tecnica=""):
    import customtkinter as ctk
    from PIL import Image

    BG, CARD, CARD_2, BORDA, TEXTO, SUAVE, ACENTO, ACENTO_HOVER = cores
    if getattr(root, "_janela_sobre", None) is not None and root._janela_sobre.winfo_exists():
        root._janela_sobre.focus()
        return

    j = ctk.CTkToplevel(root, fg_color=BG)
    root._janela_sobre = j
    j.title(_("Sobre o {nome}").format(nome=V.NOME))
    j.geometry("640x600")
    j.resizable(False, False)
    j.transient(root)
    j.after(250, lambda: (j.lift(), j.focus_force()))
    if logo_caminho:
        ico = os.path.join(os.path.dirname(logo_caminho), "icone.ico")
        if os.path.exists(ico):
            # o CustomTkinter troca o icone da janela logo depois de abrir; reaplica
            j.after(300, lambda: j.iconbitmap(ico))
    F = "Segoe UI"

    topo = ctk.CTkFrame(j, fg_color="transparent")
    topo.pack(fill="x", padx=24, pady=(20, 8))
    if logo_caminho and os.path.exists(logo_caminho):
        logo = ctk.CTkImage(Image.open(logo_caminho), size=(56, 56))
        ctk.CTkLabel(topo, image=logo, text="").pack(side="left")
    t = ctk.CTkFrame(topo, fg_color="transparent")
    t.pack(side="left", padx=(14, 0))
    ctk.CTkLabel(t, text=V.NOME, font=ctk.CTkFont(F, 24, "bold"), text_color=TEXTO, height=28).pack(anchor="w")
    ctk.CTkLabel(t, text=_("Versão {versao}  ·  {descricao}  ·  software livre ({licenca})").format(versao=V.VERSAO, descricao=_(V.DESCRICAO), licenca=V.LICENCA),
                 font=ctk.CTkFont(F, 12), text_color=SUAVE, height=18).pack(anchor="w")
    site = ctk.CTkLabel(t, text=V.SITE.replace("https://", ""), font=ctk.CTkFont(F, 12, underline=True),
                        text_color=ACENTO, height=18, cursor="hand2")
    site.pack(anchor="w")
    site.bind("<Button-1>", lambda _e: __import__("webbrowser").open(V.SITE))

    abas = ctk.CTkTabview(j, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDA,
                          segmented_button_fg_color=CARD_2, segmented_button_selected_color=ACENTO,
                          segmented_button_selected_hover_color=ACENTO_HOVER,
                          segmented_button_unselected_color=CARD_2, segmented_button_unselected_hover_color=BORDA,
                          text_color=TEXTO)
    abas.pack(fill="both", expand=True, padx=24, pady=(0, 12))
    for nome in (_("Sobre"), _("Privacidade"), _("Créditos"), _("Licença")):
        abas.add(nome)

    def caixa_texto(pai, texto):
        tb = ctk.CTkTextbox(pai, fg_color=CARD, text_color=TEXTO, font=ctk.CTkFont(F, 12), wrap="word",
                            border_width=0, scrollbar_button_color=BORDA)
        tb.pack(fill="both", expand=True, padx=4, pady=4)
        tb.insert("1.0", texto)
        tb.configure(state="disabled")
        return tb

    # -- Sobre
    sobre = _(
        "{nome} desfoca ou troca o fundo da sua webcam usando inteligência artificial que roda "
        "na sua própria placa de vídeo, via DirectML: funciona em placas AMD Radeon, NVIDIA e Intel.\n\n"
        "O resultado aparece na câmera virtual “OpenBokeh Camera”, que você escolhe no Google Meet, "
        "Zoom, Teams, Discord, OBS e outros.\n\n"
        "É gratuito, sem marca d'água, sem conta e sem anúncios. Tudo é processado no seu computador.\n\n"
        "Atalhos\n"
        "  Ctrl+Alt+B   liga/desliga a tela “Volto já” (padrão)\n"
        "  Ctrl+Alt+N   liga/desliga o efeito (padrão)\n"
        "  Ctrl+,       abre as Configurações\n"
        "  Os atalhos podem ser trocados em Configurações › Atalhos.\n\n"
        "Informações técnicas\n{info}\n\n"
        "{copyright}. Este programa vem SEM NENHUMA GARANTIA. Ele é software livre e você pode "
        "redistribuí-lo e/ou modificá-lo sob os termos da GNU General Public License, versão 3 ou posterior "
        "(veja a aba “Licença”)."
    ).format(nome=V.NOME, info=info_tecnica, copyright=V.COPYRIGHT)
    caixa_texto(abas.tab(_("Sobre")), sobre)

    # -- Privacidade
    def sem_markdown(texto):
        linhas = []
        for l in texto.splitlines():
            if l.startswith("#"):
                l = l.lstrip("#").strip().upper() if l.startswith("## ") else l.lstrip("#").strip()
            linhas.append(l.replace("**", "").replace("`", "").replace("*", ""))
        return "\n".join(linhas)
    caixa_texto(abas.tab(_("Privacidade")), sem_markdown(_arquivo("PRIVACY.md" if __import__("i18n").IDIOMA == "en" else "PRIVACIDADE.md")))

    # -- Creditos
    lista = ctk.CTkScrollableFrame(abas.tab(_("Créditos")), fg_color=CARD, scrollbar_button_color=BORDA)
    lista.pack(fill="both", expand=True, padx=2, pady=2)
    ctk.CTkLabel(lista, text=_("O OpenBokeh só existe graças a estes projetos abertos. Obrigado!"),
                 font=ctk.CTkFont(F, 12), text_color=SUAVE, anchor="w").pack(fill="x", pady=(0, 8))
    for nome, autor, uso, lic, url in CREDITOS:
        linha = ctk.CTkFrame(lista, fg_color=CARD_2, corner_radius=10)
        linha.pack(fill="x", pady=3)
        linha.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(linha, text=nome, font=ctk.CTkFont(F, 13, "bold"), text_color=TEXTO, anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(linha, text=lic, font=ctk.CTkFont(F, 11, "bold"), text_color=ACENTO, anchor="e"
                     ).grid(row=0, column=1, sticky="e", padx=12, pady=(8, 0))
        ctk.CTkLabel(linha, text=f"{uso}  ·  {autor}", font=ctk.CTkFont(F, 11), text_color=SUAVE, anchor="w"
                     ).grid(row=1, column=0, sticky="w", padx=12)
        link = ctk.CTkLabel(linha, text=url, font=ctk.CTkFont(F, 11, underline=True), text_color="#8FB4FF",
                            anchor="w", cursor="hand2")
        link.grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))
        link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
    ctk.CTkLabel(lista, text=MARCAS, font=ctk.CTkFont(F, 11), text_color=SUAVE, wraplength=520,
                 justify="left", anchor="w").pack(fill="x", pady=(10, 0))

    # -- Licenca
    caixa_texto(abas.tab(_("Licença")), _arquivo("LICENSE"))

    ctk.CTkButton(j, text=_("Fechar"), command=j.destroy, width=120, height=36, corner_radius=10,
                  font=ctk.CTkFont(F, 13), fg_color=ACENTO, hover_color=ACENTO_HOVER
                  ).pack(pady=(0, 18))
