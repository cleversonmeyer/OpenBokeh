"""Barra de menus escura (Arquivo, Camera, Exibir, Ajuda).

O menu nativo do Windows ignora as cores do tema, entao a barra e os menus
suspensos sao desenhados com CustomTkinter, no mesmo visual do app.
Itens: ("Texto", funcao) | ("Texto", funcao, "atalho") | ("Texto", funcao, None, var_booleana) | "-"
"""

import customtkinter as ctk


class BarraMenu(ctk.CTkFrame):
    def __init__(self, master, menus, cores, fonte):
        self.c = cores
        super().__init__(master, fg_color="transparent", height=30)
        self.fonte = fonte
        self.aberto = None
        for titulo, itens in menus:
            bt = ctk.CTkButton(self, text=titulo, width=10, height=26, corner_radius=6, font=fonte,
                               fg_color="transparent", hover_color=cores["CARD_2"], text_color=cores["SUAVE"])
            bt.pack(side="left", padx=(0, 2))
            bt.configure(command=lambda b=bt, i=itens: self._alternar(b, i))

    def _alternar(self, botao, itens):
        if self.aberto is not None:
            dono = self.aberto._dono
            self.fechar()
            if dono is botao:
                return
        self._abrir(botao, itens)

    def fechar(self, _=None):
        if self.aberto is not None:
            try:
                self.aberto.destroy()
            except Exception:
                pass
            self.aberto = None

    def _abrir(self, botao, itens):
        c = self.c
        m = ctk.CTkToplevel(self, fg_color=c["BORDA"])
        m.overrideredirect(True)
        m.attributes("-topmost", True)
        m._dono = botao
        self.aberto = m
        corpo = ctk.CTkFrame(m, fg_color=c["CARD"], corner_radius=0)
        corpo.pack(fill="both", expand=True, padx=1, pady=1)
        for item in itens:
            if item == "-":
                ctk.CTkFrame(corpo, height=1, fg_color=c["BORDA"]).pack(fill="x", padx=8, pady=4)
                continue
            texto, acao = item[0], item[1]
            atalho = item[2] if len(item) > 2 else None
            if callable(atalho):
                atalho = atalho()
            var = item[3] if len(item) > 3 else None
            marca = ("✓  " if var is not None and var.get() else "     ") if var is not None else "     "
            linha = ctk.CTkFrame(corpo, fg_color="transparent", corner_radius=6, height=30, cursor="hand2")
            linha.pack(fill="x", padx=4, pady=1)
            esq = ctk.CTkLabel(linha, text=marca + texto, font=self.fonte, text_color=c["TEXTO"], anchor="w")
            esq.pack(side="left", padx=(6, 24), pady=3)
            dir_ = ctk.CTkLabel(linha, text=atalho or "", font=self.fonte, text_color=c["SUAVE"], anchor="e")
            dir_.pack(side="right", padx=(0, 10))

            def clicar(_e=None, a=acao, v=var):
                self.fechar()
                if v is not None:
                    v.set(not v.get())
                if a:
                    self.after(10, a)

            def entrar(_e=None, l=linha):
                l.configure(fg_color=c["ACENTO"])

            def sair(_e=None, l=linha):
                l.configure(fg_color="transparent")
            for w in (linha, esq, dir_):
                w.bind("<Button-1>", clicar)
                w.bind("<Enter>", entrar)
                w.bind("<Leave>", sair)
        m.update_idletasks()
        x = botao.winfo_rootx()
        y = botao.winfo_rooty() + botao.winfo_height() + 2
        m.geometry(f"+{x}+{y}")
        # fecha ao clicar fora, apertar Esc ou a janela perder o foco
        m.bind("<Escape>", self.fechar)
        m.after(50, lambda: (m.focus_force(), m.bind("<FocusOut>", self._ao_perder_foco)))

    def _ao_perder_foco(self, _e=None):
        if self.aberto is None:
            return
        # FocusOut tambem dispara entre widgets do proprio menu; confere depois
        self.after(120, self._fechar_se_fora)

    def _fechar_se_fora(self):
        if self.aberto is None:
            return
        foco = self.aberto.focus_get() if self.aberto.winfo_exists() else None
        if foco is None or not str(foco).startswith(str(self.aberto)):
            self.fechar()
