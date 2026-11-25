"""
Pagina "Gravar tela" da janela principal: previa do video (tela + webcam no formato
final), botao grande de gravar, opcoes rapidas e gravacoes recentes.
"""

import os
import threading
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

import gravacao_ui as GU
import gravador as G
from i18n import _


class PaginaGravacao:
    def __init__(self, pai, root, cfg, motor, grav, c, fontes, mudou, abrir_config, toast, prev_w, prev_h, lateral_w):
        self.root, self.cfg, self.motor, self.grav, self.c = root, cfg, motor, grav, c
        self.mudou, self.abrir_config, self.toast = mudou, abrir_config, toast
        self.visivel = False
        self._ultima_previa = 0.0
        self._capturando = False
        self._base = None            # (imagem da tela, retangulo da webcam, borda) da ultima captura
        self._base_nova = False
        self._ultimo_num = -1
        self._estado_widgets = {}
        f_normal, f_peq, f_secao = fontes["normal"], fontes["peq"], fontes["secao"]
        self.f_peq = f_peq
        self.frame = fr = ctk.CTkFrame(pai, fg_color="transparent")

        # ================= esquerda: previa + gravar + recentes
        esq = ctk.CTkFrame(fr, fg_color="transparent")
        esq.grid(row=0, column=0, sticky="n", padx=(20, 10), pady=(0, 20))
        moldura = ctk.CTkFrame(esq, fg_color=c["CARD"], corner_radius=16, border_width=1, border_color=c["BORDA"])
        moldura.pack()
        self.caixa = tk.Frame(moldura, width=prev_w, height=prev_h, bg="#000000", highlightthickness=0)
        self.caixa.pack(padx=8, pady=(8, 4))
        self.caixa.pack_propagate(False)
        self.previa = tk.Label(self.caixa, bg="#000000", bd=0, fg=c["SUAVE"], font=("Segoe UI", 12))
        self.previa.pack(fill="both", expand=True)
        self.lbl_previsao = ctk.CTkLabel(moldura, text="", font=f_peq, anchor="w")
        self.lbl_previsao.pack(fill="x", padx=14, pady=(0, 8))

        acao = ctk.CTkFrame(esq, fg_color=c["CARD"], corner_radius=14, border_width=1, border_color=c["BORDA"])
        acao.pack(fill="x", pady=(12, 0))
        linha = ctk.CTkFrame(acao, fg_color="transparent")
        linha.pack(fill="x", padx=16, pady=14)
        self.bt_gravar = ctk.CTkButton(linha, text="", width=250, height=46, corner_radius=12,
                                       font=ctk.CTkFont("Segoe UI", 15, "bold"), command=self.grav.alternar)
        self.bt_gravar.pack(side="left")
        self.bt_pausa = ctk.CTkButton(linha, text=_("⏸  Pausar"), width=110, height=46, corner_radius=12,
                                      font=f_normal, fg_color=c["CARD_2"], hover_color=c["BORDA"],
                                      text_color=c["TEXTO"], border_width=1, border_color=c["BORDA"],
                                      command=self.grav.pausar)
        self.bt_pausa.pack(side="left", padx=(10, 0))
        self.lbl_info = ctk.CTkLabel(linha, text="", font=f_peq, text_color=c["SUAVE"], justify="left", anchor="w")
        self.lbl_info.pack(side="left", padx=(16, 0), fill="x", expand=True)

        rec = ctk.CTkFrame(esq, fg_color=c["CARD"], corner_radius=14, border_width=1, border_color=c["BORDA"])
        rec.pack(fill="x", pady=(12, 0))
        topo_rec = ctk.CTkFrame(rec, fg_color="transparent")
        topo_rec.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(topo_rec, text=_("Gravações recentes").upper(), font=f_secao, text_color=c["SUAVE"],
                     anchor="w").pack(side="left")
        ctk.CTkButton(topo_rec, text=_("Abrir pasta"), width=90, height=26, corner_radius=8, font=f_peq,
                      fg_color="transparent", hover_color=c["CARD_2"], text_color=c["TEXTO"], border_width=1,
                      border_color=c["BORDA"], command=self.grav.abrir_pasta).pack(side="right")
        self.lista_rec = ctk.CTkFrame(rec, fg_color="transparent")
        self.lista_rec.pack(fill="x", padx=16, pady=(0, 12))

        # ================= direita: opcoes rapidas
        dir_ = ctk.CTkScrollableFrame(fr, width=lateral_w - 30, height=560, corner_radius=14, fg_color=c["CARD"],
                                      border_width=1, border_color=c["BORDA"], scrollbar_button_color=c["BORDA"])
        dir_.grid(row=0, column=1, sticky="n", padx=(10, 20), pady=(0, 20))
        self.dir = dir_
        self._montar_opcoes(dir_, f_normal, f_peq, f_secao)

        grav.ao_mudar.append(self.pintar)
        grav.ao_terminar.append(lambda _a: self.atualizar_recentes())
        self.pintar()
        self.atualizar_recentes()
        self._laco()

    # ---------------------------------------------------------------- opcoes
    def _montar_opcoes(self, p, f_normal, f_peq, f_secao):
        c, cfg = self.c, self.cfg

        def secao(txt, topo=4):
            ctk.CTkLabel(p, text=txt.upper(), font=f_secao, text_color=c["SUAVE"], anchor="w").pack(
                fill="x", padx=12, pady=(topo, 4))

        def rotulo(txt, pai=None):
            ctk.CTkLabel(pai or p, text=txt, font=f_normal, text_color=c["TEXTO"], anchor="w").pack(fill="x", padx=12,
                                                                                            pady=(4, 2))

        def opcao(chave, opcoes, ao_vivo=False, pai=None):
            rot = dict(opcoes)
            inv = {v: k for k, v in opcoes}
            var = ctk.StringVar(value=rot.get(cfg[chave], opcoes[0][1]))
            ctk.CTkOptionMenu(pai or p, values=[r for _k, r in opcoes], variable=var, height=30, corner_radius=8,
                              font=f_normal, dropdown_font=f_normal, fg_color=c["CARD_2"], button_color=c["BORDA"],
                              button_hover_color=c["ACENTO"], dropdown_fg_color=c["CARD_2"],
                              dropdown_hover_color=c["ACENTO"], text_color=c["TEXTO"],
                              command=lambda r: self._mudar(chave, inv[r], ao_vivo)).pack(fill="x", padx=12)
            return var

        def segmentos(chave, opcoes, ao_vivo=False, depois=None):
            rot = dict(opcoes)
            inv = {v: k for k, v in opcoes}
            var = ctk.StringVar(value=rot.get(cfg[chave], opcoes[0][1]))

            def mudou(r):
                self._mudar(chave, inv[r], ao_vivo)
                if depois:
                    depois()
            ctk.CTkSegmentedButton(p, values=[r for _k, r in opcoes], variable=var, height=30, corner_radius=8,
                                   font=f_peq, fg_color=c["CARD_2"], selected_color=c["ACENTO"],
                                   selected_hover_color=c["ACENTO_HOVER"], unselected_color=c["CARD_2"],
                                   unselected_hover_color=c["BORDA"], text_color=c["TEXTO"],
                                   command=mudou).pack(fill="x", padx=12)
            return var

        def chave(chave_cfg, texto, ao_vivo=False):
            var = ctk.BooleanVar(value=cfg[chave_cfg])
            ctk.CTkSwitch(p, text=texto, variable=var, font=f_normal, text_color=c["TEXTO"],
                          progress_color=c["ACENTO"], button_color="#FFFFFF", button_hover_color="#E6E0FF",
                          fg_color=c["BORDA"], switch_width=40, switch_height=20,
                          command=lambda: self._mudar(chave_cfg, var.get(), ao_vivo)).pack(anchor="w", padx=12, pady=3)
            return var

        secao(_("O que gravar"), 8)
        segmentos("grav_fonte", [("tela", _("Tela inteira")), ("regiao", _("Região")), ("janela", _("Janela"))],
                  depois=lambda: self._montar_fonte())
        self.caixa_fonte = ctk.CTkFrame(p, fg_color="transparent")
        self.caixa_fonte.pack(fill="x")
        self._ajudantes = (rotulo, opcao)
        self._montar_fonte()
        rotulo(_("Formato do vídeo"))
        opcao("grav_saida", [("auto", _("Automático (recomendado)")), ("nativa", _("Nativo do monitor")),
                             ("1440p", "16:9 · 2560×1440"), ("1080p", "16:9 · 1920×1080")])
        rotulo(_("Encaixe no vídeo"))
        segmentos("grav_encaixe", [("inteira", _("Com faixas")), ("preencher", _("Preencher")), ("recorte", "1:1")], True)
        ctk.CTkLabel(p, text=_("Com faixas: tudo aparece · Preencher: sem faixas,\ncorta as bordas · 1:1: tamanho real"),
                     font=f_peq, text_color=c["SUAVE"], anchor="w", justify="left").pack(fill="x", padx=12, pady=(2, 0))

        secao(_("Webcam no vídeo"), 14)
        segmentos("grav_cam_forma", [("nenhuma", _("Sem")), ("circulo", _("Círculo")), ("arredondado", _("Retângulo")),
                                     ("pessoa", _("Só você"))], True)
        rotulo(_("Posição"))
        opcao("grav_cam_posicao", [("inferior_direito", _("Inferior direito")), ("inferior_esquerdo", _("Inferior esquerdo")),
                                   ("superior_direito", _("Superior direito")), ("superior_esquerdo", _("Superior esquerdo"))], True)
        rotulo(_("Tamanho"))
        segmentos("grav_cam_tamanho", [(20, _("Pequena")), (28, _("Média")), (38, _("Grande"))], True)

        secao(_("Áudio"), 14)
        self.medidores = {}

        def medidor(chave_nivel):
            l = ctk.CTkFrame(p, fg_color="transparent")
            l.pack(fill="x", padx=12, pady=(2, 4))
            b = ctk.CTkProgressBar(l, height=6, progress_color="#3DDC97", fg_color=c["BORDA"])
            b.pack(side="left", fill="x", expand=True)
            b.set(0)
            self.medidores[chave_nivel] = b

        chave("grav_mic", _("Microfone"))
        linha = ctk.CTkFrame(p, fg_color="transparent")
        linha.pack(fill="x", padx=12, pady=(2, 0))
        self.var_mic = ctk.StringVar()
        self.menu_mic = ctk.CTkOptionMenu(linha, values=[""], variable=self.var_mic, height=30, corner_radius=8,
                                          font=f_peq, dropdown_font=f_peq, fg_color=c["CARD_2"],
                                          button_color=c["BORDA"], button_hover_color=c["ACENTO"],
                                          dropdown_fg_color=c["CARD_2"], dropdown_hover_color=c["ACENTO"],
                                          text_color=c["TEXTO"], command=self._escolher_mic, width=230)
        self.menu_mic.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(linha, text="↻", width=32, height=30, corner_radius=8, font=f_peq, fg_color=c["CARD_2"],
                      hover_color=c["BORDA"], text_color=c["TEXTO"], border_width=1, border_color=c["BORDA"],
                      command=self._listar_mics).pack(side="left", padx=(6, 0))
        medidor("nivel_mic")
        self.lbl_mic = ctk.CTkLabel(p, text="", font=f_peq, text_color="#FFC857", anchor="w", justify="left")
        self.lbl_mic.pack(fill="x", padx=12)
        chave("grav_mic_sem_ruido", _("Tirar o ruído do microfone"))
        chave("grav_som_pc", _("Som do computador"))
        medidor("nivel_pc")
        import microfone as MIC
        self.medidor_mic = MIC.Medidor()
        self._listar_mics()

        secao(_("Qualidade"), 14)
        segmentos("grav_preset", [("edicao", _("Edição")), ("alta", _("Alta")), ("compacta", _("Compacta"))])
        self.lbl_peso = ctk.CTkLabel(p, text="", font=f_peq, text_color=c["SUAVE"], anchor="w", justify="left")
        self.lbl_peso.pack(fill="x", padx=12, pady=(2, 0))
        rotulo(_("Quadros por segundo"))
        segmentos("grav_fps", [(30, "30"), (60, "60")])

        ctk.CTkButton(p, text=_("Mais opções…"), height=32, corner_radius=8, font=f_normal, fg_color="transparent",
                      hover_color=c["CARD_2"], text_color=c["TEXTO"], border_width=1, border_color=c["BORDA"],
                      command=lambda: self.abrir_config("gravacao")).pack(fill="x", padx=12, pady=(16, 10))
        self._texto_peso()

    def _montar_fonte(self):
        """Parte que muda conforme "O que gravar": monitor, botao de regiao ou lista de janelas."""
        import captura as CAP
        c, cfg, box = self.c, self.cfg, self.caixa_fonte
        rotulo, opcao = self._ajudantes
        for w in box.winfo_children():
            w.destroy()
        fonte = cfg.get("grav_fonte", "tela")
        estilo_bt = dict(height=30, corner_radius=8, font=self.f_peq, fg_color=c["CARD_2"], hover_color=c["BORDA"],
                         text_color=c["TEXTO"], border_width=1, border_color=c["BORDA"])
        if fonte in ("tela", "regiao"):
            try:
                mons = G.monitores()
            except Exception:
                mons = []
            opc = [(m["indice"], f"{i + 1}: {m['largura']}×{m['altura']}" + (_(" (principal)") if m["principal"] else ""))
                   for i, m in enumerate(mons)] or [(0, "1")]
            rotulo(_("Monitor"), box)
            opcao("grav_monitor", opc, pai=box)
        if fonte == "regiao":
            r = cfg.get("grav_regiao") or []
            txt = (_("Região: {w}×{h} (a partir de {x}, {y})").format(x=r[0], y=r[1], w=r[2], h=r[3]) if len(r) == 4
                   else _("Nenhuma região marcada ainda"))
            ctk.CTkLabel(box, text=txt, font=self.f_peq, text_color=c["SUAVE"], anchor="w").pack(fill="x", padx=12,
                                                                                                pady=(6, 2))
            ctk.CTkButton(box, text=_("✂  Marcar região na tela…"), command=self._marcar_regiao, **estilo_bt).pack(
                fill="x", padx=12)
        if fonte == "janela":
            janelas = CAP.listar_janelas()
            rot, vistos = [], set()
            for j in janelas:
                nome = j["titulo"] if len(j["titulo"]) <= 40 else j["titulo"][:38] + "…"
                if nome in vistos:
                    nome = f"{nome} ({j['exe']})"
                vistos.add(nome)
                rot.append((nome, j))
            self._janelas = dict(rot)
            atual = cfg.get("grav_janela") or {}
            escolhida = next((n for n, j in rot if j["hwnd"] == atual.get("hwnd")), None) or \
                next((n for n, j in rot if j["exe"] == atual.get("exe") and j["titulo"] == atual.get("titulo")), None) or \
                next((n for n, j in rot if j["exe"] == atual.get("exe")), None)
            rotulo(_("Janela"), box)
            linha = ctk.CTkFrame(box, fg_color="transparent")
            linha.pack(fill="x", padx=12)
            var = ctk.StringVar(value=escolhida or _("Escolha uma janela…"))
            ctk.CTkOptionMenu(linha, values=[n for n, _j in rot] or [_("(nenhuma janela aberta)")], variable=var,
                              height=30, corner_radius=8, font=self.f_peq, dropdown_font=self.f_peq,
                              fg_color=c["CARD_2"], button_color=c["BORDA"], button_hover_color=c["ACENTO"],
                              dropdown_fg_color=c["CARD_2"], dropdown_hover_color=c["ACENTO"], text_color=c["TEXTO"],
                              command=self._escolher_janela, width=230).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(linha, text="↻", width=32, command=self._montar_fonte, **dict(estilo_bt, font=self.f_peq)
                          ).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(box, text=_("A janela precisa ficar visível; o vídeo acompanha\nquando ela muda de lugar ou de tamanho."),
                         font=self.f_peq, text_color=c["SUAVE"], anchor="w", justify="left").pack(fill="x", padx=12,
                                                                                                 pady=(4, 0))

    def _listar_mics(self):
        """Lista os microfones (botao ↻ atualiza: liga um microfone e ele aparece)."""
        import microfone as MIC
        self.medidor_mic.parar()               # sem fluxo aberto a lista pode ser recarregada
        try:
            mics, _cabo = MIC.dispositivos(atualizar=not self.grav.gravando)
        except Exception:
            mics = []
        padrao = MIC.microfone_padrao()
        self._rot_padrao = _("Padrão do Windows") + (f" — {padrao}" if padrao else "")
        atual = self.cfg.get("grav_mic_entrada", "")
        valores = [self._rot_padrao] + mics
        if atual and atual not in mics:
            self.lbl_mic.configure(text=_("“{nome}” não está conectado — vai usar o padrão do Windows").format(nome=atual))
        else:
            self.lbl_mic.configure(text="")
        self.menu_mic.configure(values=valores)
        self.var_mic.set(atual if atual in mics else self._rot_padrao)

    def _escolher_mic(self, rotulo):
        nome = "" if rotulo == self._rot_padrao else rotulo
        self.lbl_mic.configure(text="")
        self._mudar("grav_mic_entrada", nome)
        self.medidor_mic.parar()               # o laco reabre no microfone novo

    def _escolher_janela(self, nome):
        j = getattr(self, "_janelas", {}).get(nome)
        if j:
            self._mudar("grav_janela", {"exe": j["exe"], "titulo": j["titulo"], "hwnd": j["hwnd"]})

    def _marcar_regiao(self):
        m = next((x for x in G.monitores() if x["indice"] == self.cfg["grav_monitor"]), None) or G.monitores()[0]

        def escolheu(r):
            self._mudar("grav_regiao", r)
            self._montar_fonte()
            self.root.deiconify()
        def abrir():
            sel = GU.SeletorRegiao(self.root, m, escolheu, self.cfg.get("grav_regiao"))
            # fechou de qualquer jeito (Esc, confirmou): a janela do OpenBokeh volta
            sel.w.bind("<Destroy>", lambda e: self.root.deiconify() if e.widget is sel.w else None)
        self.root.iconify()                       # sai da frente para a pessoa ver a tela toda
        self.root.after(300, abrir)

    def _texto_peso(self):
        p = self.cfg["grav_preset"]
        txt = {"edicao": _("H.264 · abre leve em editores · {peso}"), "alta": _("HEVC · padrão · {peso}"),
               "compacta": _("HEVC menor · {peso}")}[p]
        self.lbl_peso.configure(text=txt.format(peso=GU.PESO_HORA[p]))

    def _mudar(self, chave, valor, ao_vivo=False):
        if self.grav.gravando and not ao_vivo:
            self.toast(_("Essa opção vale a partir da próxima gravação"))
        self.cfg[chave] = valor
        self.mudou()
        if ao_vivo:
            self.grav.atualizar_layout()
        if chave == "grav_preset":
            self._texto_peso()
        self.pintar()
        self._ultima_previa = 0          # redesenha a previa ja

    # ---------------------------------------------------------------- estado
    def _conf(self, widget, **kw):
        """Configura so o que mudou (reconfigurar sem necessidade faz o CustomTkinter piscar)."""
        chave = id(widget)
        antes = self._estado_widgets.get(chave, {})
        novo = {k: v for k, v in kw.items() if antes.get(k) != v}
        if novo:
            widget.configure(**novo)
            antes.update(novo)
            self._estado_widgets[chave] = antes

    def pintar_estado(self):
        c, g = self.c, self.grav
        if g.gravando:
            e = g.g.estado()
            self._conf(self.bt_gravar, text=_("■  Parar  ·  {status}").format(status=g.status()[2:]),
                       fg_color="#C62828", hover_color="#A31F1F", text_color="#FFFFFF")
            self._conf(self.bt_pausa, state="normal", text=_("▶  Retomar") if e.pausado else _("⏸  Pausar"))
        elif g.contando:
            self._conf(self.bt_gravar, text=_("Cancelar contagem"), fg_color=c["CARD_2"], hover_color=c["BORDA"],
                       text_color=c["TEXTO"])
            self._conf(self.bt_pausa, state="disabled", text=_("⏸  Pausar"))
        else:
            self._conf(self.bt_gravar, text=_("●  Iniciar gravação"), fg_color="#D32F2F", hover_color="#B71C1C",
                       text_color="#FFFFFF")
            self._conf(self.bt_pausa, state="disabled", text=_("⏸  Pausar"))

    def pintar(self):
        """Estado dos botoes + textos que dependem das opcoes (chamado quando algo muda)."""
        self.pintar_estado()
        n = int(self.cfg.get("grav_contagem", 3))
        self._conf(self.lbl_info, text=_("{atalho} gravar/parar · {pausa} pausar\n{contagem}").format(
            atalho=self.cfg["atalho_gravar"], pausa=self.cfg["atalho_pausar"],
            contagem=(_("Contagem de {n} s, depois o OpenBokeh minimiza").format(n=n) if n else _("Começa na hora"))))
        txt, ok = GU.previsao(self.cfg)
        self._conf(self.lbl_previsao, text=("✓  " if ok else "⚠  ") + txt, text_color="#3DDC97" if ok else "#FFC857")

    def atualizar_recentes(self):
        for w in self.lista_rec.winfo_children():
            w.destroy()
        arqs = GU.recentes(self.cfg, 2)
        c = self.c
        if not arqs:
            ctk.CTkLabel(self.lista_rec, text=_("Nenhuma gravação ainda. Clique em “Iniciar gravação”."),
                         font=self.f_peq, text_color=c["SUAVE"], anchor="w").pack(fill="x", pady=4)
            return
        for a in arqs:
            l = ctk.CTkFrame(self.lista_rec, fg_color=c["CARD_2"], corner_radius=8)
            l.pack(fill="x", pady=3)
            nome = os.path.splitext(os.path.basename(a))[0].replace("OpenBokeh ", "")
            try:
                mb = os.path.getsize(a) / 1e6
            except OSError:
                mb = 0
            ctk.CTkLabel(l, text=f"🎬  {nome}", font=self.f_peq, text_color=c["TEXTO"], anchor="w").pack(
                side="left", padx=10, pady=6)
            ctk.CTkLabel(l, text=f"{mb:.0f} MB", font=self.f_peq, text_color=c["SUAVE"]).pack(side="left", padx=6)
            estilo = dict(height=26, corner_radius=6, font=self.f_peq, fg_color="transparent", hover_color=c["BORDA"],
                          text_color=c["TEXTO"], border_width=1, border_color=c["BORDA"])
            ctk.CTkButton(l, text=_("Mostrar na pasta"), width=110, command=lambda x=a: GU.mostrar_no_explorer(x),
                          **estilo).pack(side="right", padx=(4, 8))
            ctk.CTkButton(l, text=_("▶ Assistir"), width=80, command=lambda x=a: os.startfile(x), **estilo).pack(
                side="right", padx=4)

    # ---------------------------------------------------------------- mostrar/esconder e laco
    def mostrar(self, **grid):
        self.frame.grid(**grid)
        self.visivel = True
        # a propria janela some das capturas: a previa mostra o que esta atras dela (o que vai ser gravado)
        GU.excluir_da_captura(self.root, True)
        self.pintar()
        self.atualizar_recentes()
        self._ultima_previa = 0

    def esconder(self):
        self.frame.grid_remove()
        self.visivel = False
        self.medidor_mic.parar()
        if not (self.grav.gravando and self.cfg["grav_ocultar_app"]):
            GU.excluir_da_captura(self.root, False)

    def _laco(self):
        """A cada quadro novo da webcam (~30/s): poe a imagem dela sobre a ultima captura da tela.
        A captura da tela (lenta) roda numa thread, 2x por segundo (1x gravando)."""
        espera = 15          # confere com frequencia; so redesenha quando a webcam tem quadro novo
        try:
            janela_aberta = self.root.state() in ("normal", "zoomed")
            if self.visivel and janela_aberta:
                if self.grav.gravando:
                    self.pintar_estado()
                    self.medidor_mic.parar()
                    a = self.grav.audio
                    for k, b in self.medidores.items():
                        b.set(min(1.0, max(getattr(a, k, 0.0) if a else 0.0, 1e-4) ** 0.5))
                elif self.cfg["grav_mic"]:
                    # antes de gravar: medidor ao vivo do microfone escolhido (nada e gravado)
                    self.medidor_mic.iniciar(self.cfg.get("grav_mic_entrada", ""))
                    self.medidores["nivel_mic"].set(min(1.0, max(self.medidor_mic.nivel, 1e-4) ** 0.5))
                else:
                    self.medidor_mic.parar()
                    self.medidores["nivel_mic"].set(0)
                agora = time.time()
                if not self._capturando and agora - self._ultima_previa > (1.0 if self.grav.gravando else 0.5):
                    self._ultima_previa = agora
                    self._capturando = True
                    lw, lh = max(self.caixa.winfo_width(), 50), max(self.caixa.winfo_height(), 50)
                    GU.excluir_da_captura(self.root, True)   # (parar a gravacao devolve a janela as capturas)
                    threading.Thread(target=self._capturar, args=(dict(self.cfg), lw, lh), daemon=True).start()
                num = getattr(self.motor, "num_saida", 0)
                if self._base is not None and (num != self._ultimo_num or self._base_nova):
                    self._ultimo_num, self._base_nova = num, False
                    img = GU.previa_webcam(self._base, self.cfg, self.motor)
                    self._foto = ImageTk.PhotoImage(Image.fromarray(img))
                    self.previa.configure(image=self._foto, text="")
            else:
                espera = 200
                self.medidor_mic.parar()       # janela minimizada/outra pagina: solta o microfone
        except Exception as e:
            print(f"[aviso] previa da gravacao: {e}")
        self.root.after(espera, self._laco)

    def _capturar(self, cfg, lw, lh):
        try:
            base = GU.previa_base(cfg, lw, lh)
            if base is None:
                self.root.after(0, lambda: self.previa.configure(image="", text=_("Nenhum monitor encontrado")))
            else:
                self._base, self._base_nova = base, True
        except Exception as e:
            print(f"[aviso] captura da previa: {e}")
        finally:
            self._capturando = False
