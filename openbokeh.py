"""
OpenBokeh - fundo desfocado com IA para webcam, gratuito e livre.
Roda na GPU via DirectML: AMD Radeon, NVIDIA e Intel no Windows.

O resultado vai para a camera virtual "OpenBokeh Camera", que voce
escolhe no Meet, OBS, Discord, Zoom, Teams...

Linha de comando:
  --listar            lista as webcams
  --camera NOME       escolhe a webcam
  --cpu               forca a IA na CPU
  --sem-janela        roda sem interface (Ctrl+C para sair)
  --benchmark N       mede N quadros, salva teste_*.jpg e sai
"""

import argparse
import os
import sys
import time

import cv2

import motor as M
from i18n import _

NOME = "OpenBokeh"

# ---- paleta (combina com a logo)
BG = "#0D0A18"
CARD = "#16122A"
CARD_2 = "#211B3D"
BORDA = "#2C2552"
TEXTO = "#EEEBFA"
SUAVE = "#9C95BE"
ACENTO = "#7C5CFF"
ACENTO_HOVER = "#6847F0"
ROSA = "#FF4FA3"
VERDE = "#3DDC97"
ERRO = "#FF6B81"

MODOS = [("desfoque", _("Desfoque")), ("imagem", _("Imagem")), ("video", _("Vídeo")), ("cor", _("Cor")), ("nenhum", _("Nenhum"))]
QUALIDADES = [("leve", _("Leve")), ("rapido", _("Rápida")), ("equilibrado", _("Equilibrada")), ("maximo", _("Máxima"))]

PREV_W, PREV_H = 720, 405      # previa no modo janela (fixo)
LATERAL_W = 340                # lateral (fixa)


# ---------------------------------------------------------------- interface
def rodar_janela(motor, cfg, na_bandeja=False):
    import tkinter as tk
    from tkinter import filedialog, colorchooser
    import customtkinter as ctk
    from PIL import Image, ImageTk

    assets = os.path.join(M.PASTA, "assets")
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenBokeh.App")
    except Exception:
        pass

    ctk.set_appearance_mode("dark")
    root = ctk.CTk(fg_color=BG)
    root.title(NOME)
    try:
        root.iconbitmap(os.path.join(assets, "icone.ico"))
        # o customtkinter troca o icone logo depois de abrir; reaplica
        root.after(250, lambda: root.iconbitmap(os.path.join(assets, "icone.ico")))
    except Exception:
        pass
    root.resizable(False, False)       # liberado depois de medir o layout
    # colunas vazias nas pontas: maximizado, o conteudo fica centralizado
    root.grid_columnconfigure((0, 3), weight=1)
    root.grid_rowconfigure(4, weight=1)

    F = "Segoe UI"
    f_titulo = ctk.CTkFont(F, 22, "bold")
    f_secao = ctk.CTkFont(F, 13, "bold")
    f_normal = ctk.CTkFont(F, 13)
    f_peq = ctk.CTkFont(F, 11)
    f_valor = ctk.CTkFont(F, 12, "bold")

    salvar_pendente = [None]

    def mudou():
        """Salva o config.json um pouco depois da ultima mudanca."""
        if salvar_pendente[0]:
            root.after_cancel(salvar_pendente[0])
        salvar_pendente[0] = root.after(800, lambda: M.salvar_config(cfg))

    def cartao(pai, titulo=None, **grid):
        c = ctk.CTkFrame(pai, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDA)
        c.grid(**grid)
        corpo = ctk.CTkFrame(c, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=16, pady=(12, 14))
        if titulo:
            ctk.CTkLabel(corpo, text=titulo.upper(), font=f_secao, text_color=SUAVE,
                         anchor="w").pack(fill="x", pady=(0, 6))
        return corpo

    # ================= cabecalho
    topo = ctk.CTkFrame(root, fg_color="transparent")
    topo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=20, pady=(6, 10))
    topo.grid_columnconfigure(1, weight=1)
    marca = ctk.CTkFrame(topo, fg_color="transparent")
    marca.grid(row=0, column=0, sticky="w")
    try:
        logo = ctk.CTkImage(Image.open(os.path.join(assets, "logo.png")), size=(42, 42))
        ctk.CTkLabel(marca, image=logo, text="").pack(side="left")
    except Exception:
        pass
    textos = ctk.CTkFrame(marca, fg_color="transparent")
    textos.pack(side="left", padx=(12, 0))
    ctk.CTkLabel(textos, text=NOME, font=f_titulo, text_color=TEXTO, height=26, anchor="w").pack(anchor="w")
    ctk.CTkLabel(textos, text=_("Câmera com IA e gravação de tela · grátis e livre"),
                 font=f_peq, text_color=SUAVE, height=16, anchor="w").pack(anchor="w")

    direita_topo = ctk.CTkFrame(topo, fg_color="transparent")
    direita_topo.grid(row=0, column=2, sticky="e")
    import sobre as S

    def abrir_sobre():
        info = _("  IA: {ia}  ·  webcam: {webcam}  ·  câmera virtual: {virtual}\n"
                 "  Configurações e registro: {pasta}").format(ia=motor.dispositivo, webcam=motor.nome_camera,
                                                              virtual=motor.cam_desc, pasta=os.path.dirname(M.CONFIG_ARQ))
        S.abrir(root, (BG, CARD, CARD_2, BORDA, TEXTO, SUAVE, ACENTO, ACENTO_HOVER),
                os.path.join(assets, "logo.png"), info)
    ctk.CTkButton(direita_topo, text="⚙", width=36, height=32, corner_radius=10, font=ctk.CTkFont(F, 16),
                  fg_color="transparent", hover_color=CARD_2, text_color=SUAVE, border_width=1, border_color=BORDA,
                  command=lambda: abrir_config()).pack(side="left", padx=(0, 10))
    bt_grav = ctk.CTkButton(direita_topo, text="", width=150, height=32, corner_radius=10, font=f_normal,
                            border_width=1, command=lambda: grav.alternar())
    bt_priv = ctk.CTkButton(direita_topo, text="", width=150, height=32, corner_radius=10, font=f_normal,
                            border_width=1)
    bt_priv.pack(side="left", padx=(0, 10))
    pilula = ctk.CTkLabel(direita_topo, text=_("  iniciando...  "), font=f_peq, text_color=TEXTO,
                          fg_color=CARD_2, corner_radius=12, height=28)
    pilula.pack(side="left")

    def pintar_privacidade():
        if motor.privacidade:
            bt_priv.configure(text=_("▶  Voltar à câmera"), fg_color=ROSA, hover_color="#E03C8C",
                              text_color="#FFFFFF", border_color=ROSA)
        else:
            bt_priv.configure(text=_("⏸  Volto já"), fg_color=CARD_2, hover_color=BORDA,
                              text_color=TEXTO, border_color=BORDA)

    def alternar_privacidade():
        motor.alternar_privacidade()
        pintar_privacidade()
    bt_priv.configure(command=alternar_privacidade)
    pintar_privacidade()

    # ================= coluna esquerda: previa + cartoes
    esq = ctk.CTkFrame(root, fg_color="transparent")
    esq.grid(row=3, column=1, sticky="n", padx=(20, 10), pady=(0, 20))

    moldura = ctk.CTkFrame(esq, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDA)
    moldura.pack()
    caixa = tk.Frame(moldura, width=PREV_W, height=PREV_H, bg="#000000", highlightthickness=0)
    caixa.pack(padx=8, pady=8)
    caixa.pack_propagate(False)
    previa = tk.Label(caixa, bg="#000000", bd=0)
    previa.pack(fill="both", expand=True)
    # ---- avisos amigaveis por cima da previa (ver mensagens.py)
    import mensagens as MSG
    CORES_NIVEL = {"info": ("#14223A", "#5FA8FF", "ⓘ"), "aviso": ("#2B2413", "#FFC857", "⚠"),
                   "erro": ("#2E1420", ERRO, "✕")}
    ORDEM_NIVEL = {"erro": 0, "aviso": 1, "info": 2}
    cartao_aviso = ctk.CTkFrame(caixa, corner_radius=12, border_width=1, fg_color=CARD, bg_color="#000000")
    cartao_aviso.grid_columnconfigure(1, weight=1)
    ca_icone = ctk.CTkLabel(cartao_aviso, text="", font=ctk.CTkFont(F, 18, "bold"), width=28)
    ca_icone.grid(row=0, column=0, rowspan=2, padx=(14, 6), pady=10, sticky="n")
    ca_titulo = ctk.CTkLabel(cartao_aviso, text="", font=f_secao, text_color=TEXTO, anchor="w", justify="left")
    ca_titulo.grid(row=0, column=1, sticky="w", pady=(10, 0))
    ca_texto = ctk.CTkLabel(cartao_aviso, text="", font=f_peq, text_color=TEXTO, anchor="w", justify="left",
                            wraplength=410)
    ca_texto.grid(row=1, column=1, sticky="w", pady=(2, 10))
    ca_botao = ctk.CTkButton(cartao_aviso, text="", width=120, height=30, corner_radius=8, font=f_peq)
    ca_botao.grid(row=0, column=2, rowspan=2, padx=(10, 4))
    aviso_atual = [None]
    dispensados = set()

    def dispensar_aviso():
        if aviso_atual[0]:
            dispensados.add(aviso_atual[0][0])
        cartao_aviso.place_forget()
        aviso_atual[0] = None
    ctk.CTkButton(cartao_aviso, text="✕", width=28, height=28, corner_radius=8, fg_color="transparent",
                  hover_color=BORDA, text_color=SUAVE, command=dispensar_aviso
                  ).grid(row=0, column=3, rowspan=2, padx=(0, 8))

    def executar_acao(acao):
        if acao == "tentar":
            motor.tentar_webcam_agora()
            toast(_("Procurando a webcam…"))
        elif acao == "privacidade":
            os.startfile("ms-settings:privacy-webcam")
        elif acao == "escolher_imagem":
            escolher_imagem()
        elif acao == "escolher_video":
            escolher_video()
        elif acao == "registro":
            abrir_registro()
        elif acao == "ajustes_webcam":
            if not motor.abrir_ajustes_webcam():
                toast(_("A webcam precisa estar ligada para abrir os ajustes"))

    def mostrar_problemas():
        ativos = dict(motor.problemas)
        dispensados.intersection_update(ativos)          # resolvido volta a poder aparecer
        candidatos = [c for c in ativos if c not in dispensados]
        if not candidatos:
            if aviso_atual[0] is not None:
                cartao_aviso.place_forget()
                aviso_atual[0] = None
            return
        cod = min(candidatos, key=lambda c: ORDEM_NIVEL[MSG.MENSAGENS.get(c, MSG.MENSAGENS["inesperado"])["nivel"]])
        if aviso_atual[0] == (cod, ativos[cod]):
            return
        nivel, titulo, texto, dica, acao = MSG.montar(cod, **ativos[cod])
        fundo, cor, icone = CORES_NIVEL[nivel]
        cartao_aviso.configure(fg_color=fundo, border_color=cor)
        ca_icone.configure(text=icone, text_color=cor)
        ca_titulo.configure(text=titulo)
        ca_texto.configure(text=f"{texto}\n{dica}")
        if acao:
            ca_botao.configure(text=acao[1], command=lambda a=acao[0]: executar_acao(a), fg_color=cor,
                               hover_color=cor, text_color="#16122A")
            ca_botao.grid()
        else:
            ca_botao.grid_remove()
        cartao_aviso.place(relx=0.5, y=14, anchor="n", relwidth=0.95)
        cartao_aviso.lift()
        aviso_atual[0] = (cod, ativos[cod])

    toast_lbl = ctk.CTkLabel(caixa, text="", fg_color=CARD_2, bg_color="#000000", corner_radius=10,
                             text_color=TEXTO, font=f_normal, height=34)
    toast_timer = [None]

    def toast(texto):
        """Mensagem curta de confirmacao, some sozinha."""
        toast_lbl.configure(text=f"   {texto}   ")
        toast_lbl.place(relx=0.5, rely=0.96, anchor="s")
        toast_lbl.lift()
        if toast_timer[0]:
            root.after_cancel(toast_timer[0])
        toast_timer[0] = root.after(2800, toast_lbl.place_forget)

    # ---- dica discreta: qual camera escolher no programa de videochamada
    faixa = ctk.CTkFrame(esq, fg_color="transparent")
    faixa.pack(fill="x", pady=(8, 0))
    faixa_txt = ctk.CTkLabel(faixa, text="", font=f_peq, text_color=SUAVE, anchor="w", justify="left")
    faixa_txt.pack(side="left", padx=(4, 0))

    def texto_faixa():
        return _("ⓘ  No Meet, Zoom ou OBS, escolha a câmera “{camera}”.").format(camera=motor.cam_desc)
    faixa_txt.configure(text=texto_faixa())

    linha_cartoes = ctk.CTkFrame(esq, fg_color="transparent")
    linha_cartoes.pack(fill="x", pady=(12, 0))
    linha_cartoes.grid_columnconfigure(0, weight=3)
    linha_cartoes.grid_columnconfigure(1, weight=2)

    # ---- cartao: webcam e efeito
    c_efeito = cartao(linha_cartoes, _("Webcam e efeito"), row=0, column=0, sticky="nsew", padx=(0, 12))
    cams = [n for n in M.listar_cameras() if not M.eh_virtual(n)] or [motor.nome_camera]
    var_cam = ctk.StringVar(value=motor.nome_camera or cfg["camera"])

    def trocar_camera(nome):
        if nome == motor.nome_camera:
            return
        pilula.configure(text=_("  abrindo {nome}...  ").format(nome=nome))
        root.update_idletasks()
        try:
            motor.abrir_camera(nome)
            motor.sem_webcam = False
            motor.resolver("webcam_ocupada", "webcam_ausente", "webcam_bloqueada", "webcam_desconectada")
            faixa_txt.configure(text=texto_faixa())
            mudou()
            toast(_("Usando a webcam “{nome}”").format(nome=nome))
        except Exception as e:
            print(f"[webcam] troca falhou: {e}")
            toast(_("Não foi possível abrir “{nome}” — ela pode estar em uso por outro app").format(nome=nome))
            var_cam.set(motor.nome_camera or cfg["camera"])

    ctk.CTkOptionMenu(c_efeito, values=cams, variable=var_cam, command=trocar_camera, height=34,
                      corner_radius=10, font=f_normal, dropdown_font=f_normal, fg_color=CARD_2,
                      button_color=BORDA, button_hover_color=ACENTO, dropdown_fg_color=CARD_2,
                      dropdown_hover_color=ACENTO, text_color=TEXTO).pack(fill="x")

    rotulo_para_modo = {r: k for k, r in MODOS}
    var_modo = ctk.StringVar(value=dict(MODOS)[cfg["modo"]])

    ctk.CTkSegmentedButton(c_efeito, values=[r for _c, r in MODOS], variable=var_modo,
                           command=lambda r: trocar_modo(rotulo_para_modo[r]),
                           height=34, corner_radius=10, font=f_normal, fg_color=CARD_2,
                           selected_color=ACENTO, selected_hover_color=ACENTO_HOVER,
                           unselected_color=CARD_2, unselected_hover_color=BORDA, text_color=TEXTO
                           ).pack(fill="x", pady=(10, 0))

    # botao "contextual": muda conforme o efeito (imagem, video ou cor)
    linha_bt = ctk.CTkFrame(c_efeito, fg_color="transparent", height=40)
    linha_bt.pack(fill="x", pady=(10, 0))
    linha_bt.pack_propagate(False)
    estilo_bt = dict(height=40, corner_radius=10, font=f_normal, fg_color=CARD_2, hover_color=BORDA,
                     text_color=TEXTO, border_width=1, border_color=BORDA, compound="left", anchor="w")
    bt_escolher = ctk.CTkButton(linha_bt, text="", **estilo_bt)
    dica_modo = ctk.CTkLabel(linha_bt, text="", font=f_peq, text_color=SUAVE, anchor="w", justify="left")

    def miniatura(caminho, video=False):
        try:
            if video:
                cap = cv2.VideoCapture(caminho, cv2.CAP_MSMF)      # aceita acentos no caminho
                ok, q = cap.read()
                cap.release()
                if not ok:
                    return None
                img = Image.fromarray(cv2.cvtColor(q, cv2.COLOR_BGR2RGB))
            else:
                img = Image.open(caminho).convert("RGB")
            img.thumbnail((96, 54))
            return ctk.CTkImage(img, size=(img.width * 22 // img.height, 22))
        except Exception:
            return None

    def amostra_cor():
        r, g, b = cfg["cor_fundo"]
        return ctk.CTkImage(Image.new("RGB", (22, 22), (r, g, b)), size=(22, 22))

    def nome_curto(caminho, n=22):
        nome = os.path.basename(caminho)
        return nome if len(nome) <= n else nome[:n - 1] + "…"

    def atualizar_botao_modo():
        modo = cfg["modo"]
        bt_escolher.pack_forget()
        dica_modo.pack_forget()
        if modo == "imagem":
            img = miniatura(cfg["imagem_fundo"])
            txt = _("  Escolher imagem   ·   {arquivo}").format(arquivo=nome_curto(cfg['imagem_fundo'])) if img else _("  Escolher imagem de fundo")
            bt_escolher.configure(text=txt, image=img, command=escolher_imagem)
            bt_escolher.pack(fill="both", expand=True)
        elif modo == "video":
            img = miniatura(cfg["video_fundo"], video=True)
            txt = _("  Escolher vídeo   ·   {arquivo}").format(arquivo=nome_curto(cfg['video_fundo'])) if img else _("  Escolher vídeo de fundo (MP4, MOV, WMV…)")
            bt_escolher.configure(text=txt, image=img, command=escolher_video)
            bt_escolher.pack(fill="both", expand=True)
        elif modo == "cor":
            r, g, b = cfg["cor_fundo"]
            bt_escolher.configure(text=_("  Escolher cor   ·   {cor}").format(cor=f"#{r:02X}{g:02X}{b:02X}"), image=amostra_cor(),
                                  command=escolher_cor)
            bt_escolher.pack(fill="both", expand=True)
        elif modo == "desfoque":
            dica_modo.configure(text=_("Ajuste a intensidade na aba “Imagem”, ao lado →"))
            dica_modo.pack(fill="both", expand=True, padx=4)
        else:
            dica_modo.configure(text=_("Sem efeito: a imagem da webcam passa direto (com luz e ruído ajustados)."))
            dica_modo.pack(fill="both", expand=True, padx=4)

    def trocar_modo(modo):
        cfg["modo"] = modo
        var_modo.set(dict(MODOS)[modo])
        atualizar_botao_modo()
        mudou()

    def escolher_imagem():
        arq = filedialog.askopenfilename(
            parent=root, title=_("Imagem de fundo"),
            filetypes=[(_("Imagens"), "*.jpg *.jpeg *.png *.bmp *.webp"), (_("Todos"), "*.*")])
        if arq:
            cfg["imagem_fundo"] = arq
            trocar_modo("imagem")

    def escolher_video():
        arq = filedialog.askopenfilename(
            parent=root, title=_("Vídeo de fundo"),
            filetypes=[(_("Vídeos"), "*.mp4 *.m4v *.mov *.wmv *.avi"), (_("Todos"), "*.*")])
        if arq:
            cfg["video_fundo"] = arq
            trocar_modo("video")

    def escolher_cor():
        r, g, b = cfg["cor_fundo"]
        cor = colorchooser.askcolor(parent=root, color=f"#{r:02x}{g:02x}{b:02x}", title=_("Cor de fundo"))
        if cor and cor[0]:
            cfg["cor_fundo"] = [int(x) for x in cor[0]]
            trocar_modo("cor")

    atualizar_botao_modo()

    # ---- cartao: opcoes
    c_opc = cartao(linha_cartoes, _("Opções"), row=0, column=1, sticky="nsew")
    estilo_sw = dict(font=f_normal, text_color=TEXTO, progress_color=ACENTO, button_color="#FFFFFF",
                     button_hover_color="#E6E0FF", fg_color=BORDA, switch_width=40, switch_height=20)
    var_esp = ctk.BooleanVar(value=cfg["espelhar"])
    ctk.CTkSwitch(c_opc, text=_("Espelhar imagem"), variable=var_esp,
                  command=lambda: (cfg.__setitem__("espelhar", var_esp.get()), motor.pedir_reset(), mudou()),
                  **estilo_sw).pack(anchor="w", pady=3)
    var_enq = ctk.BooleanVar(value=cfg["enquadrar"])

    def trocar_enquadrar():
        cfg["enquadrar"] = var_enq.get()
        mudou()
    ctk.CTkSwitch(c_opc, text=_("Enquadramento automático"), variable=var_enq, command=trocar_enquadrar,
                  **estilo_sw).pack(anchor="w", pady=3)
    var_prev = ctk.BooleanVar(value=True)
    ctk.CTkSwitch(c_opc, text=_("Mostrar prévia"), variable=var_prev, **estilo_sw).pack(anchor="w", pady=3)
    var_mask = ctk.BooleanVar(value=False)
    ctk.CTkSwitch(c_opc, text=_("Ver recorte (P&B)"), variable=var_mask, **estilo_sw).pack(anchor="w", pady=3)
    var_mic = ctk.BooleanVar(value=cfg["microfone_limpo"])

    def trocar_microfone(ligar=None):
        """Liga/desliga o microfone sem ruido (switch, bandeja ou configuracoes)."""
        import microfone
        if ligar is None:
            ligar = var_mic.get()
        if motor.microfone is None:
            var_mic.set(False)
            toast(_("Microfone sem ruído indisponível nesta instalação"))
            return
        cfg["microfone_limpo"] = bool(ligar)
        var_mic.set(cfg["microfone_limpo"])
        microfone.aplicar(motor.microfone, cfg)
        mudou()
        if bandeja is not None:
            bandeja.atualizar()
        if ligar and motor.microfone.erro:
            toast(motor.microfone.erro if len(motor.microfone.erro) < 90 else _("Falta configurar o microfone"))
            abrir_config("microfone")
        elif ligar:
            toast(_("Microfone sem ruído ligado — escolha “CABLE Output” como microfone no app de chamada"))
    ctk.CTkSwitch(c_opc, text=_("Microfone sem ruído"), variable=var_mic, command=trocar_microfone,
                  **estilo_sw).pack(anchor="w", pady=3)

    # ================= lateral: ajustes em abas
    lat = ctk.CTkFrame(root, fg_color="transparent", width=LATERAL_W)
    lat.grid(row=3, column=2, sticky="n", padx=(10, 20), pady=(0, 20))
    lat.grid_columnconfigure(0, minsize=LATERAL_W)

    abas = ctk.CTkTabview(lat, width=LATERAL_W, height=540, corner_radius=14, fg_color=CARD,
                          border_width=1, border_color=BORDA, segmented_button_fg_color=CARD_2,
                          segmented_button_selected_color=ACENTO, segmented_button_selected_hover_color=ACENTO_HOVER,
                          segmented_button_unselected_color=CARD_2, segmented_button_unselected_hover_color=BORDA,
                          text_color=TEXTO)
    abas.grid(row=0, column=0, sticky="ew")
    for nome in (_("Imagem"), _("Recorte"), _("Enquadrar"), _("Mais")):
        abas.add(nome)
    abas._segmented_button.configure(font=f_normal)

    def corpo_aba(nome):
        f = ctk.CTkFrame(abas.tab(nome), fg_color="transparent")
        f.pack(fill="both", expand=True, padx=8, pady=(2, 4))
        return f

    vars_ajuste = {}

    def deslizador(pai, titulo, chave, de, ate, dica, inteiro=True, ao_mudar=None):
        linha = ctk.CTkFrame(pai, fg_color="transparent")
        linha.pack(fill="x", pady=(4, 8))
        linha.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(linha, text=titulo, font=f_normal, text_color=TEXTO, anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        valor = ctk.CTkLabel(linha, text="", font=f_valor, text_color=TEXTO, fg_color=CARD_2,
                             corner_radius=8, width=44, height=22)
        valor.grid(row=0, column=1, sticky="e")
        var = ctk.DoubleVar(value=cfg[chave])

        def atualizar(_evento=None):
            v = round(var.get()) if inteiro else round(var.get(), 1)
            valor.configure(text=(f"{v}×" if chave == "zoom_max" else str(v)))
            if cfg[chave] != v:
                cfg[chave] = v
                if ao_mudar:
                    ao_mudar()
                mudou()
        ctk.CTkSlider(linha, from_=de, to=ate, variable=var, command=atualizar, height=18,
                      button_length=0, button_corner_radius=9, button_color="#FFFFFF",
                      button_hover_color="#E6E0FF", progress_color=ACENTO, fg_color=BORDA
                      ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ctk.CTkLabel(linha, text=dica, font=f_peq, text_color=SUAVE, anchor="w", height=16
                     ).grid(row=2, column=0, columnspan=2, sticky="w")
        atualizar()
        vars_ajuste[chave] = (var, atualizar)

    def titulo_secao(pai, texto, topo=0):
        ctk.CTkLabel(pai, text=texto.upper(), font=f_secao, text_color=SUAVE, anchor="w"
                     ).pack(fill="x", pady=(topo, 4))

    # -- aba Imagem
    t_img = corpo_aba(_("Imagem"))
    deslizador(t_img, _("Intensidade do desfoque"), "forca_desfoque", 1, 40, _("Quanto o fundo fica borrado"))
    deslizador(t_img, _("Correção de luz"), "correcao_luz", 0, 100, _("Clareia o rosto em ambiente escuro"))
    deslizador(t_img, _("Redução de ruído"), "reducao_ruido", 0, 100, _("Tira o granulado da webcam no rosto"))
    deslizador(t_img, _("Retoque de pele"), "retoque", 0, 100, _("Suaviza a pele sem borrar olhos e cabelo"))

    # -- aba Recorte
    t_rec = corpo_aba(_("Recorte"))
    deslizador(t_rec, _("Suavidade da borda"), "suavidade_borda", 0, 6, _("Mais alto = contorno mais macio"),
               inteiro=False)
    deslizador(t_rec, _("Estabilidade"), "estabilidade", 0, 95, _("Mais alto = menos piscada na borda"))
    deslizador(t_rec, _("Firmeza"), "firmeza", 0, 100, _("Mais alto = limpa “fantasmas” do fundo"))
    ctk.CTkLabel(t_rec, text=_("Qualidade da IA"), font=f_normal, text_color=TEXTO, anchor="w"
                 ).pack(fill="x", pady=(4, 6))
    rotulo_para_q = {r: k for k, r in QUALIDADES}
    var_q = ctk.StringVar(value=dict(QUALIDADES)[cfg["qualidade"]])

    def trocar_qualidade(rotulo):
        cfg["qualidade"] = rotulo_para_q[rotulo]
        motor.pedir_reset()
        mudou()
    ctk.CTkSegmentedButton(t_rec, values=[r for _c, r in QUALIDADES], variable=var_q, command=trocar_qualidade,
                           height=32, corner_radius=10, font=f_normal, fg_color=CARD_2,
                           selected_color=ACENTO, selected_hover_color=ACENTO_HOVER,
                           unselected_color=CARD_2, unselected_hover_color=BORDA, text_color=TEXTO
                           ).pack(fill="x")

    # -- aba Enquadrar
    t_enq = corpo_aba(_("Enquadrar"))
    ctk.CTkSwitch(t_enq, text=_("Enquadramento automático"), variable=var_enq, command=trocar_enquadrar,
                  **estilo_sw).pack(anchor="w", pady=(4, 10))
    deslizador(t_enq, _("Zoom máximo"), "zoom_max", 1.0, 2.5, _("Quanto pode aproximar quando você se afasta"),
               inteiro=False)
    deslizador(t_enq, _("Velocidade"), "velocidade_enquadrar", 1, 10, _("Quão rápido a câmera acompanha você"))

    titulo_secao(t_enq, _("Câmera redonda"), topo=6)
    var_red = ctk.BooleanVar(value=cfg["redonda"])

    def trocar_redonda():
        cfg["redonda"] = var_red.get()
        mudou()
    ctk.CTkSwitch(t_enq, text=_("Mostrar só um círculo"), variable=var_red, command=trocar_redonda,
                  **estilo_sw).pack(anchor="w", pady=(0, 6))
    deslizador(t_enq, _("Tamanho do círculo"), "tamanho_circulo", 30, 100, _("Em % da altura da imagem"))
    deslizador(t_enq, _("Anel em volta"), "borda_circulo", 0, 20, _("Espessura da borda branca (0 = sem)"))
    CORES_FORA = [("verde", _("Verde (OBS)")), ("preto", _("Preto")), ("branco", _("Branco"))]
    rotulo_para_cor = {r: k for k, r in CORES_FORA}
    var_cor_fora = ctk.StringVar(value=dict(CORES_FORA).get(cfg["cor_fora_circulo"], CORES_FORA[0][1]))

    def trocar_cor_fora(rotulo):
        cfg["cor_fora_circulo"] = rotulo_para_cor[rotulo]
        mudou()
    ctk.CTkSegmentedButton(t_enq, values=[r for _c, r in CORES_FORA], variable=var_cor_fora,
                           command=trocar_cor_fora, height=30, corner_radius=10, font=f_peq, fg_color=CARD_2,
                           selected_color=ACENTO, selected_hover_color=ACENTO_HOVER,
                           unselected_color=CARD_2, unselected_hover_color=BORDA, text_color=TEXTO
                           ).pack(fill="x", pady=(2, 2))
    ctk.CTkLabel(t_enq, text=_("No OBS: filtro “Chroma Key” na câmera, cor verde."),
                 font=f_peq, text_color=SUAVE, anchor="w").pack(fill="x")

    # -- aba Mais: perfis e privacidade
    t_mais = corpo_aba(_("Mais"))
    titulo_secao(t_mais, _("Perfis"))
    var_perfil = ctk.StringVar(value=next(iter(cfg["perfis"]), ""))
    menu_perfis = ctk.CTkOptionMenu(t_mais, values=list(cfg["perfis"]) or [_("(nenhum)")], variable=var_perfil,
                                    width=60, height=34, corner_radius=10, font=f_normal, dropdown_font=f_normal,
                                    fg_color=CARD_2, button_color=BORDA, button_hover_color=ACENTO,
                                    dropdown_fg_color=CARD_2, dropdown_hover_color=ACENTO, text_color=TEXTO)
    menu_perfis.pack(fill="x")
    linha_p = ctk.CTkFrame(t_mais, fg_color="transparent")
    linha_p.pack(fill="x", pady=(8, 0))
    linha_p.grid_columnconfigure((0, 1, 2), weight=1)
    estilo_bp = dict(width=60, height=34, corner_radius=10, font=f_normal, border_width=1)

    def atualizar_lista_perfis(selecionar=None):
        nomes = list(cfg["perfis"])
        menu_perfis.configure(values=nomes or [_("(nenhum)")])
        var_perfil.set(selecionar if selecionar in nomes else (nomes[0] if nomes else _("(nenhum)")))

    def aplicar_perfil():
        if M.aplicar_perfil(cfg, var_perfil.get()):
            sincronizar()
            motor.pedir_reset()
            mudou()
            aviso_perfil.configure(text=_("Perfil “{nome}” aplicado.").format(nome=var_perfil.get()))

    def salvar_perfil():
        dlg = ctk.CTkInputDialog(text=_("Nome do perfil (ex.: Reunião, Live, Aula):"), title=_("Salvar perfil"),
                                 fg_color=BG, button_fg_color=ACENTO, button_hover_color=ACENTO_HOVER,
                                 entry_fg_color=CARD_2, entry_border_color=BORDA)
        nome = (dlg.get_input() or "").strip()[:30]
        if nome:
            M.salvar_perfil(cfg, nome)
            atualizar_lista_perfis(nome)
            mudou()
            aviso_perfil.configure(text=_("Configuração atual salva como “{nome}”.").format(nome=nome))

    def excluir_perfil():
        nome = var_perfil.get()
        if nome in cfg["perfis"]:
            del cfg["perfis"][nome]
            atualizar_lista_perfis()
            mudou()
            aviso_perfil.configure(text=_("Perfil “{nome}” excluído.").format(nome=nome))

    ctk.CTkButton(linha_p, text=_("Aplicar"), command=aplicar_perfil, fg_color=ACENTO, hover_color=ACENTO_HOVER,
                  text_color="#FFFFFF", border_color=ACENTO, **estilo_bp).grid(row=0, column=0, sticky="ew", padx=(0, 4))
    ctk.CTkButton(linha_p, text=_("Salvar…"), command=salvar_perfil, fg_color=CARD_2, hover_color=BORDA,
                  text_color=TEXTO, border_color=BORDA, **estilo_bp).grid(row=0, column=1, sticky="ew", padx=4)
    ctk.CTkButton(linha_p, text=_("Excluir"), command=excluir_perfil, fg_color="transparent", hover_color=CARD_2,
                  text_color=SUAVE, border_color=BORDA, **estilo_bp).grid(row=0, column=2, sticky="ew", padx=(4, 0))
    aviso_perfil = ctk.CTkLabel(t_mais, text=_("Um perfil guarda efeito, fundo e todos os ajustes."),
                                font=f_peq, text_color=SUAVE, anchor="w", justify="left", wraplength=290)
    aviso_perfil.pack(fill="x", pady=(6, 0))

    titulo_secao(t_mais, _("Privacidade"), topo=18)
    ctk.CTkLabel(t_mais, text=_("Texto da tela “Volto já”"), font=f_normal, text_color=TEXTO, anchor="w"
                 ).pack(fill="x")
    var_texto = ctk.StringVar(value=cfg["texto_privacidade"])
    entrada = ctk.CTkEntry(t_mais, textvariable=var_texto, width=60, height=34, corner_radius=10, font=f_normal,
                           fg_color=CARD_2, border_color=BORDA, text_color=TEXTO)
    entrada.pack(fill="x", pady=(6, 0))

    def mudou_texto(*_args):
        cfg["texto_privacidade"] = var_texto.get()[:40]
        if motor.privacidade:
            motor.alternar_privacidade(True)      # redesenha a tela com o texto novo
        mudou()
    var_texto.trace_add("write", mudou_texto)
    rotulo_atalho = ctk.CTkLabel(t_mais, text="", font=f_peq, text_color=SUAVE, anchor="w", justify="left")
    rotulo_atalho.pack(fill="x", pady=(6, 0))

    import sistema as SIS
    ctk.CTkButton(t_mais, text=_("⚙  Todas as configurações…"), command=lambda: abrir_config(), height=36,
                  corner_radius=10, font=f_normal, fg_color=CARD_2, hover_color=BORDA, text_color=TEXTO,
                  border_width=1, border_color=BORDA).pack(fill="x", pady=(18, 0))

    def sincronizar():
        """Atualiza todos os controles a partir do cfg (ao aplicar perfil/restaurar)."""
        for k, (var, atualizar) in vars_ajuste.items():
            var.set(cfg[k])
            atualizar()
        var_q.set(dict(QUALIDADES)[cfg["qualidade"]])
        var_esp.set(cfg["espelhar"])
        var_enq.set(cfg["enquadrar"])
        var_red.set(cfg["redonda"])
        var_mic.set(cfg["microfone_limpo"])
        var_cor_fora.set(dict(CORES_FORA).get(cfg["cor_fora_circulo"], CORES_FORA[0][1]))
        var_modo.set(dict(MODOS)[cfg["modo"]])
        atualizar_botao_modo()

    def restaurar():
        for k, v in M.AJUSTES_PADRAO.items():
            cfg[k] = v
        sincronizar()
        motor.pedir_reset()
        mudou()

    ctk.CTkButton(lat, text=_("↺  Restaurar ajustes padrão"), command=restaurar, height=40, corner_radius=10,
                  font=f_normal, fg_color="transparent", hover_color=CARD_2, text_color=SUAVE,
                  border_width=1, border_color=BORDA).grid(row=1, column=0, sticky="ew", pady=(12, 0))

    # ================= atalhos globais configuraveis ("Volto ja" e liga/desliga efeito)
    import atalho as A
    atalhos = {}
    import gravacao_ui as GU
    grav = GU.Controle(root, motor, cfg, toast, janelas=lambda: [getattr(root, "_janela_config", None)])

    ultimo_modo = [None]
    ultimo_bt = [None]

    def pintar_gravacao():
        """No topo, so durante a gravacao: cronometro vermelho que para ao clicar."""
        st = grav.status()
        if st:
            if ultimo_bt[0] is None:
                bt_grav.configure(fg_color="#C62828", hover_color="#A31F1F", text_color="#FFFFFF",
                                  border_color="#C62828")
            if st != ultimo_bt[0]:
                ultimo_bt[0] = st
                bt_grav.configure(text=st)
            if not bt_grav.winfo_manager():      # (minimizada, "ismapped" e sempre falso)
                bt_grav.pack(side="left", padx=(0, 10), before=bt_priv)
        else:
            ultimo_bt[0] = None
            if bt_grav.winfo_manager():
                bt_grav.pack_forget()
        # o "●" no botao "Gravar tela" so muda quando a gravacao comeca/termina
        # (reconfigurar o botao a cada meio segundo fazia ele piscar)
        rotulo_grav = _("🖥  Gravar tela  ●") if st else _("🖥  Gravar tela")
        alvo = _("📷  Câmera") if pagina[0] == "camera" else rotulo_grav
        if ultimo_modo[0] != (rotulo_grav, alvo):
            ultimo_modo[0] = (rotulo_grav, alvo)
            aba_modo.configure(values=[_("📷  Câmera"), rotulo_grav])
            var_pagina.set(alvo)
    grav.ao_mudar.append(pintar_gravacao)
    grav.ao_mudar.append(lambda: bandeja is not None and bandeja.atualizar())

    # ================= duas areas: Camera (efeitos para chamadas) e Gravar tela
    import pagina_gravacao as PG
    pagina = ["camera"]
    var_pagina = ctk.StringVar(value=_("📷  Câmera"))
    barra_modo = ctk.CTkFrame(root, fg_color="transparent")
    barra_modo.grid(row=2, column=1, columnspan=2, sticky="ew", padx=20, pady=(0, 12))

    def trocar_pagina(rotulo=None, nome=None):
        nome = nome or ("camera" if rotulo == _("📷  Câmera") else "gravar")
        if nome == pagina[0]:
            return
        pagina[0] = nome
        if nome == "camera":
            pg_grav.esconder()
            esq.grid()
            lat.grid()
        else:
            esq.grid_remove()
            lat.grid_remove()
            pg_grav.mostrar(row=3, column=1, columnspan=2, sticky="n")
        pintar_gravacao()
    aba_modo = ctk.CTkSegmentedButton(barra_modo, values=[_("📷  Câmera"), _("🖥  Gravar tela")], variable=var_pagina,
                                      command=trocar_pagina, height=38, corner_radius=12,
                                      font=ctk.CTkFont(F, 14, "bold"), fg_color=CARD, selected_color=ACENTO,
                                      selected_hover_color=ACENTO_HOVER, unselected_color=CARD,
                                      unselected_hover_color=CARD_2, text_color=TEXTO)
    aba_modo.pack(side="left")
    dica_pagina = ctk.CTkLabel(barra_modo, text="", font=f_peq, text_color=SUAVE)
    dica_pagina.pack(side="left", padx=(14, 0))

    def atualizar_dica_modo(*_a):
        dica_pagina.configure(text=_("Efeitos para Meet, Zoom, Teams e OBS") if pagina[0] == "camera"
                            else _("Grava a tela com a sua webcam, o microfone e o som do PC"))
    var_pagina.trace_add("write", atualizar_dica_modo)
    atualizar_dica_modo()
    pg_grav = PG.PaginaGravacao(root, root, cfg, motor, grav,
                                dict(CARD=CARD, CARD_2=CARD_2, BORDA=BORDA, TEXTO=TEXTO, SUAVE=SUAVE, ACENTO=ACENTO,
                                     ACENTO_HOVER=ACENTO_HOVER),
                                dict(normal=f_normal, peq=f_peq, secao=f_secao), mudou,
                                lambda cat="geral": abrir_config(cat), toast, PREV_W, PREV_H, LATERAL_W)
    # depois de gravar, mostra a pagina com o video novo na lista
    grav.ao_terminar.append(lambda _a: trocar_pagina(nome="gravar"))
    root.bind("<<IrGravar>>", lambda _e: trocar_pagina(nome="gravar"))
    root.bind("<<IrCamera>>", lambda _e: trocar_pagina(nome="camera"))
    pintar_gravacao()

    def alternar_efeito():
        modo = motor.alternar_efeito()
        var_modo.set(dict(MODOS)[modo])
        atualizar_botao_modo()
        mudou()
        toast(_("Efeito desligado") if modo == "nenhum" else _("Efeito: {nome}").format(nome=dict(MODOS)[modo]))

    def recriar_atalhos():
        """(Re)registra os atalhos globais; devolve os que outro app ja usa."""
        for a in atalhos.values():
            a.parar()
        atalhos.clear()
        falhas = []
        for chave_cfg, acao in (("atalho_privacidade", alternar_privacidade), ("atalho_efeito", alternar_efeito),
                                ("atalho_gravar", grav.alternar), ("atalho_pausar", grav.pausar),
                                ("atalho_parar", grav.parar)):
            combo = cfg[chave_cfg]
            if combo == A.DESATIVADO:
                continue
            a = A.AtalhoGlobal(lambda f=acao: root.after(0, f), combo)
            atalhos[chave_cfg] = a
            if not a.ok:
                falhas.append(combo)
        if falhas:
            motor.avisar("atalho_ocupado", atalho=", ".join(falhas))
        else:
            motor.resolver("atalho_ocupado")
        p = cfg["atalho_privacidade"]
        rotulo_atalho.configure(text=(_("Atalho: {atalho} (funciona com o Meet aberto)").format(atalho=p) if p != A.DESATIVADO
                                      else _("Atalho desativado (veja Configurações › Atalhos)")))
        return falhas
    recriar_atalhos()

    # ================= janela redimensionavel: a previa acompanha
    # A lateral tem largura fixa; ao maximizar/aumentar a janela, so a previa
    # cresce (sempre 16:9). O tamanho inicial e o minimo.
    pendente = [None]

    def ajustar_previa():
        pendente[0] = None
        root.update_idletasks()
        # espaco que sobra para a previa = janela - tudo que nao e previa
        livre_w = root.winfo_width() - (lat.winfo_reqwidth() + base_w)
        livre_h = root.winfo_height() - base_h
        w = int(min(livre_w, livre_h * 16 / 9))
        w = max(w, min_w)
        h = int(w * 9 / 16)
        if (w, h) != (caixa.winfo_width(), caixa.winfo_height()):
            caixa.configure(width=w, height=h)
            ca_texto.configure(wraplength=max(300, int(w * 0.95) - 270))

    def ao_redimensionar(ev):
        if ev.widget is root and pendente[0] is None:
            pendente[0] = root.after(80, ajustar_previa)

    def preparar_redimensionamento():
        nonlocal base_w, base_h, min_w
        root.update_idletasks()
        min_w = caixa.winfo_width()
        # medidas de tudo que esta em volta da previa (margens, cabecalho, cartoes)
        base_w = root.winfo_width() - lat.winfo_reqwidth() - caixa.winfo_width()
        base_h = root.winfo_height() - caixa.winfo_height()
        root.minsize(root.winfo_width(), root.winfo_height())
        # tamanho explicito: sem isso o Tk "segue" a previa ampliada e, ao sair
        # do maximizado, a janela nao volta ao tamanho original
        tk.Tk.wm_geometry(root, f"{root.winfo_width()}x{root.winfo_height()}")
        root.resizable(True, True)
        root.bind("<Configure>", ao_redimensionar)

    base_w = base_h = min_w = 0
    preparado = [False]

    def preparar_quando_visivel():
        # o layout so pode ser medido com a janela na tela (escondida mede 0)
        if not preparado[0] and root.state() in ("normal", "zoomed"):
            preparado[0] = True
            preparar_redimensionamento()
    if not na_bandeja:
        root.after(300, preparar_quando_visivel)

    # ================= lacos de atualizacao
    foto = [None]

    def atualizar_previa():
        if root.state() not in ("normal", "zoomed") or pagina[0] != "camera":   # escondida: nao gasta CPU
            root.after(200, atualizar_previa)
            return
        img = motor.alpha if var_mask.get() else motor.saida
        if motor.sem_webcam:
            previa.configure(image="", text=_("Aguardando a webcam…"), fg=SUAVE, font=(F, 12))
        elif motor.em_espera:
            previa.configure(image="", text=_("Webcam em espera…"), fg=SUAVE, font=(F, 12))
        elif var_prev.get() and img is not None:
            lw, lh = max(caixa.winfo_width(), 50), max(caixa.winfo_height(), 50)
            h, w = img.shape[:2]
            s = min(lw / w, lh / h)
            tam = (max(1, int(w * s)), max(1, int(h * s)))
            if var_mask.get():
                img = cv2.convertScaleAbs(img, alpha=255.0)
            img = cv2.resize(img, tam, interpolation=cv2.INTER_AREA)
            foto[0] = ImageTk.PhotoImage(Image.fromarray(img))
            previa.configure(image=foto[0], text="")
        elif not var_prev.get():
            previa.configure(image="", text=_("Prévia desligada"), fg=SUAVE, font=(F, 12))
        root.after(33, atualizar_previa)

    def atualizar_status():
        # a previa so conta como "vista" com a janela aberta (nao minimizada/na bandeja)
        motor.janela_visivel = root.state() in ("normal", "zoomed")
        if motor.sem_webcam:
            pilula.configure(text=_("  ◌  sem webcam · tentando de novo  "), text_color="#FFC857")
        elif motor.em_espera:
            pilula.configure(text=_("  ◌  em espera · webcam desligada  "), text_color=SUAVE)
        else:
            pilula.configure(text=_("  ●  {fps} fps   ·   {ia}   ·   IA {ms} ms  ").format(
                fps=f"{motor.fps:4.1f}", ia=motor.dispositivo, ms=f"{motor.ms_ia:.0f}"),
                             text_color=VERDE if motor.fps >= 24 else ROSA)
        mostrar_problemas()
        if grav.gravando:
            pintar_gravacao()
        if motor.nome_camera and var_cam.get() != motor.nome_camera:
            var_cam.set(motor.nome_camera)      # webcam (re)aberta pelo modo espera
        if bandeja is not None:
            bandeja.atualizar()
        root.after(500, atualizar_status)

    def mostrar():
        root.deiconify()
        root.state("normal")
        root.lift()
        root.focus_force()
        motor.janela_visivel = True
        root.after(300, preparar_quando_visivel)

    def esconder():
        root.withdraw()
        motor.janela_visivel = False
        if bandeja is not None and not cfg["aviso_bandeja_mostrado"]:
            bandeja.avisar(_("O OpenBokeh continua rodando aqui na bandeja. "
                           "Clique no ícone para abrir; botão direito › Sair para fechar."))
            cfg["aviso_bandeja_mostrado"] = True
            mudou()

    def sair():
        grav.encerrar()
        for a in atalhos.values():
            a.parar()
        if bandeja is not None:
            bandeja.parar()
        ouvinte.parar()
        M.salvar_config(cfg)
        motor.parar()
        root.destroy()

    def fechar():
        """Botao X: vai para a bandeja (se ativado) ou sai."""
        if bandeja is not None and cfg["fechar_para_bandeja"]:
            esconder()
        else:
            sair()

    bandeja = None
    try:
        import bandeja as B
        bandeja = B.Bandeja(
            icone=os.path.join(assets, "logo_64.png"),
            motor=motor, cfg=cfg,
            mostrar=lambda: root.after(0, mostrar),
            privacidade=lambda: root.after(0, alternar_privacidade),
            aplicar_perfil=lambda nome: root.after(0, lambda: (M.aplicar_perfil(cfg, nome), sincronizar(),
                                                              motor.pedir_reset(), mudou())),
            sair=lambda: root.after(0, sair),
            configuracoes=lambda: root.after(0, lambda: (mostrar(), abrir_config())),
            gravar=lambda: root.after(0, grav.alternar), gravando=lambda: grav.gravando,
            microfone=lambda: root.after(0, lambda: trocar_microfone(not cfg["microfone_limpo"])))
    except Exception as e:
        print(f"[aviso] bandeja indisponivel: {e}")
    ouvinte = SIS.OuvinteMostrar(lambda: root.after(0, mostrar))

    def erro_interface(exc, val, tb):
        import traceback
        print("[erro interface]", "".join(traceback.format_exception(exc, val, tb)), flush=True)
        motor.avisar("inesperado")
    root.report_callback_exception = erro_interface

    # ================= barra de menus
    import json
    import platform
    import ajuda
    import menu_ui
    import versao as V

    pasta_dados = os.path.dirname(os.path.abspath(M.CONFIG_ARQ))

    def abrir_pasta_config():
        os.startfile(pasta_dados)

    def abrir_registro():
        log = os.path.join(pasta_dados, "openbokeh.log")
        os.startfile(log if os.path.exists(log) else pasta_dados)

    def exportar_config():
        arq = filedialog.asksaveasfilename(parent=root, title=_("Exportar configurações"), defaultextension=".json",
                                           initialfile="openbokeh-configuracoes.json",
                                           filetypes=[(_("Configurações do OpenBokeh"), "*.json")])
        if arq:
            try:
                with open(arq, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                toast(_("Configurações exportadas"))
            except OSError as e:
                print(f"[config] exportar: {e}")
                toast(_("Não foi possível salvar nesse local"))

    def importar_config():
        arq = filedialog.askopenfilename(parent=root, title=_("Importar configurações"),
                                         filetypes=[(_("Configurações do OpenBokeh"), "*.json")])
        if not arq:
            return
        try:
            with open(arq, encoding="utf-8") as f:
                dados = json.load(f)
            if not isinstance(dados, dict):
                raise ValueError("formato inesperado")
            validos = {k: v for k, v in dados.items()
                       if k in M.CONFIG_PADRAO and k != "camera" and type(v) is type(M.CONFIG_PADRAO[k])}
            if not validos:
                raise ValueError("nenhuma configuração reconhecida")
            cfg.update(validos)
            M.sanear(cfg)
            sincronizar()
            motor.pedir_reset()
            mudou()
            toast(_("{n} configurações importadas").format(n=len(validos)))
        except (OSError, ValueError) as e:
            print(f"[config] importar: {e}")
            toast(_("Esse arquivo não é uma configuração válida do OpenBokeh"))

    var_topo = ctk.BooleanVar(value=False)

    def nome_placa_video():
        try:
            import ctypes
            from ctypes import wintypes

            class DISPLAY_DEVICEW(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                            ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                            ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]
            d = DISPLAY_DEVICEW()
            d.cb = ctypes.sizeof(d)
            nomes = []
            i = 0
            while ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
                if d.DeviceString not in nomes:
                    nomes.append(d.DeviceString)
                i += 1
            return ", ".join(nomes) or "desconhecida"
        except Exception:
            return "desconhecida"

    def diagnostico():
        return "\n".join([
            f"{V.NOME} {V.VERSAO}",
            f"Windows: {platform.platform()}",
            f"Placa de vídeo: {nome_placa_video()}",
            f"IA: {motor.dispositivo} · {motor.ms_ia:.0f} ms · qualidade {cfg['qualidade']}",
            f"Webcam: {motor.nome_camera or '(nenhuma)'} · em espera: {motor.em_espera} · sem webcam: {motor.sem_webcam}",
            f"Câmera virtual: {motor.cam_desc}",
            f"Desempenho: {motor.fps:.1f} fps",
            f"Efeito: {cfg['modo']} · enquadrar: {cfg['enquadrar']} · luz: {cfg['correcao_luz']} · ruído: {cfg['reducao_ruido']}",
            f"Avisos ativos: {', '.join(motor.problemas) or 'nenhum'}",
        ])

    def copiar_diagnostico():
        root.clipboard_clear()
        root.clipboard_append(diagnostico())
        toast(_("Diagnóstico copiado — é só colar na mensagem de suporte"))

    def reconectar_webcam():
        motor.tentar_webcam_agora()
        toast(_("Reconectando a webcam…"))

    menus = [
        (_("Arquivo"), [(_("Configurações…"), lambda: abrir_config(), "Ctrl+,"),
                     (_("Abrir pasta de dados"), abrir_pasta_config), "-",
                     (_("Exportar configurações…"), exportar_config),
                     (_("Importar configurações…"), importar_config), "-",
                     (_("Esconder na bandeja"), esconder),
                     (_("Sair do OpenBokeh"), sair)]),
        (_("Câmera"), [(_("Volto já"), alternar_privacidade,
                     lambda: "" if cfg["atalho_privacidade"] == A.DESATIVADO else cfg["atalho_privacidade"]),
                    (_("Ligar/desligar efeito"), alternar_efeito,
                     lambda: "" if cfg["atalho_efeito"] == A.DESATIVADO else cfg["atalho_efeito"]),
                    (_("Ajustes avançados da webcam…"), lambda: motor.abrir_ajustes_webcam()
                     or toast(_("A webcam precisa estar ligada para abrir os ajustes"))),
                    (_("Reconectar webcam"), reconectar_webcam), "-",
                    (_("Privacidade da câmera no Windows…"), lambda: os.startfile("ms-settings:privacy-webcam"))]),
        (_("Gravação"), [(_("Ir para Gravar tela"), lambda: trocar_pagina(nome="gravar")),
                      (_("Iniciar/parar gravação"), lambda: grav.alternar(),
                       lambda: "" if cfg["atalho_gravar"] == A.DESATIVADO else cfg["atalho_gravar"]),
                      (_("Pausar/retomar"), lambda: grav.pausar(),
                       lambda: "" if cfg["atalho_pausar"] == A.DESATIVADO else cfg["atalho_pausar"]),
                      (_("Parar gravação"), lambda: grav.parar(),
                       lambda: "" if cfg["atalho_parar"] == A.DESATIVADO else cfg["atalho_parar"]), "-",
                      (_("Abrir pasta de gravações"), lambda: grav.abrir_pasta()),
                      (_("Opções de gravação…"), lambda: abrir_config("gravacao"))]),
        (_("Exibir"), [(_("Mostrar prévia"), None, None, var_prev),
                    (_("Ver recorte (preto e branco)"), None, None, var_mask),
                    (_("Sempre no topo"), lambda: root.attributes("-topmost", var_topo.get()), None, var_topo)]),
        (_("Ajuda"), [(_("Primeiros passos"), lambda: ajuda.primeiros_passos(root)),
                   (_("Solução de problemas"), lambda: ajuda.solucao_problemas(root, abrir_registro, copiar_diagnostico)),
                   (_("Copiar diagnóstico"), copiar_diagnostico),
                   (_("Abrir registro de erros"), abrir_registro), "-",
                   (_("Sobre o OpenBokeh"), abrir_sobre)]),
    ]
    def restaurar_tudo():
        manter = {k: cfg[k] for k in ("perfis", "camera", "boas_vindas_vistas", "aviso_bandeja_mostrado")}
        res_antes = (cfg["largura"], cfg["altura"])
        import copy
        cfg.update(copy.deepcopy(M.CONFIG_PADRAO))
        cfg.update(manter)
        motor.definir_saida(cfg["saida"])
        if (cfg["largura"], cfg["altura"]) != res_antes:
            motor.reabrir_webcam()
        recriar_atalhos()
        sincronizar()
        motor.pedir_reset()
        mudou()
        toast(_("Configurações restauradas (seus perfis foram mantidos)"))

    def reiniciar():
        import subprocess
        M.salvar_config(cfg)
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(sys.argv[0])]
        subprocess.Popen(args + ["--aguardar-pid", str(os.getpid())], close_fds=True)
        sair()

    def abrir_config(categoria="geral"):
        import configuracoes
        configuracoes.abrir(root, motor, cfg, dict(
            cores=dict(BG=BG, CARD=CARD, CARD_2=CARD_2, BORDA=BORDA, TEXTO=TEXTO, SUAVE=SUAVE,
                       ACENTO=ACENTO, ACENTO_HOVER=ACENTO_HOVER, ERRO=ERRO),
            assets=assets, mudou=mudou, sincronizar=sincronizar, toast=toast,
            recriar_atalhos=recriar_atalhos, trocar_camera=lambda n: (var_cam.set(n), trocar_camera(n)),
            reiniciar=reiniciar, primeiros_passos=lambda: ajuda.primeiros_passos(root), sobre=abrir_sobre,
            exportar=exportar_config, importar=importar_config, abrir_registro=abrir_registro,
            copiar_diagnostico=copiar_diagnostico, restaurar_tudo=restaurar_tudo,
            alternar_privacidade=alternar_privacidade, trocar_microfone=trocar_microfone, grav=grav,
            cameras=lambda: [n for n in M.listar_cameras() if not M.eh_virtual(n)]), categoria)
    root.bind_all("<Control-comma>", lambda _e: abrir_config())

    barra = menu_ui.BarraMenu(root, menus, dict(CARD=CARD, CARD_2=CARD_2, BORDA=BORDA, TEXTO=TEXTO,
                                                SUAVE=SUAVE, ACENTO=ACENTO), f_normal)
    barra.grid(row=0, column=1, columnspan=2, sticky="w", padx=14, pady=(6, 0))

    # primeira vez: primeiros passos
    if not cfg["boas_vindas_vistas"] and not na_bandeja:
        def boas_vindas_vistas():
            cfg["boas_vindas_vistas"] = True
            mudou()
        root.after(900, lambda: ajuda.primeiros_passos(root, ao_fechar=boas_vindas_vistas))

    root.protocol("WM_DELETE_WINDOW", fechar)
    if na_bandeja and bandeja is not None:
        root.after(10, lambda: (root.withdraw(), setattr(motor, "janela_visivel", False)))
    atualizar_previa()
    atualizar_status()
    root.mainloop()


# ---------------------------------------------------------------- instancia unica
_mutex_instancia = None


def instancia_unica():
    """True se esta e a unica janela do OpenBokeh; senao foca a existente."""
    global _mutex_instancia
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.windll.user32
        k32.CreateMutexW.restype = ctypes.c_void_p
        _mutex_instancia = k32.CreateMutexW(None, False, "Local\\OpenBokeh.InstanciaUnica")
        if ctypes.get_last_error() != 183:     # ERROR_ALREADY_EXISTS
            return True
        import sistema
        if sistema.pedir_para_mostrar():       # a outra janela pode estar escondida na bandeja
            return False
        h = u32.FindWindowW(None, NOME)
        if h:
            u32.ShowWindow(h, 9)               # SW_RESTORE (se estava minimizada)
            u32.SetForegroundWindow(h)
        return False
    except Exception:
        return True


# ---------------------------------------------------------------- main
def main():
    if sys.stdout is None:
        # app instalado (sem console): mensagens vao para um log em %APPDATA%
        arq_log = os.path.join(os.path.dirname(M.CONFIG_ARQ), "openbokeh.log")
        try:        # guarda o registro da vez anterior (se o app fechou com erro, ele nao se perde)
            if os.path.exists(arq_log):
                os.replace(arq_log, os.path.join(os.path.dirname(arq_log), "openbokeh-anterior.log"))
        except OSError:
            pass
        log = open(arq_log, "w", encoding="utf-8")
        sys.stdout = sys.stderr = log
    sys.stdout.reconfigure(line_buffering=True)
    import versao as V
    print(f"{V.NOME} {V.VERSAO} iniciado em {time.strftime('%Y-%m-%d %H:%M:%S')}")

    def excecao_nao_tratada(exc, val, tb):
        import traceback
        print("[erro fatal]", "".join(traceback.format_exception(exc, val, tb)), flush=True)
    sys.excepthook = excecao_nao_tratada
    ap = argparse.ArgumentParser(description=_("OpenBokeh - fundo desfocado com IA"))
    ap.add_argument("--camera", help=_("nome ou índice da webcam"))
    ap.add_argument("--cpu", action="store_true", help=_("forçar IA na CPU"))
    ap.add_argument("--sem-janela", action="store_true", help=_("rodar sem interface"))
    ap.add_argument("--bandeja", action="store_true", help=_("abrir escondido na bandeja (início com o Windows)"))
    ap.add_argument("--aguardar-pid", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--listar", action="store_true", help=_("listar câmeras e sair"))
    ap.add_argument("--benchmark", type=int, metavar="N", help=_("mede N quadros e sai"))
    args = ap.parse_args()

    if args.listar:
        for i, n in enumerate(M.listar_cameras()):
            print(f"[{i}] {n}")
        return

    # uma instancia so: a segunda nao conseguiria abrir a webcam; em vez de
    # mostrar erro, traz a janela que ja esta aberta para a frente
    if args.aguardar_pid:                    # "Reiniciar agora": espera a instancia antiga fechar
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, args.aguardar_pid)   # SYNCHRONIZE
            if h:
                ctypes.windll.kernel32.WaitForSingleObject(h, 15000)
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            pass
    if not args.benchmark and not args.sem_janela and not instancia_unica():
        return

    cfg = M.carregar_config()
    if args.camera is not None:
        cfg["camera"] = args.camera

    try:
        motor = M.Motor(cfg, forcar_cpu=args.cpu or cfg["processador"] == "cpu", camera_virtual=not args.benchmark)
    except Exception as e:
        import traceback
        print("[erro fatal] IA:", "".join(traceback.format_exception(e)))
        if not args.sem_janela and not args.benchmark:
            import ajuda
            ajuda.erro_fatal(_("Não foi possível iniciar a IA"),
                             "O OpenBokeh não conseguiu carregar o modelo de inteligência artificial. "
                             "Reinstalar o OpenBokeh costuma resolver. Se continuar, envie o arquivo de "
                             "registro (openbokeh.log) da pasta abaixo para o suporte.",
                             os.path.dirname(M.CONFIG_ARQ))
        sys.exit(1)
    motor.dispositivo = motor.ia.dispositivo
    if not args.benchmark:
        try:
            import microfone
            motor.microfone = microfone.criar(cfg)
        except Exception as e:
            print(f"[aviso] microfone sem ruido indisponivel: {e}")
    try:
        motor.iniciar(em_espera=args.bandeja and cfg["espera_automatica"])
    except Exception as e:
        print(f"[erro] {e}")
        if not args.sem_janela and not args.benchmark:
            import ajuda
            ajuda.erro_fatal(_("Não foi possível iniciar o OpenBokeh"),
                             "Algo impediu o OpenBokeh de começar. Tente abrir de novo; se continuar, "
                             "reinicie o computador ou envie o arquivo de registro (openbokeh.log) da "
                             "pasta abaixo para o suporte.", os.path.dirname(M.CONFIG_ARQ))
        sys.exit(1)
    if motor.cap:
        print(f"Webcam: {motor.nome_camera} ({motor.cap.largura}x{motor.cap.altura} @ {motor.cap.fps:.0f})")
    elif motor.sem_webcam:
        print("Webcam: indisponivel agora (o app avisa o motivo e tenta de novo sozinho)")
    else:
        print("Webcam: em espera (liga quando algum app usar a OpenBokeh Camera)")
    print(f"IA: {motor.dispositivo} | Camera virtual: {motor.cam_desc}")
    if motor.microfone is not None and cfg["microfone_limpo"]:
        print("Microfone sem ruido: " + (motor.microfone.erro or "ligado"))

    if args.benchmark:
        while getattr(motor, "num_saida", 0) < 30:          # aquecimento
            time.sleep(0.05)
        n0, t0 = motor.num_saida, time.perf_counter()
        while motor.num_saida - n0 < args.benchmark:
            time.sleep(0.05)
        dt = time.perf_counter() - t0
        print(f"{motor.num_saida - n0} quadros | {(motor.num_saida - n0) / dt:.1f} fps | IA {motor.ms_ia:.1f} ms")
        # imencode + tofile: o cv2.imwrite falha em pastas com acento (ex.: usuario "João")
        cv2.imencode(".jpg", cv2.cvtColor(motor.saida, cv2.COLOR_RGB2BGR))[1].tofile(os.path.join(M.PASTA, "teste_saida.jpg"))
        cv2.imencode(".png", cv2.convertScaleAbs(motor.alpha, alpha=255))[1].tofile(os.path.join(M.PASTA, "teste_alpha.png"))
        motor.parar()
        return

    if args.sem_janela:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        M.salvar_config(cfg)
        motor.parar()
        return

    rodar_janela(motor, cfg, na_bandeja=args.bandeja)


if __name__ == "__main__":
    main()
