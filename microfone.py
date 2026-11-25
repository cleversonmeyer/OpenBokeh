"""
Microfone sem ruido do OpenBokeh.

Le o microfone, tira o ruido de fundo (ventilador, teclado, rua, ar-condicionado)
com o RNNoise (Xiph, BSD-3: rede neural pequena que roda na CPU com ~1% de uso)
e envia o som limpo para um cabo de audio virtual (VB-CABLE). No Meet/Zoom/
Discord/OBS escolhe-se "CABLE Output" como microfone.

O Windows nao deixa um programa criar um microfone sem um driver assinado,
por isso o cabo virtual e instalado a parte (gratuito, vb-audio.com).

Tudo acontece na memoria, em blocos de 10 ms: nada e gravado nem enviado.
"""

import collections
import ctypes
import os
import sys
import threading
import time

import numpy as np

from i18n import _

TAXA = 48000                 # o RNNoise trabalha a 48 kHz
QUADRO = 480                 # 10 ms por quadro
ESCALA = 32768.0             # o RNNoise espera amostras na escala de 16 bits
NOME_CABO = "CABLE Input"    # entrada do cabo (o lado "Output" e o microfone que os apps veem)
MIC_DO_CABO = "CABLE Output"
URL_CABO = "https://vb-audio.com/Cable/"
MAX_FILA = 6                 # quadros na fila (60 ms): acima disso descarta os mais velhos


def _caminho_dll():
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "rnnoise.dll")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_rnnoise", "build", "rnnoise.dll")


class RNNoise:
    """Um estado do RNNoise (cada fluxo de audio precisa do seu)."""
    _dll = None

    def __init__(self):
        if RNNoise._dll is None:
            d = ctypes.CDLL(_caminho_dll())
            d.rnnoise_create.restype = ctypes.c_void_p
            d.rnnoise_create.argtypes = [ctypes.c_void_p]
            d.rnnoise_destroy.argtypes = [ctypes.c_void_p]
            d.rnnoise_process_frame.restype = ctypes.c_float
            d.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                                ctypes.POINTER(ctypes.c_float)]
            RNNoise._dll = d
        self._st = RNNoise._dll.rnnoise_create(None)
        self._saida = np.zeros(QUADRO, np.float32)
        self._atraso = np.zeros(QUADRO, np.float32)   # o RNNoise devolve o som 1 quadro atrasado

    def processar(self, quadro, intensidade=1.0):
        """quadro: 480 amostras float32 (-1..1). Devolve (limpo, probabilidade de voz)."""
        entrada = np.ascontiguousarray(quadro * ESCALA, np.float32)
        p = ctypes.POINTER(ctypes.c_float)
        voz = RNNoise._dll.rnnoise_process_frame(self._st, self._saida.ctypes.data_as(p), entrada.ctypes.data_as(p))
        limpo = self._saida / ESCALA
        if intensidade < 1.0:
            # mistura com o original alinhado no tempo (senao vira eco metalico)
            limpo = limpo * intensidade + self._atraso * (1.0 - intensidade)
        self._atraso = quadro.copy()
        return np.clip(limpo, -1.0, 1.0).astype(np.float32), voz

    def fechar(self):
        if self._st:
            RNNoise._dll.rnnoise_destroy(self._st)
            self._st = None

    def __del__(self):
        try:
            self.fechar()
        except Exception:
            pass


def disponivel():
    """A biblioteca de audio e o RNNoise estao presentes?"""
    try:
        import importlib.util
        return importlib.util.find_spec("sounddevice") is not None and os.path.exists(_caminho_dll())
    except Exception:
        return False


def _wasapi(sd):
    for i, h in enumerate(sd.query_hostapis()):
        if "WASAPI" in h["name"]:
            return i, h
    return None, None


# ---------------------------------------------------------------- fluxos abertos
# Para enxergar um microfone ligado com o app aberto, a PortAudio precisa ser reiniciada,
# e isso DERRUBA todo fluxo de audio aberto no processo (microfone da gravacao, das
# chamadas, medidor...). Por isso cada fluxo se registra aqui e a lista so e recarregada
# quando nenhum estiver aberto.
_abertos = set()
_trava_pa = threading.Lock()


def registrar(fluxo):
    with _trava_pa:
        _abertos.add(fluxo)


def liberar(fluxo):
    with _trava_pa:
        _abertos.discard(fluxo)


def recarregar_lista(sd):
    """Atualiza a lista de dispositivos se nao houver fluxo aberto. True se recarregou."""
    with _trava_pa:
        if _abertos:
            return False
        try:
            sd._terminate()
            sd._initialize()
            return True
        except Exception:
            return False


def dispositivos(atualizar=True):
    """(microfones, nome do cabo ou None). Usa o WASAPI (menor atraso)."""
    import sounddevice as sd
    if atualizar:
        recarregar_lista(sd)      # microfone/cabo ligado com o app aberto
    api, _h = _wasapi(sd)
    mics, cabo = [], None
    for d in sd.query_devices():
        if d["hostapi"] != api:
            continue
        if d["max_input_channels"] > 0 and MIC_DO_CABO.lower() not in d["name"].lower() \
                and "vb-audio" not in d["name"].lower():
            mics.append(d["name"])
        if d["max_output_channels"] > 0 and NOME_CABO.lower() in d["name"].lower():
            cabo = d["name"]
    return mics, cabo


def cabo_instalado():
    try:
        return dispositivos()[1] is not None
    except Exception:
        return False


def microfone_padrao():
    """Nome do microfone padrao do Windows (ou "")."""
    try:
        import sounddevice as sd
        api, h = _wasapi(sd)
        i = h["default_input_device"] if h else -1
        return sd.query_devices(i)["name"] if i is not None and i >= 0 else ""
    except Exception:
        return ""


def _indice(sd, nome, entrada):
    api, h = _wasapi(sd)
    if not nome:
        return h["default_input_device"] if entrada else h["default_output_device"]
    for i, d in enumerate(sd.query_devices()):
        if d["hostapi"] == api and d["name"] == nome and \
                (d["max_input_channels"] if entrada else d["max_output_channels"]) > 0:
            return i
    return h["default_input_device"] if entrada else None


def criar(cfg):
    """MicrofoneLimpo ja configurado pelo cfg, ou None se o audio nao estiver disponivel."""
    if not disponivel():
        return None
    m = MicrofoneLimpo()
    aplicar(m, cfg)
    return m


def aplicar(m, cfg):
    if m is not None:
        m.configurar(cfg["microfone_limpo"], cfg["microfone_entrada"], cfg["microfone_intensidade"])


class MicrofoneLimpo:
    """Fluxo continuo: microfone -> RNNoise -> cabo virtual.
    Fica de olho e religa sozinho se o microfone for desconectado e voltar."""

    def __init__(self):
        self.ligado = False
        self.erro = ""              # texto amigavel do ultimo problema ("" = tudo certo)
        self.nivel_entrada = 0.0    # 0..1 (para o medidor da interface)
        self.nivel_saida = 0.0
        self.mic = ""
        self.intensidade = 1.0
        self._fluxos = None
        self._fila = collections.deque()
        self._trava = threading.Lock()
        self._vigia = None
        self._resto = np.zeros(0, np.float32)

    # -------- controle
    def configurar(self, ligado, mic="", intensidade=100):
        self.intensidade = max(0, min(100, intensidade)) / 100.0
        mudou_mic = mic != self.mic
        self.mic = mic
        if ligado and (not self.ligado or mudou_mic):
            self.ligado = True
            self._reiniciar()
            if self._vigia is None:
                self._vigia = threading.Thread(target=self._vigiar, daemon=True, name="microfone")
                self._vigia.start()
        elif not ligado and self.ligado:
            self.ligado = False
            self._parar()
            self.erro = ""

    def encerrar(self):
        self.ligado = False
        self._parar()

    @property
    def rodando(self):
        return self._fluxos is not None and all(f.active for f in self._fluxos)

    # -------- fluxo de audio
    def _parar(self):
        with self._trava:
            fl, self._fluxos = self._fluxos, None
        for f in fl or ():
            try:
                f.stop()
                f.close()
            except Exception:
                pass
            liberar(f)
        self.nivel_entrada = self.nivel_saida = 0.0

    def _reiniciar(self):
        self._parar()
        if not self.ligado:
            return
        try:
            import sounddevice as sd
            _mics, cabo = dispositivos()          # (so recarrega se nada estiver aberto)
            if cabo is None:
                self.erro = _("Cabo de áudio virtual não encontrado. Instale o VB-CABLE (gratuito) e reinicie o computador.")
                return
            i_mic = _indice(sd, self.mic, True)
            i_cabo = _indice(sd, cabo, False)
            if i_mic is None or i_mic < 0:
                self.erro = _("Nenhum microfone encontrado.")
                return
            self._rn = RNNoise()
            self._fila.clear()
            self._resto = np.zeros(0, np.float32)
            extra = sd.WasapiSettings(auto_convert=True)
            ent = sd.InputStream(device=i_mic, samplerate=TAXA, channels=1, dtype="float32", blocksize=QUADRO,
                                 latency="low", extra_settings=extra, callback=self._ao_capturar)
            sai = sd.OutputStream(device=i_cabo, samplerate=TAXA, channels=1, dtype="float32", blocksize=QUADRO,
                                  latency="low", extra_settings=extra, callback=self._ao_tocar)
            ent.start()
            sai.start()
            registrar(ent)
            registrar(sai)
            with self._trava:
                self._fluxos = (ent, sai)
            self.erro = ""
        except Exception as e:
            self._parar()
            self.erro = _("Não foi possível abrir o microfone. Confira se ele está conectado e se o Windows "
                          "permite o acesso (Configurações › Privacidade › Microfone). Detalhe: {erro}"
                          ).format(erro=str(e)[:100])

    def _ao_capturar(self, dados, n, _tempo, _status):
        x = np.concatenate((self._resto, dados[:, 0]))
        i = 0
        while len(x) - i >= QUADRO:
            q = x[i:i + QUADRO]
            limpo, _voz = self._rn.processar(q, self.intensidade)
            self._fila.append(limpo)
            i += QUADRO
        self._resto = x[i:].copy()
        while len(self._fila) > MAX_FILA:
            self._fila.popleft()
        pico = float(np.abs(dados).max()) if n else 0.0
        self.nivel_entrada = max(pico, self.nivel_entrada * 0.85)

    def _ao_tocar(self, saida, n, _tempo, _status):
        pos = 0
        while pos < n and self._fila:
            q = self._fila[0]
            k = min(len(q), n - pos)
            saida[pos:pos + k, 0] = q[:k]
            if k < len(q):
                self._fila[0] = q[k:]
            else:
                self._fila.popleft()
            pos += k
        if pos < n:
            saida[pos:, 0] = 0.0
        pico = float(np.abs(saida).max()) if n else 0.0
        self.nivel_saida = max(pico, self.nivel_saida * 0.85)

    def _vigiar(self):
        """Religa se o fluxo parou (microfone desconectado, cabo reinstalado...).
        Sem o cabo instalado, confere so a cada 15 s (antes reiniciava a PortAudio a cada 3 s,
        o que derrubava o microfone da gravacao de tela)."""
        espera = 0
        while True:
            time.sleep(3)
            espera -= 3
            if self.ligado and not self.rodando and espera <= 0:
                self._reiniciar()
                espera = 15 if self.erro else 0


class Medidor:
    """Mostra se um microfone esta captando (nivel 0..1), sem gravar nada."""

    def __init__(self):
        self.nivel = 0.0
        self.nome = None
        self.erro = ""
        self._f = None

    def iniciar(self, nome=""):
        if self._f is not None and nome == self.nome:
            return
        self.parar()
        self.nome = nome
        try:
            import sounddevice as sd
            idx = _indice(sd, nome, True)
            f = sd.InputStream(device=idx, samplerate=TAXA, channels=1, dtype="float32", blocksize=960,
                               extra_settings=sd.WasapiSettings(auto_convert=True), callback=self._cb)
            f.start()
            registrar(f)
            self._f, self.erro = f, ""
        except Exception as e:
            self.erro = str(e)[:100]
            self._f = None

    def _cb(self, dados, n, _t, _s):
        pico = float(np.abs(dados).max()) if n else 0.0
        self.nivel = max(pico, self.nivel * 0.8)

    def parar(self):
        f, self._f = self._f, None
        if f is not None:
            try:
                f.stop()
                f.close()
            except Exception:
                pass
            liberar(f)
        self.nivel = 0.0


def testar(mic="", segundos=4, ao_terminar=None, ao_mudar=None):
    """Grava alguns segundos e toca nos alto-falantes/fones: primeiro como
    estava, depois sem ruido. Roda numa thread; ao_mudar(etapa) informa
    "gravando" | "original" | "limpo"; ao_terminar(erro ou None)."""
    def rodar():
        try:
            import sounddevice as sd
            i_mic = _indice(sd, mic, True)
            extra = sd.WasapiSettings(auto_convert=True)
            ao_mudar and ao_mudar("gravando")
            bruto = sd.rec(int(segundos * TAXA), samplerate=TAXA, channels=1, dtype="float32", device=i_mic,
                           extra_settings=extra, blocking=True)[:, 0]
            rn = RNNoise()
            n = len(bruto) // QUADRO * QUADRO
            limpo = np.concatenate([rn.processar(bruto[i:i + QUADRO])[0] for i in range(0, n, QUADRO)])
            rn.fechar()
            saida = _indice(sd, "", False)
            ao_mudar and ao_mudar("original")
            sd.play(bruto[:n], TAXA, device=saida, extra_settings=extra, blocking=True)
            time.sleep(0.3)
            ao_mudar and ao_mudar("limpo")
            sd.play(limpo, TAXA, device=saida, extra_settings=extra, blocking=True)
            ao_terminar and ao_terminar(None)
        except Exception as e:
            ao_terminar and ao_terminar(str(e)[:120])
    threading.Thread(target=rodar, daemon=True, name="teste-microfone").start()
