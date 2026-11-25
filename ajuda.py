"""Dialogos de ajuda no visual do OpenBokeh: primeiros passos, solucao de
problemas e erro fatal (substitui a caixa de erro padrao do Windows)."""

import os

import versao as V
from i18n import _

CORES = dict(BG="#0D0A18", CARD="#16122A", CARD_2="#211B3D", BORDA="#2C2552", TEXTO="#EEEBFA",
             SUAVE="#9C95BE", ACENTO="#7C5CFF", ACENTO_HOVER="#6847F0", ERRO="#FF6B81")
F = "Segoe UI"

PASSOS = [
    ("1", _("Escolha a câmera no seu app de chamada"),
     _("No Google Meet, Zoom, Teams, Discord ou OBS, selecione a câmera “OpenBokeh Camera”. "
     "Pronto: o fundo desfocado aparece para todo mundo.")),
    ("2", _("Ajuste o visual"),
     _("Troque o efeito (desfoque, imagem, vídeo ou cor) e use as abas ao lado para luz, ruído e "
     "enquadramento automático. Salve combinações como perfis na aba Mais.")),
    ("3", _("Precisa sair um instante?"),
     _("Aperte Ctrl+Alt+B (atalho padrão, funciona com o Meet aberto) para mostrar a tela “Volto já” sem desligar a câmera.")),
    ("4", _("Grave a tela"),
     _("Na área “Gravar tela”, no topo da janela, clique em “Iniciar gravação” ou aperte Ctrl+Alt+R em qualquer "
     "app. A sua webcam entra num círculo, com o microfone sem ruído e o som do PC.")),
    ("5", _("Ele fica na bandeja"),
     _("Fechar a janela deixa o OpenBokeh ao lado do relógio. Sem nenhum app usando a câmera, a webcam "
     "desliga sozinha para economizar energia e privacidade.")),
]

PROBLEMAS = [
    (_("A câmera “OpenBokeh Camera” não aparece no app de chamada"),
     _("Feche e abra de novo o app de chamada (ou recarregue a página do Meet). Se continuar, reinstale o OpenBokeh.")),
    (_("No Meet aparece “OpenBokeh está fechado”"),
     _("Abra o OpenBokeh (menu Iniciar). Se ele estiver na bandeja, a imagem aparece em cerca de 2 segundos.")),
    (_("“A webcam está sendo usada por outro programa”"),
     _("Algum app abriu a sua webcam de verdade em vez da OpenBokeh Camera. Nesse app, troque "
     "para “OpenBokeh Camera”. O OpenBokeh se reconecta sozinho.")),
    (_("Imagem lenta ou travando"),
     _("Na aba Recorte, use Qualidade “Rápida”. Feche jogos ou programas pesados. Confira se a IA está na "
     "GPU (topo da janela); se estiver na CPU, atualize o driver da placa de vídeo.")),
    (_("Bordas piscando ou “fantasmas” no fundo"),
     _("Na aba Recorte, aumente Estabilidade (menos piscada) e Firmeza (menos fantasmas). Boa iluminação "
     "no rosto ajuda muito a IA.")),
    (_("Imagem escura ou granulada"),
     _("Na aba Imagem, aumente Correção de luz e Redução de ruído, ou use o perfil “Ambiente escuro”.")),
    (_("Não consigo gravar na pasta Vídeos"),
     _("O “Acesso controlado a pastas” do Windows protege Vídeos, Documentos e Imagens. O OpenBokeh grava então em "
       "“Gravações OpenBokeh”, na sua pasta de usuário. Para usar a pasta Vídeos: Segurança do Windows › Proteção contra "
       "ransomware › Permitir um aplicativo › adicionar o OpenBokeh.")),
    (_("A gravação ficou com a imagem ou o som atrasado"),
     _("Feche jogos e programas pesados durante a gravação, ou use 30 quadros por segundo e o preset Compacta.")),
    (_("Texto da camiseta aparece invertido para os outros"),
     _("Desligue “Espelhar imagem” em Opções. Os apps de chamada já espelham só a sua prévia.")),
]


def _janela(root, titulo, largura=600, altura=560):
    import customtkinter as ctk
    j = ctk.CTkToplevel(root, fg_color=CORES["BG"])
    j.title(titulo)
    j.geometry(f"{largura}x{altura}")
    j.resizable(False, False)
    if root is not None:
        j.transient(root)
    j.after(250, lambda: (j.lift(), j.focus_force()))
    ico = os.path.join(_pasta_assets(), "icone.ico")
    if os.path.exists(ico):
        j.after(300, lambda: j.iconbitmap(ico))
    return j


def _pasta_assets():
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")


def _cabecalho(j, titulo, subtitulo):
    import customtkinter as ctk
    from PIL import Image
    topo = ctk.CTkFrame(j, fg_color="transparent")
    topo.pack(fill="x", padx=24, pady=(20, 10))
    logo = os.path.join(_pasta_assets(), "logo.png")
    if os.path.exists(logo):
        ctk.CTkLabel(topo, image=ctk.CTkImage(Image.open(logo), size=(44, 44)), text="").pack(side="left")
    t = ctk.CTkFrame(topo, fg_color="transparent")
    t.pack(side="left", padx=(12, 0))
    ctk.CTkLabel(t, text=titulo, font=ctk.CTkFont(F, 20, "bold"), text_color=CORES["TEXTO"],
                 height=26, anchor="w").pack(anchor="w")
    ctk.CTkLabel(t, text=subtitulo, font=ctk.CTkFont(F, 12), text_color=CORES["SUAVE"],
                 height=18, anchor="w").pack(anchor="w")


def primeiros_passos(root, ao_fechar=None):
    import customtkinter as ctk
    j = _janela(root, _("Bem-vindo ao {nome}").format(nome=V.NOME), 600, 660)
    _cabecalho(j, _("Bem-vindo ao {nome}!").format(nome=V.NOME), _("Cinco coisas para começar bem"))
    lista = ctk.CTkFrame(j, fg_color="transparent")
    lista.pack(fill="both", expand=True, padx=24)
    for num, titulo, texto in PASSOS:
        c = ctk.CTkFrame(lista, fg_color=CORES["CARD"], corner_radius=12, border_width=1, border_color=CORES["BORDA"])
        c.pack(fill="x", pady=5)
        ctk.CTkLabel(c, text=num, width=34, height=34, corner_radius=17, fg_color=CORES["ACENTO"],
                     text_color="#FFFFFF", font=ctk.CTkFont(F, 15, "bold")).pack(side="left", padx=14, pady=14)
        t = ctk.CTkFrame(c, fg_color="transparent")
        t.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 14))
        ctk.CTkLabel(t, text=titulo, font=ctk.CTkFont(F, 13, "bold"), text_color=CORES["TEXTO"], anchor="w").pack(fill="x")
        ctk.CTkLabel(t, text=texto, font=ctk.CTkFont(F, 12), text_color=CORES["SUAVE"], anchor="w",
                     justify="left", wraplength=440).pack(fill="x")

    def fechar():
        if ao_fechar:
            ao_fechar()
        j.destroy()
    j.protocol("WM_DELETE_WINDOW", fechar)
    ctk.CTkButton(j, text=_("Começar"), command=fechar, width=160, height=38, corner_radius=10,
                  font=ctk.CTkFont(F, 14), fg_color=CORES["ACENTO"], hover_color=CORES["ACENTO_HOVER"]
                  ).pack(pady=(10, 20))
    return j


def solucao_problemas(root, abrir_registro=None, copiar_diagnostico=None):
    import customtkinter as ctk
    j = _janela(root, _("Solução de problemas"), 640, 620)
    _cabecalho(j, _("Solução de problemas"), _("As dúvidas mais comuns e como resolver"))
    lista = ctk.CTkScrollableFrame(j, fg_color="transparent", scrollbar_button_color=CORES["BORDA"])
    lista.pack(fill="both", expand=True, padx=20)
    for pergunta, resposta in PROBLEMAS:
        c = ctk.CTkFrame(lista, fg_color=CORES["CARD"], corner_radius=12, border_width=1, border_color=CORES["BORDA"])
        c.pack(fill="x", pady=4)
        ctk.CTkLabel(c, text=pergunta, font=ctk.CTkFont(F, 13, "bold"), text_color=CORES["TEXTO"], anchor="w",
                     justify="left", wraplength=540).pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(c, text=resposta, font=ctk.CTkFont(F, 12), text_color=CORES["SUAVE"], anchor="w",
                     justify="left", wraplength=540).pack(fill="x", padx=14, pady=(0, 10))
    botoes = ctk.CTkFrame(j, fg_color="transparent")
    botoes.pack(pady=(10, 18))
    estilo = dict(height=36, corner_radius=10, font=ctk.CTkFont(F, 13), border_width=1)
    if copiar_diagnostico:
        ctk.CTkButton(botoes, text=_("Copiar diagnóstico"), command=copiar_diagnostico, fg_color=CORES["CARD_2"],
                      hover_color=CORES["BORDA"], border_color=CORES["BORDA"], **estilo).pack(side="left", padx=5)
    if abrir_registro:
        ctk.CTkButton(botoes, text=_("Abrir registro"), command=abrir_registro, fg_color=CORES["CARD_2"],
                      hover_color=CORES["BORDA"], border_color=CORES["BORDA"], **estilo).pack(side="left", padx=5)
    ctk.CTkButton(botoes, text=_("Fechar"), command=j.destroy, fg_color=CORES["ACENTO"], hover_color=CORES["ACENTO_HOVER"],
                  border_color=CORES["ACENTO"], **estilo).pack(side="left", padx=5)
    return j


def erro_fatal(titulo, texto, pasta_registro=None):
    """Quando o app nao consegue nem abrir: janela propria, no lugar da caixa
    de erro padrao do Windows."""
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    j = ctk.CTk(fg_color=CORES["BG"])
    j.title(V.NOME)
    j.geometry("520x330")
    j.resizable(False, False)
    ico = os.path.join(_pasta_assets(), "icone.ico")
    if os.path.exists(ico):
        j.after(300, lambda: j.iconbitmap(ico))
    _cabecalho(j, titulo, f"{V.NOME} {V.VERSAO}")
    ctk.CTkLabel(j, text=texto, font=ctk.CTkFont(F, 13), text_color=CORES["TEXTO"], justify="left",
                 wraplength=460, anchor="w").pack(fill="x", padx=28, pady=(6, 10))
    botoes = ctk.CTkFrame(j, fg_color="transparent")
    botoes.pack(side="bottom", pady=20)
    if pasta_registro and os.path.isdir(pasta_registro):
        ctk.CTkButton(botoes, text=_("Abrir pasta de registros"), command=lambda: os.startfile(pasta_registro),
                      height=36, corner_radius=10, fg_color=CORES["CARD_2"], hover_color=CORES["BORDA"],
                      border_width=1, border_color=CORES["BORDA"]).pack(side="left", padx=6)
    ctk.CTkButton(botoes, text=_("Fechar"), command=j.destroy, height=36, corner_radius=10,
                  fg_color=CORES["ACENTO"], hover_color=CORES["ACENTO_HOVER"]).pack(side="left", padx=6)
    j.mainloop()
