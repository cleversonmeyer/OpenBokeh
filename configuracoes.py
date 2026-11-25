"""
Janela de Configuracoes do OpenBokeh: categorias a esquerda, ajustes a direita.
Tudo se aplica na hora e e salvo automaticamente.

`ctx` traz o que a janela principal oferece: mudou(), sincronizar(), toast(),
recriar_atalhos(), trocar_camera(nome), reiniciar(), primeiros_passos(), trocar_microfone(v),
sobre(), exportar(), importar(), abrir_registro(), restaurar_tudo(), cameras().
"""

import os
import sys

import customtkinter as ctk

import atalho as A
import motor as M
import sistema as SIS
from i18n import _

F = "Segoe UI"
CATEGORIAS = [("geral", "⚙", _("Geral")), ("webcam", "◉", "Webcam"), ("virtual", "▣", _("Câmera virtual")),
              ("microfone", "🎙", _("Microfone")), ("gravacao", "⏺", _("Gravação")), ("desempenho", "⚡", _("Desempenho")), ("atalhos", "⌨", _("Atalhos")), ("privacidade", "◐", _("Privacidade")),
              ("dados", "▤", _("Dados"))]


def abrir(root, motor, cfg, ctx, categoria="geral"):
    c = ctx["cores"]
    if getattr(root, "_janela_config", None) is not None and root._janela_config.winfo_exists():
        root._janela_config.focus()
        return
    j = ctk.CTkToplevel(root, fg_color=c["BG"])
    root._janela_config = j
    j.title(_("Configurações do OpenBokeh"))
    j.geometry("860x600")
    j.resizable(False, False)
    j.transient(root)
    j.after(250, lambda: (j.lift(), j.focus_force()))
    ico = os.path.join(ctx["assets"], "icone.ico")
    if os.path.exists(ico):
        j.after(300, lambda: j.iconbitmap(ico))

    f_titulo = ctk.CTkFont(F, 20, "bold")
    f_secao = ctk.CTkFont(F, 13, "bold")
    f_normal = ctk.CTkFont(F, 13)
    f_peq = ctk.CTkFont(F, 11)

    # ---------------- navegacao
    nav = ctk.CTkFrame(j, fg_color=c["CARD"], corner_radius=0, width=210)
    nav.pack(side="left", fill="y")
    nav.pack_propagate(False)
    ctk.CTkLabel(nav, text=_("Configurações"), font=ctk.CTkFont(F, 17, "bold"), text_color=c["TEXTO"],
                 anchor="w").pack(fill="x", padx=18, pady=(20, 14))
    botoes_nav = {}

    area = ctk.CTkFrame(j, fg_color="transparent")
    area.pack(side="left", fill="both", expand=True)
    titulo_pagina = ctk.CTkLabel(area, text="", font=f_titulo, text_color=c["TEXTO"], anchor="w")
    titulo_pagina.pack(fill="x", padx=28, pady=(20, 6))
    conteudo = ctk.CTkScrollableFrame(area, fg_color="transparent", scrollbar_button_color=c["BORDA"])
    conteudo.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # ---------------- componentes
    def cartao(titulo=None, descricao=None):
        k = ctk.CTkFrame(conteudo, fg_color=c["CARD"], corner_radius=12, border_width=1, border_color=c["BORDA"])
        k.pack(fill="x", padx=8, pady=6)
        corpo = ctk.CTkFrame(k, fg_color="transparent")
        corpo.pack(fill="x", padx=16, pady=12)
        if titulo:
            ctk.CTkLabel(corpo, text=titulo, font=f_secao, text_color=c["TEXTO"], anchor="w").pack(fill="x")
        if descricao:
            ctk.CTkLabel(corpo, text=descricao, font=f_peq, text_color=c["SUAVE"], anchor="w", justify="left",
                         wraplength=520).pack(fill="x", pady=(2, 4))
        return corpo

    def linha(pai, texto, dica=None):
        """Texto (e dica) a esquerda; devolve o espaco da direita para o controle."""
        l = ctk.CTkFrame(pai, fg_color="transparent")
        l.pack(fill="x", pady=5)
        l.grid_columnconfigure(0, weight=1)
        t = ctk.CTkFrame(l, fg_color="transparent")
        t.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(t, text=texto, font=f_normal, text_color=c["TEXTO"], anchor="w").pack(anchor="w")
        if dica:
            ctk.CTkLabel(t, text=dica, font=f_peq, text_color=c["SUAVE"], anchor="w", justify="left",
                         wraplength=380).pack(anchor="w")
        d = ctk.CTkFrame(l, fg_color="transparent")
        d.grid(row=0, column=1, sticky="e", padx=(12, 0))
        return d

    def chave(pai, texto, dica, valor, ao_mudar, ativo=True):
        var = ctk.BooleanVar(value=valor)
        sw = ctk.CTkSwitch(linha(pai, texto, dica), text="", variable=var, width=46, switch_width=44,
                           switch_height=22, progress_color=c["ACENTO"], button_color="#FFFFFF",
                           button_hover_color="#E6E0FF", fg_color=c["BORDA"],
                           command=lambda: ao_mudar(var.get()))
        sw.pack()
        if not ativo:
            sw.configure(state="disabled")
        return var

    def segmentos(pai, texto, dica, opcoes, atual, ao_mudar):
        rot = dict(opcoes)
        inv = {v: k for k, v in opcoes}
        var = ctk.StringVar(value=rot.get(atual, opcoes[0][1]))
        ctk.CTkSegmentedButton(linha(pai, texto, dica), values=[r for _c, r in opcoes], variable=var,
                               command=lambda r: ao_mudar(inv[r]), height=30, corner_radius=8, font=f_peq,
                               fg_color=c["CARD_2"], selected_color=c["ACENTO"], selected_hover_color=c["ACENTO_HOVER"],
                               unselected_color=c["CARD_2"], unselected_hover_color=c["BORDA"],
                               text_color=c["TEXTO"]).pack()
        return var

    def lista(pai, texto, dica, valores, atual, ao_mudar, largura=190):
        var = ctk.StringVar(value=atual)
        ctk.CTkOptionMenu(linha(pai, texto, dica), values=valores, variable=var, command=ao_mudar, width=largura,
                          height=32, corner_radius=8, font=f_normal, dropdown_font=f_normal, fg_color=c["CARD_2"],
                          button_color=c["BORDA"], button_hover_color=c["ACENTO"], dropdown_fg_color=c["CARD_2"],
                          dropdown_hover_color=c["ACENTO"], text_color=c["TEXTO"]).pack()
        return var

    def botao(pai, texto, comando, principal=False, perigo=False, lado="left"):
        cor = c["ACENTO"] if principal else ("#3A1424" if perigo else c["CARD_2"])
        b = ctk.CTkButton(pai, text=texto, command=comando, height=34, corner_radius=8, font=f_normal,
                          fg_color=cor, hover_color=c["ACENTO_HOVER"] if principal else c["BORDA"],
                          text_color="#FFFFFF" if principal else (c["ERRO"] if perigo else c["TEXTO"]),
                          border_width=1, border_color=c["ACENTO"] if principal else (c["ERRO"] if perigo else c["BORDA"]))
        b.pack(side=lado, padx=(0, 8), pady=(6, 0))
        return b

    def salvar(chave_cfg, valor, depois=None):
        cfg[chave_cfg] = valor
        ctx["mudou"]()
        if depois:
            depois()

    # ---------------- paginas
    def pagina_geral():
        k = cartao(_("Inicialização"))
        chave(k, _("Iniciar com o Windows"),
              _("Abre escondido na bandeja, com a webcam em espera até algum app usar a câmera.")
              if SIS.instalado() else _("Disponível na versão instalada."),
              SIS.inicio_automatico_ativo(),
              lambda v: (SIS.definir_inicio_automatico(v), ctx["toast"](_("Início automático ligado") if v else _("Início automático desligado"))),
              ativo=SIS.instalado())
        chave(k, _("Fechar (X) mantém na bandeja"), _("O OpenBokeh continua funcionando ao lado do relógio."),
              cfg["fechar_para_bandeja"], lambda v: salvar("fechar_para_bandeja", v, ctx["sincronizar"]))
        chave(k, _("Mostrar notificações"), _("Avisos do Windows vindos do ícone da bandeja."),
              cfg["notificacoes"], lambda v: salvar("notificacoes", v))
        import i18n
        k = cartao(_("Idioma"), _("A troca vale ao reiniciar o OpenBokeh."))
        segmentos(k, _("Idioma da interface"), None, [(c, _(n)) for c, n in i18n.IDIOMAS], cfg.get("idioma", "auto"),
                  lambda v: (salvar("idioma", v), ctx["toast"](_("Idioma salvo — reinicie o OpenBokeh para aplicar"))))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Reiniciar agora"), ctx["reiniciar"])
        k = cartao(_("Ajuda"))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Rever primeiros passos"), ctx["primeiros_passos"])
        botao(l, _("Sobre o OpenBokeh"), ctx["sobre"])

    def pagina_webcam():
        k = cartao(_("Webcam de entrada"), _("A câmera real que o OpenBokeh usa. Ela fica reservada para ele enquanto ele está ligado."))
        cams = ctx["cameras"]() or [motor.nome_camera or cfg["camera"] or _("(nenhuma)")]
        lista(k, "Webcam", None, cams, motor.nome_camera or cfg["camera"] or cams[0], ctx["trocar_camera"], 240)

        def trocar_res(nome):
            w, h = M.RESOLUCOES[nome]
            cfg["largura"], cfg["altura"] = w, h
            ctx["mudou"]()
            motor.reabrir_webcam()
            ctx["toast"](_("Captura em {nome}").format(nome=nome))
        atual = "1080p" if cfg["altura"] >= 1080 else "720p"
        segmentos(k, _("Resolução de captura"), _("1080p fica mais nítido, mas exige mais do computador."),
                  [("720p", "HD 720p"), ("1080p", "Full HD 1080p")], atual, trocar_res)
        chave(k, _("Espelhar imagem"), _("Normalmente desligado: os apps de chamada já espelham a sua prévia."),
              cfg["espelhar"], lambda v: salvar("espelhar", v, lambda: (motor.pedir_reset(), ctx["sincronizar"]())))

        k = cartao(_("Ajustes da própria webcam"),
                   _("Exposição, foco, balanço de branco, brilho e contraste — controles do driver da câmera."))

        def ajustes():
            if not motor.abrir_ajustes_webcam():
                ctx["toast"](_("A webcam precisa estar ligada para abrir os ajustes"))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Abrir ajustes avançados da webcam…"), ajustes)

        k = cartao(_("Economia de energia"))
        chave(k, _("Desligar a webcam quando nenhum app usar"),
              _("Com a janela escondida e nenhum app usando a OpenBokeh Camera, a luz da webcam apaga."),
              cfg["espera_automatica"], lambda v: salvar("espera_automatica", v, ctx["sincronizar"]))
        segmentos(k, _("Desligar depois de"), None, [(5, "5 s"), (30, "30 s"), (120, "2 min")],
                  cfg["espera_segundos"], lambda v: salvar("espera_segundos", v))

    def pagina_virtual():
        import camera_propria as CP
        k = cartao("OpenBokeh Camera",
                   _("É a câmera que você escolhe no Meet, Zoom, Teams, Discord ou OBS para receber a imagem com efeito."))
        for nome, ok, dica in (
                (_("Clássica (Chrome, Edge, Zoom, Discord, OBS)"), CP.instalada(), _("64 e 32 bits")),
                (_("Windows 11 (app Câmera, Microsoft Store, novo Teams)"), CP.instalada_mf(),
                 _("aparece como “OpenBokeh Camera (Câmera Virtual do Windows)”"))):
            ctk.CTkLabel(k, text=f"{'●' if ok else '○'}  {nome}: {_('instalada') if ok else _('não instalada')}",
                         font=f_normal, text_color="#3DDC97" if ok else c["SUAVE"], anchor="w").pack(fill="x")
            ctk.CTkLabel(k, text="      " + dica, font=f_peq, text_color=c["SUAVE"], anchor="w").pack(fill="x", pady=(0, 4))
        segmentos(k, _("Resolução enviada aos apps"), _("Full HD deixa a imagem mais nítida nos apps que aceitam 1080p."),
                  [("720p", "HD 720p"), ("1080p", "Full HD 1080p")], cfg["saida"],
                  lambda v: (motor.definir_saida(v), ctx["mudou"](), ctx["toast"](_("Câmera virtual em {res}").format(res=v))))

        k = cartao(_("Reparar câmera virtual"),
                   _("Se a OpenBokeh Camera sumiu da lista dos apps, registre-a de novo. O Windows vai pedir permissão "
                   "de administrador."))

        def reparar():
            pasta = os.path.join(os.path.dirname(sys.executable), "camera")
            dll64 = os.path.join(pasta, "OpenBokehCamera64.dll")
            dll32 = os.path.join(pasta, "OpenBokehCamera32.dll")
            if not SIS.instalado() or not os.path.exists(dll64):
                ctx["toast"](_("Disponível só na versão instalada"))
                return
            windir = os.environ.get("WINDIR", r"C:\Windows")
            cmd = f'/c ""{windir}\\System32\\regsvr32.exe" /s "{dll64}"'
            if os.path.exists(dll32):
                cmd += f' & "{windir}\\SysWOW64\\regsvr32.exe" /s "{dll32}"'
            dllmf = os.path.join(pasta, "OpenBokehMF.dll")
            if os.path.exists(dllmf):
                cmd += (f' & "{windir}\\System32\\regsvr32.exe" /s "{dllmf}"'
                        f' & "{windir}\\System32\\rundll32.exe" "{dllmf}",Instalar')
            cmd += '"'
            import ctypes
            # um unico pedido de administrador para as duas cameras (64 e 32 bits)
            r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", cmd, None, 0)
            ctx["toast"](_("Câmera virtual registrada de novo — reabra o app de chamada") if r > 32
                         else _("Reparo cancelado"))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Reparar câmera virtual"), reparar)

    def pagina_microfone():
        import microfone as MIC
        mic = motor.microfone
        if mic is None:
            cartao(_("Microfone sem ruído"), _("Indisponível nesta instalação (faltam os componentes de áudio). "
                                             "Reinstalar o OpenBokeh resolve."))
            return
        try:
            mics, cabo = MIC.dispositivos()
        except Exception:
            mics, cabo = [], None

        k = cartao(_("Microfone sem ruído"),
                   _("Tira o ruído de fundo (ventilador, teclado, rua, ar-condicionado) com uma IA leve, no seu "
                     "computador. O som limpo vai para o cabo de áudio virtual: no Meet, Zoom, Teams, Discord ou "
                     "OBS, escolha “CABLE Output” como microfone."))
        var_lig = chave(k, _("Ligar microfone sem ruído"), None, cfg["microfone_limpo"],
                        lambda v: (ctx["trocar_microfone"](v), atualizar_estado()))
        padrao = _("Padrão do Windows")
        lista(k, _("Microfone"), _("O microfone de verdade que será limpo."), [padrao] + mics,
              cfg["microfone_entrada"] if cfg["microfone_entrada"] in mics else padrao,
              lambda v: (salvar("microfone_entrada", "" if v == padrao else v), MIC.aplicar(mic, cfg),
                         atualizar_estado()), 260)
        segmentos(k, _("Intensidade"), _("Máxima tira mais ruído; mais baixa deixa a voz mais natural."),
                  [(50, _("Suave")), (75, _("Média")), (100, _("Máxima"))], cfg["microfone_intensidade"],
                  lambda v: (salvar("microfone_intensidade", v), MIC.aplicar(mic, cfg)))
        estado = ctk.CTkLabel(k, text="", font=f_peq, anchor="w", justify="left", wraplength=520)
        estado.pack(fill="x", pady=(8, 2))
        medidores = ctk.CTkFrame(k, fg_color="transparent")
        medidores.pack(fill="x")
        barras = {}
        for i, (chave_n, rot) in enumerate((("nivel_entrada", _("Microfone")), ("nivel_saida", _("Sem ruído")))):
            ctk.CTkLabel(medidores, text=rot, font=f_peq, text_color=c["SUAVE"], width=80, anchor="w"
                         ).grid(row=i, column=0, sticky="w")
            b = ctk.CTkProgressBar(medidores, height=8, progress_color=c["ACENTO"], fg_color=c["BORDA"], width=420)
            b.grid(row=i, column=1, sticky="w", pady=3)
            b.set(0)
            barras[chave_n] = b

        def atualizar_estado():
            if not estado.winfo_exists():
                return
            if not cfg["microfone_limpo"]:
                txt, cor = _("Desligado."), c["SUAVE"]
            elif mic.erro:
                txt, cor = mic.erro, c["ERRO"]
            elif mic.rodando:
                txt, cor = _("Funcionando: escolha “CABLE Output” como microfone no app de chamada."), "#3DDC97"
            else:
                txt, cor = _("Iniciando…"), c["SUAVE"]
            estado.configure(text=txt, text_color=cor)
            var_lig.set(cfg["microfone_limpo"])

        def medir():
            if not estado.winfo_exists():
                return
            for chave_n, b in barras.items():
                v = getattr(mic, chave_n, 0.0)
                b.set(min(1.0, (max(v, 1e-4) ** 0.5)))      # raiz: fala normal ja enche bem a barra
            atualizar_estado()
            j.after(80, medir)
        medir()

        k = cartao(_("Cabo de áudio virtual (VB-CABLE)"),
                   _("O Windows só deixa criar um microfone novo com um driver próprio. Por isso o OpenBokeh usa o "
                     "VB-CABLE, gratuito, da VB-Audio, instalado uma vez. Ele cria o “CABLE Output”."))
        ok = cabo is not None
        ctk.CTkLabel(k, text=("●  " + _("Instalado")) if ok else ("○  " + _("Não instalado")), font=f_normal,
                     text_color="#3DDC97" if ok else c["ERRO"], anchor="w").pack(fill="x", pady=(2, 4))
        if not ok:
            ctk.CTkLabel(k, text=_("1. Baixe o pacote no site oficial e extraia o arquivo .zip.\n"
                                   "2. Clique com o botão direito em “VBCABLE_Setup_x64.exe” › Executar como "
                                   "administrador › Install Driver.\n"
                                   "3. Reinicie o computador e ligue o microfone sem ruído aqui."),
                         font=f_peq, text_color=c["TEXTO"], anchor="w", justify="left", wraplength=520
                         ).pack(fill="x", pady=(0, 4))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Abrir site do VB-CABLE"), lambda: __import__("webbrowser").open(MIC.URL_CABO), principal=not ok)
        botao(l, _("Procurar de novo"), lambda: mostrar("microfone"))

        k = cartao(_("Testar"), _("Grava 4 segundos e toca nos seus fones: primeiro como está, depois sem ruído. "
                                  "Funciona mesmo sem o cabo instalado. Use fones para não dar eco."))
        aviso = ctk.CTkLabel(k, text="", font=f_peq, text_color=c["SUAVE"], anchor="w")
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")

        def testar():
            etapas = {"gravando": _("● Gravando… fale e faça barulho perto do microfone"),
                      "original": _("▶ Tocando: como está"), "limpo": _("▶ Tocando: sem ruído")}
            bt.configure(state="disabled")
            MIC.testar(cfg["microfone_entrada"],
                       ao_mudar=lambda e: j.after(0, lambda: aviso.winfo_exists() and aviso.configure(text=etapas[e])),
                       ao_terminar=lambda erro: j.after(0, lambda: aviso.winfo_exists() and (
                           aviso.configure(text=(_("Não foi possível testar: {erro}").format(erro=erro)) if erro
                                           else _("Teste concluído.")), bt.configure(state="normal"))))
        bt = botao(l, _("Gravar e ouvir"), testar, principal=ok)
        aviso.pack(fill="x", pady=(6, 0))

    def pagina_gravacao():
        import gravador as G
        import gravacao_ui as GU
        grav = ctx.get("grav")
        if not G.disponivel():
            cartao(_("Gravação de tela"), _("Indisponível nesta instalação. Reinstalar o OpenBokeh resolve."))
            return

        def mudar(chave_cfg, valor, ao_vivo=False):
            salvar(chave_cfg, valor)
            atualizar_previsao()
            if ao_vivo and grav is not None:
                grav.atualizar_layout()

        k = cartao(_("Gravar a tela"), _("Grava a tela com a sua webcam por cima, o microfone e o som do computador. "
                                        "Atalho: {atalho}. O arquivo MP4 fica na pasta abaixo.").format(
                                            atalho=cfg["atalho_gravar"]))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("● Gravar agora") if not (grav and grav.gravando) else _("■ Parar gravação"),
              lambda: (grav.alternar(), mostrar("gravacao")), principal=True)
        botao(l, _("Abrir pasta de gravações"), lambda: grav.abrir_pasta())

        k = cartao(_("Tela e formato"))
        try:
            mons = G.monitores()
        except Exception:
            mons = []
        nomes = [f"{i + 1}: {m['largura']}×{m['altura']}" + (_(" (principal)") if m["principal"] else "")
                 for i, m in enumerate(mons)] or ["1"]
        atual = nomes[cfg["grav_monitor"]] if cfg["grav_monitor"] < len(nomes) else nomes[0]
        lista(k, _("Monitor"), None, nomes, atual, lambda v: mudar("grav_monitor", nomes.index(v)), 200)
        segmentos(k, _("Formato do vídeo"), _("Ultrawide vira 16:9 1440p, tela em 1:1."),
                  [("auto", _("Automático")), ("nativa", _("Nativo")), ("1440p", "16:9 1440p"), ("1080p", "16:9 1080p")],
                  cfg["grav_saida"], lambda v: mudar("grav_saida", v))
        segmentos(k, _("Encaixe no vídeo"), _("Preencher: sem faixas, corta as bordas. 1:1: tamanho real."),
                  [("inteira", _("Com faixas")), ("preencher", _("Preencher")), ("recorte", "1:1")], cfg["grav_encaixe"],
                  lambda v: mudar("grav_encaixe", v, True))
        segmentos(k, _("Faixas em volta"), None, [("desfocado", _("Tela desfocada")), ("cor", _("Cor escura"))],
                  cfg["grav_fundo"], lambda v: mudar("grav_fundo", v, True))
        chave(k, _("Mostrar o cursor do mouse"), None, cfg["grav_cursor"], lambda v: mudar("grav_cursor", v, True))
        previsao = ctk.CTkLabel(k, text="", font=f_peq, anchor="w", justify="left", wraplength=520)
        previsao.pack(fill="x", pady=(6, 0))

        def atualizar_previsao():
            if previsao.winfo_exists():
                txt, ok = GU.previsao(cfg)
                previsao.configure(text=("✓ " if ok else "⚠ ") + txt, text_color="#3DDC97" if ok else "#FFC857")
        atualizar_previsao()

        k = cartao(_("Qualidade"), _("Todas mantêm o texto nítido. Pesos medidos com texto rolando a 60 fps."))
        segmentos(k, _("Preset"), None,
                  [("edicao", _("Edição (H.264)")), ("alta", _("Alta (HEVC)")), ("compacta", _("Compacta"))],
                  cfg["grav_preset"], lambda v: mudar("grav_preset", v))
        ctk.CTkLabel(k, text=_("Edição {e} · abre leve em qualquer editor\nAlta {a} · padrão, arquivo final\n"
                               "Compacta {c} · guardar e enviar").format(e=GU.PESO_HORA["edicao"], a=GU.PESO_HORA["alta"],
                                                                        c=GU.PESO_HORA["compacta"]),
                     font=f_peq, text_color=c["SUAVE"], anchor="w", justify="left").pack(fill="x", pady=(0, 4))
        segmentos(k, _("Quadros por segundo"), _("60 deixa a rolagem de texto legível."), [(30, "30"), (60, "60")],
                  int(cfg["grav_fps"]), lambda v: mudar("grav_fps", v))

        k = cartao(_("Webcam no vídeo"), _("Usa o efeito atual da câmera (desfoque, retoque, luz)."))
        segmentos(k, _("Formato"), None,
                  [("nenhuma", _("Sem webcam")), ("circulo", _("Círculo")), ("arredondado", _("Retângulo")),
                   ("pessoa", _("Só você"))], cfg["grav_cam_forma"], lambda v: mudar("grav_cam_forma", v, True))
        pos = [("inferior_direito", _("Inferior direito")), ("inferior_esquerdo", _("Inferior esquerdo")),
               ("superior_direito", _("Superior direito")), ("superior_esquerdo", _("Superior esquerdo"))]
        rot = dict(pos)
        inv = {v: k2 for k2, v in pos}
        lista(k, _("Posição"), None, [r for _c, r in pos], rot.get(cfg["grav_cam_posicao"], pos[0][1]),
              lambda v: mudar("grav_cam_posicao", inv[v], True), 200)
        segmentos(k, _("Tamanho"), None, [(20, _("Pequena")), (28, _("Média")), (38, _("Grande"))],
                  cfg["grav_cam_tamanho"], lambda v: mudar("grav_cam_tamanho", v, True))
        segmentos(k, _("Borda branca"), None, [(0, _("Sem")), (4, _("Fina")), (8, _("Grossa"))],
                  cfg["grav_cam_borda"], lambda v: mudar("grav_cam_borda", v, True))

        k = cartao(_("Áudio"))
        chave(k, _("Microfone"), None, cfg["grav_mic"], lambda v: mudar("grav_mic", v))
        import microfone as MIC_
        try:
            mics_g = MIC_.dispositivos(atualizar=False)[0]
        except Exception:
            mics_g = []
        padrao_g = _("Padrão do Windows")
        atual_g = cfg.get("grav_mic_entrada", "")
        lista(k, _("Microfone da gravação"), _("Pode ser outro que o das chamadas (lapela, headset, webcam...)."),
              [padrao_g] + mics_g, atual_g if atual_g in mics_g else padrao_g,
              lambda v: mudar("grav_mic_entrada", "" if v == padrao_g else v), 260)
        chave(k, _("Tirar o ruído do microfone"), _("Não precisa do VB-CABLE para gravar."), cfg["grav_mic_sem_ruido"],
              lambda v: mudar("grav_mic_sem_ruido", v))
        chave(k, _("Som do computador"), _("O que estiver tocando: vídeos, apps, chamadas."), cfg["grav_som_pc"],
              lambda v: mudar("grav_som_pc", v))

        pasta_real, bloqueada = grav.pasta_gravavel() if grav else (G.pasta_padrao(), False)
        k = cartao(_("Arquivos"), _("Pasta: {pasta}").format(pasta=pasta_real))
        if bloqueada:
            ctk.CTkLabel(k, text=_("A pasta escolhida está protegida pelo Windows (Segurança do Windows › Proteção contra "
                                   "ransomware › Acesso controlado a pastas). Para gravar nela, permita o OpenBokeh em "
                                   "“Permitir um aplicativo”. Enquanto isso, os vídeos vão para a pasta acima."),
                         font=f_peq, text_color="#FFC857", anchor="w", justify="left", wraplength=520).pack(fill="x", pady=(0, 4))

        def escolher_pasta():
            from tkinter import filedialog
            d = filedialog.askdirectory(parent=j, title=_("Pasta das gravações"))
            if d:
                salvar("grav_pasta", d)
                mostrar("gravacao")
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Escolher pasta…"), escolher_pasta)
        botao(l, _("Usar a pasta Vídeos"), lambda: (salvar("grav_pasta", ""), mostrar("gravacao")))
        chave(k, _("Esconder o OpenBokeh do vídeo"), _("As janelas do app não aparecem na gravação."),
              cfg["grav_ocultar_app"], lambda v: salvar("grav_ocultar_app", v))
        k = cartao(_("Ao começar"))
        segmentos(k, _("Contagem regressiva"), _("Tempo para você se preparar antes de gravar."),
                  [(0, _("Sem")), (3, "3 s"), (5, "5 s")], cfg["grav_contagem"], lambda v: salvar("grav_contagem", v))
        chave(k, _("Minimizar o OpenBokeh"), _("Fica só uma barrinha com cronômetro, pausar e parar (ela não aparece no vídeo)."),
              cfg["grav_minimizar"], lambda v: salvar("grav_minimizar", v))

    def pagina_desempenho():
        k = cartao(_("Processamento da IA"), _("Em uso agora: {ia}.").format(ia=motor.dispositivo))
        segmentos(k, _("Usar"), _("A troca vale ao reiniciar o OpenBokeh."),
                  [("auto", _("Placa de vídeo (GPU)")), ("cpu", _("Processador (CPU)"))], cfg["processador"],
                  lambda v: salvar("processador", v))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Reiniciar o OpenBokeh agora"), ctx["reiniciar"])

        k = cartao(_("Qualidade e fluidez"))
        segmentos(k, _("Qualidade da IA"), _("Mais alta = recorte mais preciso. “Leve” é para PCs sem placa de vídeo."),
                  [("leve", _("Leve")), ("rapido", _("Rápida")), ("equilibrado", _("Equilibrada")), ("maximo", _("Máxima"))],
                  cfg["qualidade"],
                  lambda v: salvar("qualidade", v, lambda: (motor.pedir_reset(), ctx["sincronizar"]())))
        chave(k, _("Ajustar a qualidade automaticamente"),
              _("Se o computador não acompanhar, a qualidade baixa sozinha para a imagem não travar."),
              cfg["qualidade_automatica"], lambda v: salvar("qualidade_automatica", v))
        segmentos(k, _("Limite de quadros"), _("Menos quadros por segundo aliviam computadores mais fracos."),
                  [(15, "15 fps"), (24, "24 fps"), (30, "30 fps")], cfg["limite_fps"],
                  lambda v: salvar("limite_fps", v))

    def pagina_atalhos():
        k = cartao(_("Atalhos de teclado"), _("Funcionam em qualquer lugar do Windows, inclusive com o Meet em primeiro plano."))
        estado = ctk.CTkLabel(k, text="", font=f_peq, text_color=c["SUAVE"], anchor="w")

        def trocar(chave_cfg, valor):
            outros = [k for k in ("atalho_privacidade", "atalho_efeito", "atalho_gravar", "atalho_pausar",
                                  "atalho_parar") if k != chave_cfg]
            if valor != A.DESATIVADO and any(valor == cfg[o] for o in outros):
                ctx["toast"](_("Esse atalho já está em uso pela outra função"))
                return
            cfg[chave_cfg] = valor
            ctx["mudou"]()
            falhas = ctx["recriar_atalhos"]()
            estado.configure(text=(_("Atalho em uso por outro programa: ") + ", ".join(falhas)) if falhas
                             else _("Atalhos ativos."), text_color=c["ERRO"] if falhas else "#3DDC97")
        mostrar = lambda v: _("Desativado") if v == A.DESATIVADO else v
        voltar = lambda v: A.DESATIVADO if v == _("Desativado") else v
        opcoes = [mostrar(o) for o in A.OPCOES]
        lista(k, _("Volto já (tela de privacidade)"), None, opcoes, mostrar(cfg["atalho_privacidade"]),
              lambda v: trocar("atalho_privacidade", voltar(v)))
        lista(k, _("Ligar/desligar o efeito"), _("Alterna entre o efeito atual e a imagem sem efeito."), opcoes,
              mostrar(cfg["atalho_efeito"]), lambda v: trocar("atalho_efeito", voltar(v)))
        lista(k, _("Iniciar/parar gravação de tela"), None, opcoes, mostrar(cfg["atalho_gravar"]),
              lambda v: trocar("atalho_gravar", voltar(v)))
        lista(k, _("Pausar/retomar gravação"), None, opcoes, mostrar(cfg["atalho_pausar"]),
              lambda v: trocar("atalho_pausar", voltar(v)))
        lista(k, _("Parar gravação"), _("Só para (não inicia uma nova)."), opcoes, mostrar(cfg["atalho_parar"]),
              lambda v: trocar("atalho_parar", voltar(v)))
        estado.pack(fill="x", pady=(6, 0))

    def pagina_privacidade():
        k = cartao(_("Tela “Volto já”"), _("Aparece no lugar da sua imagem quando você liga o Volto já. "
                                       "A câmera continua ligada na chamada."))
        var_texto = ctk.StringVar(value=cfg["texto_privacidade"])

        def texto_mudou(*_args):
            cfg["texto_privacidade"] = var_texto.get()[:40]
            if motor.privacidade:
                motor.alternar_privacidade(True)
            ctx["mudou"]()
        var_texto.trace_add("write", texto_mudou)
        ctk.CTkEntry(linha(k, _("Texto")), textvariable=var_texto, width=240, height=32, corner_radius=8,
                     font=f_normal, fg_color=c["CARD_2"], border_color=c["BORDA"], text_color=c["TEXTO"]).pack()

        nome = os.path.basename(cfg["imagem_privacidade"]) if cfg["imagem_privacidade"] else _("Imagem desfocada (padrão)")
        img_lbl = ctk.CTkLabel(k, text=_("Fundo: {nome}").format(nome=nome), font=f_peq, text_color=c["SUAVE"], anchor="w")
        img_lbl.pack(fill="x", pady=(8, 0))

        def escolher():
            from tkinter import filedialog
            arq = filedialog.askopenfilename(parent=j, title=_("Imagem da tela Volto já"),
                                             filetypes=[(_("Imagens"), "*.jpg *.jpeg *.png *.bmp *.webp")])
            if arq:
                salvar("imagem_privacidade", arq, lambda: motor.privacidade and motor.alternar_privacidade(True))
                img_lbl.configure(text=_("Fundo: {nome}").format(nome=os.path.basename(arq)))

        def padrao():
            salvar("imagem_privacidade", "", lambda: motor.privacidade and motor.alternar_privacidade(True))
            img_lbl.configure(text=_("Fundo: Imagem desfocada (padrão)"))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Escolher imagem…"), escolher)
        botao(l, _("Usar imagem desfocada"), padrao)
        botao(l, _("Testar agora"), ctx["alternar_privacidade"], principal=True)

        cartao(_("Seus dados"), _("O OpenBokeh processa tudo no seu computador: nenhuma imagem é gravada ou enviada, "
                             "não há conta, anúncios nem telemetria, e a versão instalada não acessa a internet."))

    def pagina_dados():
        pasta = os.path.dirname(os.path.abspath(M.CONFIG_ARQ))
        k = cartao(_("Configurações e perfis"), _("Ficam em {pasta}").format(pasta=pasta))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Exportar…"), ctx["exportar"])
        botao(l, _("Importar…"), ctx["importar"])
        botao(l, _("Abrir pasta"), lambda: os.startfile(pasta))

        k = cartao(_("Registro de erros"), _("Arquivo técnico (sem imagens) que ajuda a resolver problemas."))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        botao(l, _("Abrir registro"), ctx["abrir_registro"])
        botao(l, _("Copiar diagnóstico"), ctx["copiar_diagnostico"])

        k = cartao(_("Restaurar padrões"), _("Volta todas as configurações ao original. Seus perfis são mantidos."))
        l = ctk.CTkFrame(k, fg_color="transparent")
        l.pack(fill="x")
        confirmar = {"armado": False}

        def restaurar():
            if not confirmar["armado"]:
                confirmar["armado"] = True
                b.configure(text=_("Clique de novo para confirmar"))
                j.after(4000, lambda: (confirmar.update(armado=False),
                                       b.winfo_exists() and b.configure(text=_("Restaurar tudo"))))
                return
            ctx["restaurar_tudo"]()
            j.destroy()
        b = botao(l, _("Restaurar tudo"), restaurar, perigo=True)

    paginas = {"gravacao": pagina_gravacao, "geral": pagina_geral, "webcam": pagina_webcam, "virtual": pagina_virtual, "microfone": pagina_microfone,
               "desempenho": pagina_desempenho, "atalhos": pagina_atalhos, "privacidade": pagina_privacidade,
               "dados": pagina_dados}

    def mostrar(cod):
        for w in conteudo.winfo_children():
            w.destroy()
        for k, bt in botoes_nav.items():
            bt.configure(fg_color=c["ACENTO"] if k == cod else "transparent",
                         text_color="#FFFFFF" if k == cod else c["TEXTO"])
        titulo_pagina.configure(text=dict((k, t) for k, _i, t in CATEGORIAS)[cod])
        paginas[cod]()
        conteudo._parent_canvas.yview_moveto(0)

    for cod, icone, nome in CATEGORIAS:
        bt = ctk.CTkButton(nav, text=f"  {icone}   {nome}", anchor="w", height=38, corner_radius=8, font=f_normal,
                           fg_color="transparent", hover_color=c["CARD_2"], text_color=c["TEXTO"],
                           command=lambda k=cod: mostrar(k))
        bt.pack(fill="x", padx=10, pady=2)
        botoes_nav[cod] = bt
    ctk.CTkLabel(nav, text=_("As mudanças são salvas\nautomaticamente."), font=f_peq, text_color=c["SUAVE"],
                 justify="left", anchor="w").pack(side="bottom", fill="x", padx=18, pady=16)
    mostrar(categoria)
    return j
