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
_donos = set()              # MicrofoneLimpo ligados: pausam e voltam num recarregamento forcado
_trava_pa = threading.RLock()   # toda troca na PortAudio passa por aqui


def registrar(fluxo):
    with _trava_pa:
        _abertos.add(fluxo)


def liberar(fluxo):
    with _trava_pa:
        _abertos.discard(fluxo)


def recarregar_lista(sd, forcar=False):
    """Atualiza a lista de dispositivos. Sem forcar, so se nenhum fluxo estiver aberto.
    Forcando, o microfone das chamadas pausa um instante e volta (quem chama garante que
    nao ha gravacao em andamento). True se recarregou."""
    donos = []
    with _trava_pa:
        if _abertos and not forcar:
            return False
        donos = [d for d in _donos if d.ligado]
    for d in donos:
        d._parar()
    with _trava_pa:
        ok = False
        if not _abertos:
            try:
                sd._terminate()
                sd._initialize()
                ok = True
            except Exception:
                ok = False
    for d in donos:
        d._reiniciar()
    return ok


# ---------------------------------------------------------------- microfone ligado/desligado
def assinatura_dispositivos():
    """Microfones ativos agora + qual e o padrao (API de audio do Windows): serve para
    perceber quando um microfone e conectado, tirado ou trocado como padrao."""
    try:
        return tuple(sorted((n, p) for _i, n, p in microfones_windows()))
    except Exception:
        return ()


def _assinatura_winmm():
    """(reserva, sem uso) lista do winmm: em processo sem janela ela nao se atualiza."""
    class CAPS(ctypes.Structure):
        _fields_ = [("wMid", ctypes.c_ushort), ("wPid", ctypes.c_ushort), ("vDriverVersion", ctypes.c_uint),
                    ("szPname", ctypes.c_wchar * 32), ("dwFormats", ctypes.c_uint), ("wChannels", ctypes.c_ushort),
                    ("wReserved1", ctypes.c_ushort)]
    try:
        w = ctypes.windll.winmm
        nomes = []
        for i in range(w.waveInGetNumDevs()):
            c = CAPS()
            if w.waveInGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0:
                nomes.append(c.szPname)
        return tuple(sorted(nomes))
    except Exception:
        return ()


class VigiaDispositivos:
    """Confere a cada 2 s se a lista de microfones mudou e avisa (ao_mudar() roda nesta thread)."""

    def __init__(self, ao_mudar):
        self.ao_mudar = ao_mudar
        self._ultima = assinatura_dispositivos()
        self._rodar = True
        threading.Thread(target=self._laco, daemon=True, name="vigia-microfones").start()

    def _laco(self):
        while self._rodar:
            time.sleep(2)
            atual = assinatura_dispositivos()
            if atual != self._ultima:
                self._ultima = atual
                try:
                    self.ao_mudar()
                except Exception as e:
                    print(f"[aviso] lista de microfones: {e}")

    def parar(self):
        self._rodar = False


# ---------------------------------------------------------------- volume
class AjusteVolume:
    """Ganho do microfone (dB) + volume automatico (nivela a voz) + limitador (nao distorce).
    Processa blocos float32 mono; o ganho muda suave dentro do bloco (sem estalos)."""
    ALVO = 10 ** (-20 / 20)            # nivel medio de fala desejado (-20 dBFS)
    VOZ = 10 ** (-48 / 20)             # abaixo disso e silencio/ruido: nao mexe no ganho automatico
    AUTO_MIN, AUTO_MAX = 10 ** (-12 / 20), 10 ** (20 / 20)

    def __init__(self, ganho_db=0.0, automatico=True):
        self.ganho_db, self.automatico = ganho_db, automatico
        self._auto = 1.0
        self._g_ant = None

    def processar(self, x):
        if len(x) == 0:
            return x
        g = 10 ** (self.ganho_db / 20)
        if self.automatico:
            rms = float(np.sqrt(np.mean((x * g) ** 2)))
            if rms > self.VOZ:
                alvo = min(self.AUTO_MAX, max(self.AUTO_MIN, self.ALVO / rms))
                # sobe devagar (~1 s), desce rapido (~60 ms): nao "bombeia" e nao estoura
                k = 0.012 * len(x) / 480 if alvo > self._auto else 0.15 * len(x) / 480
                self._auto += (alvo - self._auto) * min(1.0, k)
            g *= self._auto
        g_ant = g if self._g_ant is None else self._g_ant
        y = x * np.linspace(g_ant, g, len(x), dtype=np.float32)
        self._g_ant = g
        return limitar(y)


def limitar(y, joelho=0.7):
    """Limitador suave: abaixo do joelho passa igual; acima, curva ate no maximo 1.0."""
    a = np.abs(y)
    acima = a > joelho
    if acima.any():
        y = y.copy()
        y[acima] = np.sign(y[acima]) * (joelho + (1 - joelho) * np.tanh((a[acima] - joelho) / (1 - joelho)))
    return y.astype(np.float32)


class Aquecimento:
    """O RNNoise leva alguns decimos de segundo para aprender o ruido do ambiente; nesse
    comeco a voz pode sair "tremida". Segura o inicio em silencio e entra suave."""

    def __init__(self, silencio=0.30, rampa=0.15):
        self.silencio, self.rampa = int(silencio * TAXA), int(rampa * TAXA)
        self.pos = 0

    def processar(self, x):
        if self.pos >= self.silencio + self.rampa:
            return x
        t = np.arange(self.pos, self.pos + len(x))
        self.pos += len(x)
        f = np.clip((t - self.silencio) / self.rampa, 0, 1).astype(np.float32)
        return x * f


def ganho_de(cfg, nome):
    """Ganho salvo para o microfone (por nome; "" = padrao do Windows)."""
    g = (cfg.get("ganhos_microfone") or {}).get(nome or "", 0)
    return float(g) if isinstance(g, (int, float)) else 0.0


# ---------------------------------------------------------------- microfones pela API do Windows
# A lista e a captura dos microfones vem direto da WASAPI (na DLL do gravador): a lista e
# sempre a atual e um microfone plugado/tirado aparece na hora, sem "religar" nada.
# (Antes a PortAudio precisava ser reiniciada para ver microfone novo, o que podia esvaziar
# a lista ou travar o app dentro do MMDevAPI.dll do Windows.)
_trava_dll_mic = threading.RLock()


def _dll_mic():
    import gravador
    d = gravador.dll()
    if not getattr(d, "_mic_ok", False):
        d.GrMicListar.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        d.GrMicAbrir.argtypes = [ctypes.c_wchar_p]
        d.GrMicLer.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        d.GrMicEstado.argtypes = [ctypes.c_int]
        d.GrMicFechar.argtypes = [ctypes.c_int]
        d._mic_ok = True
    return d


def microfones_windows():
    """[(id, nome, padrao)] dos microfones ativos agora."""
    try:
        buf = ctypes.create_unicode_buffer(16384)
        with _trava_dll_mic:
            _dll_mic().GrMicListar(buf, 16384)
    except Exception as e:
        print(f"[aviso] lista de microfones: {e}")
        return []
    lista = []
    for linha in buf.value.splitlines():
        if "|" not in linha:
            continue
        ident, nome = linha.split("|", 1)
        lista.append((ident.lstrip("*"), nome, ident.startswith("*")))
    return lista


def _id_mic(nome):
    """id do microfone pelo nome; "" (padrao do Windows) se o nome nao existir mais."""
    if not nome:
        return ""
    return next((i for i, n, _p in microfones_windows() if n == nome), "")


def dispositivos(atualizar=True):
    """(microfones, nome do cabo ou None). Os microfones vem da API do Windows (sempre atual);
    o cabo virtual (saida), da PortAudio."""
    mics = [n for _i, n, _p in microfones_windows()
            if MIC_DO_CABO.lower() not in n.lower() and "vb-audio" not in n.lower()]
    cabo = None
    try:
        import sounddevice as sd
        api, _h = _wasapi(sd)
        for d in sd.query_devices():
            if d["hostapi"] == api and d["max_output_channels"] > 0 and NOME_CABO.lower() in d["name"].lower():
                cabo = d["name"]
    except Exception:
        pass
    return mics, cabo


class CapturaMic:
    """Captura de um microfone pela WASAPI (DLL). Imita o fluxo da sounddevice:
    start/stop/close/active, e chama callback(dados[n,1], n, None, None) em blocos."""

    def __init__(self, nome, callback, bloco=QUADRO):
        self.nome, self.callback, self.bloco = nome, callback, bloco
        self.h = -1
        self._rodar = False
        self._t = None

    def start(self):
        d = _dll_mic()
        ident = _id_mic(self.nome)          # (fora da trava: consulta a lista)
        with _trava_dll_mic:
            self.h = d.GrMicAbrir(ident)
        if self.h < 0 or d.GrMicEstado(self.h) != 0:
            self.close()
            raise RuntimeError(_("o microfone não abriu (desconectado ou em uso exclusivo)"))
        self._rodar = True
        self._t = threading.Thread(target=self._laco, daemon=True, name="captura-microfone")
        self._t.start()

    def _laco(self):
        d = _dll_mic()
        buf = np.zeros(9600, np.float32)
        resto = np.zeros(0, np.float32)
        while self._rodar:
            time.sleep(0.005)
            n = d.GrMicLer(self.h, buf.ctypes.data, len(buf))
            if not n:
                continue
            x = np.concatenate((resto, buf[:n]))
            k = len(x) // self.bloco * self.bloco
            for i in range(0, k, self.bloco):
                try:
                    self.callback(x[i:i + self.bloco].reshape(-1, 1), self.bloco, None, None)
                except Exception as e:
                    print(f"[aviso] captura do microfone: {e}")
            resto = x[k:].copy()

    @property
    def active(self):
        return self._rodar and self.h >= 0 and _dll_mic().GrMicEstado(self.h) == 0

    def stop(self):
        self._rodar = False
        if self._t is not None:
            self._t.join(timeout=1)
            self._t = None

    def close(self):
        self.stop()
        if self.h >= 0:
            with _trava_dll_mic:
                _dll_mic().GrMicFechar(self.h)
            self.h = -1


def cabo_instalado():
    try:
        return dispositivos()[1] is not None
    except Exception:
        return False


def microfone_padrao():
    """Nome do microfone padrao do Windows (ou "")."""
    return next((n for _i, n, p in microfones_windows() if p), "")


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
        m.volume.ganho_db = ganho_de(cfg, cfg["microfone_entrada"])
        m.volume.automatico = bool(cfg.get("volume_automatico", True))
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
        self.volume = AjusteVolume()
        self._aquecer = Aquecimento()

    # -------- controle
    def configurar(self, ligado, mic="", intensidade=100):
        self.intensidade = max(0, min(100, intensidade)) / 100.0
        mudou_mic = mic != self.mic
        self.mic = mic
        if ligado and (not self.ligado or mudou_mic):
            self.ligado = True
            with _trava_pa:
                _donos.add(self)
            self._reiniciar()
            if self._vigia is None:
                self._vigia = threading.Thread(target=self._vigiar, daemon=True, name="microfone")
                self._vigia.start()
        elif not ligado and self.ligado:
            self.ligado = False
            with _trava_pa:
                _donos.discard(self)
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
            _mics, cabo = dispositivos(atualizar=False)   # nao religa a PortAudio por conta propria
            if cabo is None:
                self.erro = _("Cabo de áudio virtual não encontrado. Instale o VB-CABLE (gratuito) e reinicie o computador.")
                return
            i_cabo = _indice(sd, cabo, False)
            if not microfones_windows():
                self.erro = _("Nenhum microfone encontrado.")
                return
            self._rn = RNNoise()
            self._aquecer = Aquecimento()
            self._fila.clear()
            self._resto = np.zeros(0, np.float32)
            extra = sd.WasapiSettings(auto_convert=True)
            ent = CapturaMic(self.mic, self._ao_capturar)
            sai = sd.OutputStream(device=i_cabo, samplerate=TAXA, channels=1, dtype="float32", blocksize=QUADRO,
                                  latency="low", extra_settings=extra, callback=self._ao_tocar)
            ent.start()
            sai.start()
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
            self._fila.append(self.volume.processar(self._aquecer.processar(limpo)))
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
        self.estourou = 0.0      # momento (time.time) da ultima vez que passou do limite
        self.nome = None
        self.erro = ""
        self._f = None
        self.volume = AjusteVolume()

    def iniciar(self, nome=""):
        if self._f is not None and nome == self.nome:
            return
        with _trava_pa:
            self._iniciar(nome)

    def _iniciar(self, nome):
        self.parar()
        self.nome = nome
        try:
            f = CapturaMic(nome, self._cb, bloco=960)
            f.start()
            self._f, self.erro = f, ""
        except Exception as e:
            self.erro = str(e)[:100]
            self._f = None

    def _cb(self, dados, n, _t, _s):
        bruto = dados[:, 0]
        if n and float(np.abs(bruto).max()) > 0.98:       # o proprio microfone ja chega estourado
            self.estourou = time.time()
        y = self.volume.processar(bruto.copy())
        pico = float(np.abs(y).max()) if n else 0.0
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
            extra = sd.WasapiSettings(auto_convert=True)
            ao_mudar and ao_mudar("gravando")
            partes = []
            cap = CapturaMic(mic, lambda dados, n, _t, _s: partes.append(dados[:, 0].copy()))
            cap.start()
            time.sleep(segundos)
            cap.close()
            bruto = np.concatenate(partes) if partes else np.zeros(QUADRO, np.float32)
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
