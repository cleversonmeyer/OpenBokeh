"""
Gravacao de tela do OpenBokeh (lado Python).

O trabalho pesado fica na DLL nativa (gravador/OpenBokehGravador.cpp): captura da tela,
composicao com a webcam, conversao de cor e codificacao, tudo na placa de video.
Aqui ficam: escolha do formato, calculo do layout (regra do texto 1:1), presets de
qualidade e a ponte com a webcam e o audio.
"""

import ctypes
import os
import sys
import threading
import time
from ctypes import c_int, c_int64, c_uint, c_double, c_wchar

import numpy as np

# ---------------------------------------------------------------- formatos e presets
SAIDAS = {                      # nome -> (largura, altura); "nativa" = tamanho do monitor
    "nativa": None,
    "1440p": (2560, 1440),
    "1080p": (1920, 1080),
}
ENCAIXES = ("inteira", "preencher", "recorte")   # com faixas | sem faixas (corta) | tamanho real 1:1

# qualidade = AVEncCommonQuality (0..100, maior = melhor); bpp = bits por pixel do VBR reserva
PRESETS = {
    "edicao":   {"codec": 0, "qualidade": 85, "bpp": 0.10, "gop": 1},   # H.264, abre leve em editores
    "alta":     {"codec": 1, "qualidade": 75, "bpp": 0.05, "gop": 2},   # HEVC, padrao
    "compacta": {"codec": 1, "qualidade": 62, "bpp": 0.025, "gop": 2},  # HEVC menor
}
FORMAS_CAM = {"nenhuma": 0, "circulo": 1, "arredondado": 2, "pessoa": 3, "retangulo": 4}


class Config(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("monitor", c_int), ("saidaW", c_int), ("saidaH", c_int), ("fps", c_int),
        ("codec", c_int), ("qualidade", c_int), ("bitrateKbps", c_int), ("gopSegundos", c_int),
        ("cursor", c_int),
        ("areaX", c_int), ("areaY", c_int), ("areaW", c_int), ("areaH", c_int),
        ("telaX", c_int), ("telaY", c_int), ("telaW", c_int), ("telaH", c_int),
        ("fundo", c_int), ("corFundo", c_uint),
        ("camForma", c_int), ("camX", c_int), ("camY", c_int), ("camW", c_int), ("camH", c_int),
        ("camBorda", c_int), ("camCorBorda", c_uint),
        ("audio", c_int),
        ("arquivo", c_wchar * 520),
    ]


class Estado(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("gravando", c_int), ("pausado", c_int),
        ("quadros", c_int64), ("perdidos", c_int64),
        ("segundos", c_double), ("bytes", c_int64),
        ("hardware", c_int), ("modoQualidade", c_int), ("fragmentado", c_int),
        ("codificador", c_wchar * 128), ("erro", c_wchar * 256),
    ]


def _caminho_dll():
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "OpenBokehGravador.dll")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "gravador", "build", "OpenBokehGravador.dll")


_dll = None


def dll():
    global _dll
    if _dll is None:
        d = ctypes.CDLL(_caminho_dll())
        d.GrListarMonitores.argtypes = [ctypes.c_wchar_p, c_int]
        d.GrIniciar.argtypes = [ctypes.POINTER(Config)]
        d.GrAtualizar.argtypes = [ctypes.POINTER(Config)]
        d.GrQuadroWebcam.argtypes = [ctypes.c_void_p, c_int, c_int]
        d.GrAudio.argtypes = [ctypes.c_void_p, c_int]
        d.GrPausar.argtypes = [c_int]
        d.GrEstado.argtypes = [ctypes.POINTER(Estado)]
        d.GrSomLer.argtypes = [ctypes.c_void_p, c_int]
        d.GrSomErro.restype = ctypes.c_wchar_p
        _dll = d
    return _dll


def disponivel():
    return os.path.exists(_caminho_dll())


def monitores():
    """[{indice, nome, x, y, largura, altura, principal}]"""
    buf = ctypes.create_unicode_buffer(4096)
    n = dll().GrListarMonitores(buf, 4096)
    lista = []
    for i, linha in enumerate(buf.value.strip().splitlines()[:n]):
        nome, x, y, w, h = linha.split("|")
        lista.append({"indice": i, "nome": nome.replace("\\\\.\\", ""), "x": int(x), "y": int(y),
                      "largura": int(w), "altura": int(h), "principal": int(x) == 0 and int(y) == 0})
    return lista


# ---------------------------------------------------------------- layout
def tamanho_saida(nome, tela_w, tela_h):
    t = SAIDAS.get(nome)
    w, h = t if t else (tela_w, tela_h)
    return w & ~1, h & ~1


def layout_tela(tela_w, tela_h, saida_w, saida_h, encaixe="inteira", area=None):
    """Como a area capturada entra no video. Devolve (area, destino, escala):
    area = (x, y, w, h) usada da tela; destino = (x, y, w, h) no video; escala = px da tela
    por px do video (1 = 1:1, nitido; >1 = reduzida; <1 = ampliada).
      inteira   - a area toda, o maior possivel, com faixas onde sobrar. A tela inteira nunca
                  e ampliada (se cabe, entra em 1:1, a regra de nitidez).
      preencher - ocupa o video todo, sem faixas, cortando as bordas que sobrarem.
      recorte   - tamanho real (1:1): o centro da area, sem redimensionar.
    """
    ax, ay, aw, ah = area if area else (0, 0, tela_w, tela_h)
    ax, ay = max(0, min(tela_w - 16, int(ax))), max(0, min(tela_h - 16, int(ay)))
    aw, ah = max(16, min(tela_w - ax, int(aw))), max(16, min(tela_h - ay, int(ah)))
    tela_toda = (aw, ah) == (tela_w, tela_h)
    if encaixe == "recorte":
        w, h = min(saida_w, aw), min(saida_h, ah)
        x, y = ax + (aw - w) // 2, ay + (ah - h) // 2
        return (x, y, w, h), ((saida_w - w) // 2, (saida_h - h) // 2, w, h), 1.0
    if encaixe == "preencher":
        s = max(saida_w / aw, saida_h / ah)
        w, h = min(aw, int(round(saida_w / s))), min(ah, int(round(saida_h / s)))
        x, y = ax + (aw - w) // 2, ay + (ah - h) // 2
        if (w, h) == (saida_w, saida_h):
            return (x, y, w, h), (0, 0, saida_w, saida_h), 1.0
        return (x, y, w, h), (0, 0, saida_w, saida_h), w / saida_w
    s = min(saida_w / aw, saida_h / ah)
    if tela_toda:
        s = min(s, 1.0)
    if abs(s - 1.0) < 1e-6:
        w, h = aw, ah
    else:
        w, h = int(round(aw * s)) & ~1, int(round(ah * s)) & ~1
    return (ax, ay, aw, ah), ((saida_w - w) // 2, (saida_h - h) // 2, w, h), aw / w


def layout_webcam(saida_w, saida_h, forma="circulo", posicao="inferior_direito", tamanho=22, margem=3,
                  proporcao=16 / 9):
    """Retangulo da webcam no video. tamanho e margem em % da altura do video."""
    h = int(saida_h * tamanho / 100)
    w = h if forma == "circulo" else int(h * proporcao)
    m = int(saida_h * margem / 100)
    x = m if "esquerd" in posicao else saida_w - w - m
    y = m if "superior" in posicao else saida_h - h - m
    return x, y, w, h


def bitrate_kbps(preset, w, h, fps):
    return max(2000, int(w * h * fps * PRESETS[preset]["bpp"] / 1000))


def _cor(rgb):
    r, g, b = rgb
    return (int(r) << 16) | (int(g) << 8) | int(b)


# ---------------------------------------------------------------- gravacao
class Gravacao:
    """Uma gravacao. opcoes (dict):
    monitor, saida ("nativa" | "1440p" | "1080p"), encaixe, area, fps, preset, cursor,
    fundo ("desfocado" | "cor"), cor_fundo, cam_forma, cam_posicao, cam_tamanho, cam_borda, audio."""

    def __init__(self, opcoes, arquivo):
        self.op = dict(opcoes)
        self.arquivo = arquivo
        mons = monitores()
        if not mons:
            raise RuntimeError("nenhum monitor")
        m = next((x for x in mons if x["indice"] == self.op.get("monitor", 0)), mons[0])
        self.monitores = mons
        self.monitor = m
        self.saida = tamanho_saida(self.op.get("saida", "nativa"), m["largura"], m["altura"])
        self.cfg = Config()
        self._montar()

    def _montar(self):
        op, m, c = self.op, self.monitor, self.cfg
        sw, sh = self.saida
        preset = op.get("preset", "alta")
        p = PRESETS[preset]
        fps = int(op.get("fps", 60))
        c.monitor = m["indice"]
        c.saidaW, c.saidaH, c.fps = sw, sh, fps
        c.codec, c.qualidade, c.gopSegundos = p["codec"], int(op.get("qualidade", p["qualidade"])), p["gop"]
        c.bitrateKbps = bitrate_kbps(preset, sw, sh, fps)
        c.cursor = 1 if op.get("cursor", True) else 0
        area, dest, self.escala = layout_tela(m["largura"], m["altura"], sw, sh, op.get("encaixe", "inteira"),
                                              op.get("regiao"))
        c.areaX, c.areaY, c.areaW, c.areaH = area
        c.telaX, c.telaY, c.telaW, c.telaH = dest
        c.fundo = 1 if op.get("fundo", "desfocado") == "desfocado" else 0
        c.corFundo = _cor(op.get("cor_fundo", (18, 16, 28)))
        forma = op.get("cam_forma", "nenhuma")
        c.camForma = FORMAS_CAM.get(forma, 0)
        if c.camForma:
            c.camX, c.camY, c.camW, c.camH = layout_webcam(sw, sh, forma, op.get("cam_posicao", "inferior_direito"),
                                                           op.get("cam_tamanho", 22))
        c.camBorda = int(op.get("cam_borda", 0) * sh / 1080)
        c.camCorBorda = _cor(op.get("cam_cor_borda", (255, 255, 255)))
        c.audio = 1 if op.get("audio", False) else 0
        c.arquivo = self.arquivo

    @property
    def usa_webcam(self):
        return self.cfg.camForma != 0

    @property
    def texto_1x1(self):
        """True se o texto da tela sai sem redimensionar (nitidez maxima)."""
        return abs(self.escala - 1.0) < 1e-3

    def iniciar(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.arquivo)), exist_ok=True)
        r = dll().GrIniciar(ctypes.byref(self.cfg))
        if r != 0:
            raise RuntimeError(f"{self.estado().erro or 'falha ao iniciar'} (0x{r & 0xFFFFFFFF:08X})")

    def atualizar(self, **mudancas):
        """Muda layout/webcam durante a gravacao."""
        self.op.update(mudancas)
        self._montar()
        dll().GrAtualizar(ctypes.byref(self.cfg))

    def webcam(self, rgb, alpha=None):
        """rgb: HxWx3 uint8; alpha: HxW float 0..1 (recorte da IA) ou None."""
        h, w = rgb.shape[:2]
        rgba = np.empty((h, w, 4), np.uint8)
        rgba[..., :3] = rgb
        rgba[..., 3] = 255 if alpha is None else np.clip(alpha * 255, 0, 255).astype(np.uint8)
        dll().GrQuadroWebcam(rgba.ctypes.data, w, h)

    def audio(self, pcm_estereo_int16):
        a = np.ascontiguousarray(pcm_estereo_int16, np.int16)
        dll().GrAudio(a.ctypes.data, len(a))

    def pausar(self, sim=True):
        dll().GrPausar(1 if sim else 0)

    def parar(self):
        dll().GrParar()

    def estado(self):
        e = Estado()
        dll().GrEstado(ctypes.byref(e))
        return e


# ---------------------------------------------------------------- audio
TAXA = 48000


class _Fila:
    """Fila de amostras (numpy) com retirada de exatamente N (completa com silencio)."""

    def __init__(self, canais):
        self.canais, self.partes, self.qtd = canais, [], 0
        self.trava = threading.Lock()

    def por(self, x):
        with self.trava:
            self.partes.append(x)
            self.qtd += len(x)

    def tirar(self, n, maximo):
        with self.trava:
            while self.qtd - n > maximo and self.partes:     # atrasou demais: descarta o mais velho
                self.qtd -= len(self.partes.pop(0))
            forma = (n,) if self.canais == 1 else (n, self.canais)
            out = np.zeros(forma, np.float32)
            pos = 0
            while pos < n and self.partes:
                p = self.partes[0]
                k = min(len(p), n - pos)
                out[pos:pos + k] = p[:k]
                if k < len(p):
                    self.partes[0] = p[k:]
                else:
                    self.partes.pop(0)
                self.qtd -= k
                pos += k
            return out


class MisturadorAudio:
    """Microfone (com o RNNoise, opcional) + som do computador -> trilha da gravacao.
    O relogio e o do PC: a cada 20 ms entrega exatamente o tempo que passou, completando
    com silencio o que faltar (nada tocando, microfone desligado...)."""

    def __init__(self, gravacao, mic=True, mic_nome="", sem_ruido=True, intensidade=1.0, vol_mic=1.0,
                 som_pc=True, vol_pc=0.8, ganho_db=0.0, volume_automatico=True):
        self.g = gravacao
        self.mic, self.mic_nome, self.sem_ruido, self.intensidade = mic, mic_nome, sem_ruido, intensidade
        self.vol_mic, self.som_pc, self.vol_pc = vol_mic, som_pc, vol_pc
        self.nivel_mic = self.nivel_pc = 0.0
        self.erro = ""
        self._fila_mic = _Fila(1)
        self._resto = np.zeros(0, np.float32)
        self._fluxo = None
        self._rodar = False
        self._rn = None
        self.ganho_db, self.volume_automatico = ganho_db, volume_automatico
        self._volume = None
        self._aquecer = None

    def iniciar(self):
        self._rodar = True
        if self.som_pc and dll().GrSomIniciar() != 0:
            self.erro = dll().GrSomErro() or "som do computador indisponivel"
            self.som_pc = False
        if self.mic:
            try:
                import microfone as MIC
                if self.sem_ruido and MIC.disponivel():
                    self._rn = MIC.RNNoise()
                    self._aquecer = MIC.Aquecimento()       # sem a "tremida" do comeco
                self._volume = MIC.AjusteVolume(self.ganho_db, self.volume_automatico)
                # captura direto pela API de audio do Windows (DLL): aceita microfone plugado na hora
                self._fluxo = MIC.CapturaMic(self.mic_nome, self._ao_capturar)
                self._fluxo.start()
            except Exception as e:
                self.erro = f"microfone: {e}"
                self._fluxo = None
        self._thread = threading.Thread(target=self._misturar, daemon=True, name="audio-gravacao")
        self._thread.start()

    def _ao_capturar(self, dados, n, _t, _s):
        x = dados[:, 0].copy()
        if self._rn is not None:
            x = np.concatenate((self._resto, x))
            k = len(x) // 480 * 480
            limpo = [self._rn.processar(x[i:i + 480], self.intensidade)[0] for i in range(0, k, 480)]
            self._resto = x[k:].copy()
            x = np.concatenate(limpo) if limpo else np.zeros(0, np.float32)
            if len(x):
                x = self._aquecer.processar(x)
        if len(x) and self._volume is not None:
            x = self._volume.processar(x)          # volume do microfone + automatico + limitador
        if len(x):
            self._fila_mic.por(x)

    def _misturar(self):
        t0, feitos = time.perf_counter(), 0
        buf = np.zeros((TAXA, 2), np.float32)
        maximo = int(TAXA * 0.15)                     # mais de 150 ms acumulados: descarta
        while self._rodar:
            time.sleep(0.02)
            n = int((time.perf_counter() - t0) * TAXA) - feitos
            if n < 480:
                continue
            n = min(n, TAXA)
            mix = np.zeros((n, 2), np.float32)
            if self._fluxo is not None:
                m = self._fila_mic.tirar(n, maximo) * self.vol_mic
                mix += m[:, None]
                self.nivel_mic = max(float(np.abs(m).max()) if n else 0.0, self.nivel_mic * 0.8)
            if self.som_pc:
                lidos = dll().GrSomLer(buf.ctypes.data, n)
                pc = buf[:lidos] * self.vol_pc
                mix[:lidos] += pc
                self.nivel_pc = max(float(np.abs(pc).max()) if lidos else 0.0, self.nivel_pc * 0.8)
                atraso = dll().GrSomQtd()
                if atraso > maximo:                       # nao deixa acumular atraso
                    dll().GrSomLer(buf.ctypes.data, atraso - maximo // 2)
            np.clip(mix, -1.0, 1.0, out=mix)
            self.g.audio((mix * 32767).astype(np.int16))
            feitos += n

    def parar(self):
        self._rodar = False
        if getattr(self, "_thread", None):
            self._thread.join(timeout=2)
        if self._fluxo is not None:
            try:
                self._fluxo.stop()
                self._fluxo.close()
            except Exception:
                pass
            pass
        if self.som_pc:
            dll().GrSomParar()
        if self._rn is not None:
            self._rn.fechar()


def nome_arquivo(pasta):
    return os.path.join(pasta, time.strftime("OpenBokeh %Y-%m-%d %H-%M-%S.mp4"))


def pasta_padrao():
    try:
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x000E, None, 0, buf)    # CSIDL_MYVIDEO
        base = buf.value or os.path.expanduser("~")
    except Exception:
        base = os.path.expanduser("~")
    return os.path.join(base, "OpenBokeh")
