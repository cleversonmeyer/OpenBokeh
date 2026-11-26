"""
Gravacao de tela na interface do OpenBokeh:
  - Controle: iniciar (com contagem 3-2-1), pausar, parar, espaco em disco, pasta liberada
  - MiniBarra: barrinha flutuante com cronometro, pausar e parar (nao aparece no video)
  - previa_composicao: imagem de como o video vai sair (tela + webcam no formato final)
  - recentes: ultimos videos gravados
"""

import ctypes
import glob
import os
import shutil

import cv2
import numpy as np

import captura as CAP
import microfone as MIC
import gravador as G
from i18n import _

WDA_NONE, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x11
MIN_LIVRE_INICIAR = 2 * 1024 ** 3      # 2 GB livres para comecar
MIN_LIVRE_GRAVANDO = 500 * 1024 ** 2   # abaixo de 500 MB a gravacao para sozinha (e salva)

PADRAO = {
    "grav_fonte": "tela",            # tela | regiao | janela
    "grav_regiao": [],               # [x, y, w, h] no monitor escolhido
    "grav_janela": {},               # {"exe", "titulo", "hwnd"} da janela escolhida
    "grav_monitor": 0,
    "grav_saida": "auto",            # auto | nativa | 1440p | 1080p
    "grav_encaixe": "inteira",       # inteira (com faixas) | preencher (sem faixas) | recorte (1:1)
    "grav_fundo": "desfocado",       # desfocado | cor
    "grav_preset": "alta",           # edicao | alta | compacta
    "grav_fps": 60,
    "grav_cursor": True,
    "grav_cam_forma": "circulo",     # nenhuma | circulo | arredondado | pessoa | retangulo
    "grav_cam_posicao": "inferior_direito",
    "grav_cam_tamanho": 28,          # % da altura do video
    "grav_cam_borda": 4,             # px em 1080p
    "grav_mic": True,
    "grav_mic_entrada": "",          # microfone da gravacao ("" = padrao do Windows)
    "ganhos_microfone": {},          # nome do microfone -> volume em dB (-12..+24); vale p/ gravacao e chamadas
    "volume_automatico": True,       # nivela a voz (sobe microfone baixo, segura o alto) + limitador
    "grav_mic_sem_ruido": True,
    "grav_som_pc": True,
    "grav_pasta": "",
    "grav_ocultar_app": True,        # as janelas do OpenBokeh nao aparecem no video
    "grav_contagem": 3,              # segundos de contagem antes de comecar (0 = direto)
    "grav_minimizar": True,          # minimiza o OpenBokeh ao comecar (fica a mini barra)
    "atalho_gravar": "Ctrl+Alt+R",   # iniciar/parar
    "atalho_pausar": "Ctrl+Alt+P",   # pausar/retomar
    "atalho_parar": "Ctrl+Alt+S",    # so parar (nao inicia)
}

# medido numa RX 7600, 2560x1080 a 60 fps, texto rolando (2026-11-25)
PESO_HORA = {"edicao": "~2,6 GB/h", "alta": "~1,4 GB/h", "compacta": "~1,2 GB/h"}


def excluir_da_captura(janela, sim=True):
    """A janela some de gravacoes e capturas de tela (a pessoa continua vendo)."""
    try:
        h = ctypes.windll.user32.GetAncestor(janela.winfo_id(), 2)      # GA_ROOT
        ctypes.windll.user32.SetWindowDisplayAffinity(h, WDA_EXCLUDEFROMCAPTURE if sim else WDA_NONE)
    except Exception:
        pass


def monitor_escolhido(cfg):
    mons = G.monitores()
    if not mons:
        return None
    return next((x for x in mons if x["indice"] == cfg["grav_monitor"]), mons[0])


def fonte_atual(cfg):
    """(monitor, regiao, hwnd, problema). regiao = (x, y, w, h) no monitor ou None (tela toda).
    problema = texto para mostrar se a janela/regiao escolhida nao serve."""
    mons = G.monitores()
    if not mons:
        return None, None, None, _("Nenhum monitor encontrado")
    m = next((x for x in mons if x["indice"] == cfg["grav_monitor"]), mons[0])
    fonte = cfg.get("grav_fonte", "tela")
    if fonte == "regiao":
        r = cfg.get("grav_regiao") or []
        if len(r) == 4 and r[2] >= 16 and r[3] >= 16:
            return m, CAP.no_monitor((m["x"] + r[0], m["y"] + r[1], m["x"] + r[0] + r[2], m["y"] + r[1] + r[3]), m), \
                None, None
        return m, None, None, _("Selecione a região que vai ser gravada")
    if fonte == "janela":
        h = CAP.achar_janela(cfg.get("grav_janela") or {})
        if not h:
            return m, None, None, _("Escolha a janela que vai ser gravada")
        ret = CAP.retangulo(h)
        if not ret:
            return m, None, h, _("A janela está minimizada — abra ela para gravar")
        mj = CAP.monitor_da_area(ret, mons) or m
        return mj, CAP.no_monitor(ret, mj), h, None
    return m, None, None, None


def saida_efetiva(cfg, monitor, regiao=None):
    nome = cfg["grav_saida"]
    if nome != "auto":
        return nome
    if regiao is None and cfg["grav_encaixe"] == "inteira":
        # tela toda com faixas: ultrawide -> 16:9 1440p com a tela em 1:1; senao a resolucao do monitor
        return "1440p" if monitor["largura"] / monitor["altura"] > 1.9 else "nativa"
    # regiao, janela, "preencher" ou 1:1: o tamanho 16:9 mais perto do que e capturado
    altura = regiao[3] if regiao else monitor["altura"]
    return "1080p" if altura <= 1150 else "1440p"


def opcoes(cfg):
    m, regiao, hwnd, _p = fonte_atual(cfg)
    return {
        "monitor": m["indice"] if m else 0, "regiao": regiao, "hwnd": hwnd,
        "saida": saida_efetiva(cfg, m, regiao) if m else "nativa",
        "encaixe": cfg["grav_encaixe"], "fundo": cfg["grav_fundo"],
        "preset": cfg["grav_preset"], "fps": int(cfg["grav_fps"]), "cursor": cfg["grav_cursor"],
        "cam_forma": cfg["grav_cam_forma"], "cam_posicao": cfg["grav_cam_posicao"],
        "cam_tamanho": cfg["grav_cam_tamanho"], "cam_borda": cfg["grav_cam_borda"],
        "audio": bool(cfg["grav_mic"] or cfg["grav_som_pc"]),
    }


def previsao(cfg):
    """(texto, nitido) sobre como a imagem vai entrar no video, para mostrar antes de gravar."""
    try:
        m, regiao, _h, problema = fonte_atual(cfg)
    except Exception:
        return "", True
    if problema:
        return problema, False
    sw, sh = G.tamanho_saida(saida_efetiva(cfg, m, regiao), m["largura"], m["altura"])
    _a, dest, escala = G.layout_tela(m["largura"], m["altura"], sw, sh, cfg["grav_encaixe"], regiao)
    if abs(escala - 1) < 1e-3:
        return _("Vídeo {w}×{h} · texto em 1:1 (nitidez máxima)").format(w=sw, h=sh), True
    if escala < 1:
        return _("Vídeo {w}×{h} · imagem ampliada {p}% (letras maiores, um pouco mais suaves)").format(
            w=sw, h=sh, p=round(100 / escala)), True
    return (_("Vídeo {w}×{h} · tela reduzida a {p}% (texto menos nítido — prefira 1440p ou recorte)")
            .format(w=sw, h=sh, p=round(100 / escala)), False)


# ---------------------------------------------------------------- previa do video
def _mascara(forma, w, h, alpha=None):
    if forma == "pessoa" and alpha is not None:
        return alpha
    m = np.zeros((h, w), np.uint8)
    if forma == "circulo":
        cv2.circle(m, (w // 2, h // 2), min(w, h) // 2, 255, -1, cv2.LINE_AA)
    elif forma == "arredondado":
        r = int(min(w, h) * 0.18)
        cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
        cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
        for cx, cy in ((r, r), (w - r - 1, r), (r, h - r - 1), (w - r - 1, h - r - 1)):
            cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    else:
        m[:] = 255
    return m.astype(np.float32) / 255.0


def _cobrir(img, w, h):
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    nw, nh = max(w, int(round(iw * s))), max(h, int(round(ih * s)))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    x, y = (nw - w) // 2, (nh - h) // 2
    return r[y:y + h, x:x + w]


def previa_base(cfg, caixa_w, caixa_h):
    """Parte "lenta" da previa (captura da tela + faixas), no tamanho de exibicao.
    Devolve (imagem RGB, retangulo da webcam ou None, espessura da borda) ou None.
    Pode rodar fora da thread da interface."""
    from PIL import ImageGrab
    m, regiao, _h, _p = fonte_atual(cfg)
    if not m:
        return None
    sw, sh = G.tamanho_saida(saida_efetiva(cfg, m, regiao), m["largura"], m["altura"])
    k = min(caixa_w / sw, caixa_h / sh)
    ow, oh = max(2, int(sw * k)), max(2, int(sh * k))
    tela = np.asarray(ImageGrab.grab(bbox=(m["x"], m["y"], m["x"] + m["largura"], m["y"] + m["altura"]),
                                     all_screens=True).convert("RGB"))
    area, dest, _e = G.layout_tela(m["largura"], m["altura"], sw, sh, cfg["grav_encaixe"], regiao)
    if cfg["grav_fundo"] == "desfocado":
        ax0, ay0, aw0, ah0 = area
        peq = cv2.resize(tela[ay0:ay0 + ah0, ax0:ax0 + aw0], (max(8, ow // 8), max(8, oh // 8)),
                         interpolation=cv2.INTER_AREA)
        fundo = _cobrir(peq, max(1, ow // 8), max(1, oh // 8))
        out = (cv2.resize(cv2.GaussianBlur(fundo, (0, 0), 2), (ow, oh)) * 0.55).astype(np.uint8)
    else:
        out = np.full((oh, ow, 3), (18, 16, 28), np.uint8)
    ax, ay, aw, ah = area
    dx, dy, dw, dh = [int(round(v * k)) for v in dest]
    dw, dh = min(dw, ow - dx), min(dh, oh - dy)
    if dw > 0 and dh > 0:
        out[dy:dy + dh, dx:dx + dw] = cv2.resize(tela[ay:ay + ah, ax:ax + aw], (dw, dh), interpolation=cv2.INTER_AREA)
    ret = None
    if cfg["grav_cam_forma"] != "nenhuma":
        cx, cy, cw, ch = [int(round(v * k)) for v in G.layout_webcam(sw, sh, cfg["grav_cam_forma"],
                                                                      cfg["grav_cam_posicao"], cfg["grav_cam_tamanho"])]
        cx, cy = max(0, cx), max(0, cy)
        cw, ch = min(cw, ow - cx), min(ch, oh - cy)
        if cw > 4 and ch > 4:
            ret = (cx, cy, cw, ch)
    borda = int(cfg["grav_cam_borda"] * k * sh / 1080)
    return out, ret, borda


_cache_masc = {}


def previa_webcam(base, cfg, motor):
    """Parte "rapida": poe a webcam (quadro atual do motor) sobre a base. ~1-2 ms."""
    img, ret, borda = base
    forma = cfg["grav_cam_forma"]
    cam = getattr(motor, "saida", None)
    if ret is None or cam is None:
        return img
    out = img.copy()
    cx, cy, cw, ch = ret
    pedaco = _cobrir(cam, cw, ch).astype(np.float32)
    if forma == "pessoa":
        alpha = getattr(motor, "alpha", None)
        msk = _cobrir(alpha, cw, ch) if alpha is not None else np.ones((ch, cw), np.float32)
    else:
        chave = (forma, cw, ch)
        if chave not in _cache_masc:
            _cache_masc.clear()
            _cache_masc[chave] = _mascara(forma, cw, ch)
        msk = _cache_masc[chave]
    msk = msk[..., None]
    reg = out[cy:cy + ch, cx:cx + cw].astype(np.float32)
    out[cy:cy + ch, cx:cx + cw] = (pedaco * msk + reg * (1 - msk)).astype(np.uint8)
    if borda > 0 and forma == "circulo":
        cv2.circle(out, (cx + cw // 2, cy + ch // 2), min(cw, ch) // 2 - borda // 2, (255, 255, 255), max(1, borda),
                   cv2.LINE_AA)
    return out


def recentes(cfg, n=4):
    """Ultimos videos (mais novos primeiro) da pasta escolhida e da pasta liberada."""
    pastas = {cfg["grav_pasta"] or G.pasta_padrao(), os.path.join(os.path.expanduser("~"), _("Gravações OpenBokeh"))}
    arqs = []
    for p in pastas:
        arqs += glob.glob(os.path.join(p, "*.mp4"))
    arqs = [a for a in arqs if os.path.isfile(a)]
    return sorted(arqs, key=os.path.getmtime, reverse=True)[:n]


def mostrar_no_explorer(arquivo):
    """Abre a pasta com o arquivo selecionado. Usa a API do Windows: pela linha de
    comando ("explorer /select,...") as aspas se perdiam com espacos/acentos no caminho
    e o Explorer abria em Documentos."""
    caminho = os.path.normpath(os.path.abspath(arquivo))
    try:
        sh = ctypes.windll.shell32
        sh.ILCreateFromPathW.restype = ctypes.c_void_p
        sh.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
        sh.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        sh.ILFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.ole32.CoInitialize(None)
        pidl = sh.ILCreateFromPathW(caminho)
        if pidl:
            try:
                if sh.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == 0:
                    return
            finally:
                sh.ILFree(pidl)
    except Exception as e:
        print(f"[aviso] mostrar na pasta: {e}")
    os.startfile(os.path.dirname(caminho))      # plano B: so abre a pasta


def _gravavel(pasta):
    try:
        os.makedirs(pasta, exist_ok=True)
        teste = os.path.join(pasta, ".openbokeh-teste")
        with open(teste, "w"):
            pass
        os.remove(teste)
        return True
    except OSError:
        return False


def _livre(pasta):
    try:
        return shutil.disk_usage(pasta).free
    except OSError:
        return None


# ---------------------------------------------------------------- janelinhas flutuantes
class Contagem:
    """3-2-1 grande no centro da tela; clique cancela. Nao aparece no video."""

    def __init__(self, root, segundos, ao_terminar, ao_cancelar):
        import customtkinter as ctk
        self.root, self.ao_terminar, self.ao_cancelar = root, ao_terminar, ao_cancelar
        self.n = segundos
        w = self.w = ctk.CTkToplevel(root, fg_color="#120F1C")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.92)
        lado = 200
        x = (w.winfo_screenwidth() - lado) // 2
        y = (w.winfo_screenheight() - lado) // 2
        w.geometry(f"{lado}x{lado}+{x}+{y}")
        self.num = ctk.CTkLabel(w, text=str(self.n), font=ctk.CTkFont("Segoe UI", 96, "bold"), text_color="#FFFFFF")
        self.num.pack(expand=True, fill="both")
        ctk.CTkLabel(w, text=_("clique para cancelar"), font=ctk.CTkFont("Segoe UI", 11),
                     text_color="#9C95BE").pack(pady=(0, 14))
        for alvo in (w, self.num):
            alvo.bind("<Button-1>", lambda _e: self.cancelar())
        w.after(60, lambda: excluir_da_captura(w))
        w.after(1000, self._passo)

    def _passo(self):
        if not self.w.winfo_exists():
            return
        self.n -= 1
        if self.n <= 0:
            self.w.destroy()
            self.root.after(150, self.ao_terminar)      # um respiro para a janela sumir
            return
        self.num.configure(text=str(self.n))
        self.w.after(1000, self._passo)

    def cancelar(self):
        if self.w.winfo_exists():
            self.w.destroy()
            self.ao_cancelar()


class MiniBarra:
    """Barrinha no alto da tela durante a gravacao: cronometro, pausar e parar.
    Pode ser arrastada. Nao aparece no video."""

    def __init__(self, root, controle):
        import customtkinter as ctk
        self.c = controle
        w = self.w = ctk.CTkToplevel(root, fg_color="#1B1726")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        largura, altura = 270, 44
        w.geometry(f"{largura}x{altura}+{(w.winfo_screenwidth() - largura) // 2}+10")
        f = ctk.CTkFrame(w, fg_color="#1B1726", corner_radius=12, border_width=1, border_color="#3A3354")
        f.pack(fill="both", expand=True)
        self.ponto = ctk.CTkLabel(f, text="●", font=ctk.CTkFont("Segoe UI", 16), text_color="#FF4D4D", width=22)
        self.ponto.pack(side="left", padx=(12, 2))
        self.tempo = ctk.CTkLabel(f, text="00:00", font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color="#FFFFFF",
                                  width=110, anchor="w")
        self.tempo.pack(side="left")
        estilo = dict(width=36, height=30, corner_radius=8, font=ctk.CTkFont("Segoe UI", 14),
                      fg_color="#2A2440", hover_color="#3A3354", text_color="#FFFFFF")
        self.bt_pausa = ctk.CTkButton(f, text="⏸", command=self.c.pausar, **estilo)
        self.bt_pausa.pack(side="left", padx=4)
        ctk.CTkButton(f, text="■", command=self.c.parar, **dict(estilo, fg_color="#C62828",
                                                                  hover_color="#A31F1F")).pack(side="left", padx=(4, 10))
        for alvo in (f, self.tempo, self.ponto):
            alvo.bind("<ButtonPress-1>", self._pegar)
            alvo.bind("<B1-Motion>", self._arrastar)
        w.after(60, lambda: excluir_da_captura(w))
        self._piscar = True
        self._atualizar()

    def _pegar(self, e):
        self._dx, self._dy = e.x_root - self.w.winfo_x(), e.y_root - self.w.winfo_y()

    def _arrastar(self, e):
        self.w.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _atualizar(self):
        if not self.w.winfo_exists() or not self.c.gravando:
            return
        e = self.c.g.estado()
        s = int(e.segundos)
        self.tempo.configure(text=f"{s // 3600:d}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600
                             else f"{s // 60:02d}:{s % 60:02d}  ·  {e.bytes / 1e6:.0f} MB")
        self._piscar = not self._piscar
        self.ponto.configure(text_color=("#FF4D4D" if self._piscar or e.pausado else "#5A2030"),
                             text="⏸" if e.pausado else "●")
        self.bt_pausa.configure(text="▶" if e.pausado else "⏸")
        self.w.after(500, self._atualizar)

    def fechar(self):
        if self.w.winfo_exists():
            self.w.destroy()


class SeletorRegiao:
    """Escurece o monitor; a pessoa arrasta um retangulo. Shift = mantem 16:9.
    Enter/soltar confirma, Esc cancela. ao_escolher((x, y, w, h)) no monitor."""

    def __init__(self, root, monitor, ao_escolher, atual=None):
        import tkinter as tk
        self.m, self.ao_escolher = monitor, ao_escolher
        w = self.w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.45)
        w.geometry(f"{monitor['largura']}x{monitor['altura']}+{monitor['x']}+{monitor['y']}")
        self.cv = tk.Canvas(w, bg="#000000", highlightthickness=0, cursor="crosshair")
        self.cv.pack(fill="both", expand=True)
        self.cv.create_text(monitor["largura"] // 2, 40, fill="#FFFFFF", font=("Segoe UI", 16, "bold"),
                            text=_("Arraste para marcar a área que vai ser gravada"))
        self.cv.create_text(monitor["largura"] // 2, 72, fill="#D8D2F0", font=("Segoe UI", 12),
                            text=_("Shift = proporção 16:9   ·   Enter confirma   ·   Esc cancela"))
        self.ret = self.cv.create_rectangle(0, 0, 0, 0, outline="#7C5CFF", width=3)
        self.rot = self.cv.create_text(0, 0, fill="#FFFFFF", font=("Segoe UI", 12, "bold"), anchor="sw")
        self.ini = None
        self.atual = tuple(atual) if atual and len(atual) == 4 else None
        if self.atual:
            self._desenhar(*self.atual)
        self.cv.bind("<ButtonPress-1>", self._pegar)
        self.cv.bind("<B1-Motion>", self._mover)
        self.cv.bind("<ButtonRelease-1>", lambda _e: self.confirmar())
        w.bind("<Escape>", lambda _e: self.w.destroy())
        w.bind("<Return>", lambda _e: self.confirmar())
        w.after(50, lambda: (w.focus_force(), excluir_da_captura(w)))

    def _pegar(self, e):
        self.ini = (e.x, e.y)

    def _mover(self, e):
        if not self.ini:
            return
        x0, y0 = self.ini
        w, h = e.x - x0, e.y - y0
        if e.state & 0x0001:                      # Shift: 16:9
            h = int(abs(w) * 9 / 16) * (1 if h >= 0 else -1)
        x, y = min(x0, x0 + w), min(y0, y0 + h)
        self.atual = (max(0, x), max(0, y), abs(w), abs(h))
        self._desenhar(*self.atual)

    def _desenhar(self, x, y, w, h):
        self.cv.coords(self.ret, x, y, x + w, y + h)
        self.cv.coords(self.rot, x + 4, y - 6 if y > 30 else y + h + 22)
        self.cv.itemconfigure(self.rot, text=f"{w} × {h}")

    def confirmar(self):
        if self.atual and self.atual[2] >= 64 and self.atual[3] >= 64:
            x, y, w, h = self.atual
            w, h = min(w, self.m["largura"] - x) & ~1, min(h, self.m["altura"] - y) & ~1
            self.w.destroy()
            self.ao_escolher([int(x), int(y), int(w), int(h)])
        elif self.ini is None:
            self.w.destroy()


# ---------------------------------------------------------------- controle
class Controle:
    def __init__(self, root, motor, cfg, toast, janelas=lambda: []):
        self.root, self.motor, self.cfg, self.toast = root, motor, cfg, toast
        self.janelas = janelas          # outras janelas do app para esconder da gravacao
        self.g = None
        self.audio = None
        self.arquivo = ""
        self.ultimo_arquivo = ""
        self.contagem = None
        self.barra = None
        self._minimizou = False
        self.ao_mudar = []              # callbacks (botoes, bandeja...)
        self.ao_terminar = []           # callbacks(arquivo) quando um video e salvo

    @property
    def gravando(self):
        return self.g is not None

    @property
    def contando(self):
        return self.contagem is not None

    def pasta(self):
        """Pasta escolhida (ou Videos\\OpenBokeh). Veja pasta_gravavel()."""
        return self.cfg["grav_pasta"] or G.pasta_padrao()

    def pasta_gravavel(self):
        """(pasta, bloqueada). Se o Windows bloquear a pasta escolhida ("Acesso controlado a
        pastas", protecao contra ransomware que vale para Videos/Documentos/Imagens), grava
        numa pasta liberada dentro do perfil do usuario."""
        p = self.pasta()
        if _gravavel(p):
            return p, False
        alt = os.path.join(os.path.expanduser("~"), _("Gravações OpenBokeh"))
        return (alt, True) if _gravavel(alt) else (p, True)

    # -------- janelas fora do video
    def _ocultar(self, sim):
        for w in [self.root] + list(self.janelas()):
            try:
                if w is not None and w.winfo_exists():
                    excluir_da_captura(w, sim)
            except Exception:
                pass

    # -------- iniciar / parar
    def alternar(self):
        if self.gravando:
            self.parar()
        elif self.contando:
            self.contagem.cancelar()
        else:
            self.iniciar_com_contagem()

    def iniciar_com_contagem(self):
        if self.gravando or self.contando:
            return
        if not self._pode_comecar():
            return
        n = int(self.cfg.get("grav_contagem", 3))
        if n <= 0:
            self._comecar()
            return

        def fim():
            self.contagem = None
            self._comecar()

        def cancelou():
            self.contagem = None
            self.toast(_("Gravação cancelada"))
            self._avisar()
        self.contagem = Contagem(self.root, n, fim, cancelou)
        self._avisar()

    def _pode_comecar(self):
        if not G.disponivel():
            self.toast(_("Gravação indisponível nesta instalação"))
            return False
        pasta, _b = self.pasta_gravavel()
        livre = _livre(pasta)
        if livre is not None and livre < MIN_LIVRE_INICIAR:
            self.toast(_("Pouco espaço em disco ({gb} GB livres). Libere espaço ou escolha outra pasta.")
                       .format(gb=f"{livre / 1024 ** 3:.1f}"))
            return False
        return True

    def _comecar(self):
        if self.cfg["grav_minimizar"] and self.root.state() in ("normal", "zoomed"):
            self.root.iconify()
            self._minimizou = True
        self.iniciar()
        if not self.gravando and self._minimizou:
            self.root.deiconify()
            self._minimizou = False

    def iniciar(self):
        if self.gravando:
            return
        if not self._pode_comecar():
            return
        pasta, bloqueada = self.pasta_gravavel()
        self.ultima_pasta = pasta
        if bloqueada:
            print(f"[aviso] pasta {self.pasta()} bloqueada pelo Windows; gravando em {pasta}")
        _m, _r, _h, problema = fonte_atual(self.cfg)
        if problema:
            self.toast(problema)
            return
        try:
            self.arquivo = G.nome_arquivo(pasta)
            op = opcoes(self.cfg)
            g = G.Gravacao(op, self.arquivo)
            g.iniciar()
        except Exception as e:
            self.toast(_("Não foi possível gravar: {erro}").format(erro=str(e)[:90]))
            print(f"[erro] gravacao: {e}")
            return
        self.g = g
        if self.cfg["grav_mic"] or self.cfg["grav_som_pc"]:
            self.audio = G.MisturadorAudio(
                g, mic=self.cfg["grav_mic"], mic_nome=self.cfg.get("grav_mic_entrada", ""),
                sem_ruido=self.cfg["grav_mic_sem_ruido"], intensidade=self.cfg.get("microfone_intensidade", 100) / 100,
                som_pc=self.cfg["grav_som_pc"],
                ganho_db=MIC.ganho_de(self.cfg, self.cfg.get("grav_mic_entrada", "")),
                volume_automatico=bool(self.cfg.get("volume_automatico", True)))
            self.audio.iniciar()
            if self.audio.erro:
                print(f"[aviso] audio da gravacao: {self.audio.erro}")
        self.motor.gravacao = g
        if self.cfg["grav_ocultar_app"]:
            self._ocultar(True)
        try:
            self.barra = MiniBarra(self.root, self)
        except Exception as e:
            print(f"[aviso] mini barra: {e}")
        e = g.estado()
        print(f"Gravacao: {self.arquivo} | {g.saida[0]}x{g.saida[1]} | 1:1={g.texto_1x1} | "
              f"{e.codificador} hw={e.hardware} qualidade={e.modoQualidade} frag={e.fragmentado}")
        if bloqueada:
            self.toast(_("O Windows protege a pasta escolhida (acesso controlado a pastas). Gravando em: {pasta}")
                       .format(pasta=pasta))
        self.root.after(5000, self._vigiar_disco)
        self._janela, self._ret_janela = op.get("hwnd"), None
        if self._janela:
            self.root.after(150, self._seguir_janela)
        self._avisar()

    def _seguir_janela(self):
        """Modo janela: a area acompanha a janela (mover, redimensionar). Minimizada ou
        fechada, fica a ultima area."""
        if not self.gravando or not self._janela:
            return
        ret = CAP.retangulo(self._janela)
        if ret and ret != self._ret_janela:
            self._ret_janela = ret
            reg = CAP.no_monitor(ret, self.g.monitor)
            if reg:
                self.g.atualizar(regiao=reg)
        self.root.after(150, self._seguir_janela)

    def _vigiar_disco(self):
        if not self.gravando:
            return
        livre = _livre(os.path.dirname(self.arquivo))
        if livre is not None and livre < MIN_LIVRE_GRAVANDO:
            self.parar()
            self.toast(_("Gravação parada: o disco está quase cheio. O vídeo foi salvo."))
            return
        self.root.after(5000, self._vigiar_disco)

    def pausar(self):
        if self.gravando:
            p = not self.g.estado().pausado
            self.g.pausar(p)
            self._avisar()

    def parar(self):
        if not self.gravando:
            return
        g, self.g = self.g, None
        self.motor.gravacao = None
        if self.barra is not None:
            self.barra.fechar()
            self.barra = None
        if self.audio is not None:
            self.audio.parar()
            self.audio = None
        g.parar()
        e = g.estado()
        self._ocultar(False)
        if e.erro:
            print(f"[aviso] gravacao: {e.erro}")
        tam = os.path.getsize(self.arquivo) / 1e6 if os.path.exists(self.arquivo) else 0
        print(f"Gravacao salva: {self.arquivo} ({tam:.1f} MB, {e.segundos:.0f} s, perdidos {e.perdidos})")
        self.ultimo_arquivo = self.arquivo
        if self._minimizou:
            self._minimizou = False
            self.root.deiconify()
            self.root.lift()
        self.toast(_("Vídeo salvo ({mb} MB)").format(mb=f"{tam:.0f}"))
        for f in self.ao_terminar:
            try:
                f(self.arquivo)
            except Exception:
                pass
        self._avisar()

    def atualizar_layout(self):
        """Opcoes que mudam ao vivo (webcam, fundo, cursor)."""
        if self.gravando:
            o = opcoes(self.cfg)
            self.g.atualizar(**{k: o[k] for k in ("cam_forma", "cam_posicao", "cam_tamanho", "cam_borda",
                                                   "fundo", "cursor", "encaixe")})

    def abrir_pasta(self):
        p = getattr(self, "ultima_pasta", None) or self.pasta_gravavel()[0]
        try:
            os.makedirs(p, exist_ok=True)
            os.startfile(p)
        except OSError:
            self.toast(_("Não foi possível abrir a pasta {pasta}").format(pasta=p))

    def _avisar(self):
        for f in self.ao_mudar:
            try:
                f()
            except Exception:
                pass

    def status(self):
        """Texto curto para o botao: '■ 01:23 · 45 MB' (ou '' se nao grava)."""
        if not self.gravando:
            return ""
        e = self.g.estado()
        s = int(e.segundos)
        txt = f"{s // 60:02d}:{s % 60:02d} · {e.bytes / 1e6:.0f} MB"
        return ("⏸ " if e.pausado else "■ ") + txt

    def encerrar(self):
        if self.contando:
            self.contagem.cancelar()
        self.parar()
