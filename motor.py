"""
OpenBokeh - motor de processamento (sem interface).

webcam -> IA (Robust Video Matting, DirectML) -> refinamento do recorte
       -> composicao (desfoque / imagem / cor) -> camera virtual
"""

import copy
import json
import os
import sys
import threading
import time
import urllib.request

import cv2
import numpy as np

import efeitos
import mensagens
from i18n import _

PASTA = os.path.dirname(os.path.abspath(__file__))
MODELO_URL = ("https://github.com/PeterL1n/RobustVideoMatting/releases/"
              "download/v1.0.0/rvm_mobilenetv3_{}.onnx")
MODELO_ARQ = os.path.join(PASTA, "modelos", "rvm_mobilenetv3_{}.onnx")
# instalado (empacotado), a pasta do programa e protegida: config vai para %APPDATA%
if getattr(sys, "frozen", False):
    _DADOS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "OpenBokeh")
    os.makedirs(_DADOS, exist_ok=True)
    CONFIG_ARQ = os.path.join(_DADOS, "config.json")
else:
    CONFIG_ARQ = os.path.join(PASTA, "config.json")

# lado menor da imagem que a IA enxerga (o detalhe fino e recuperado depois
# na resolucao cheia pelo proprio modelo)
QUALIDADES = {"leve": 160, "rapido": 216, "equilibrado": 288, "maximo": 432}
# Sem placa de video (IA na CPU), o modelo recebe a imagem reduzida para este
# lado menor e so o recorte e ampliado de volta: a etapa final do modelo roda na
# resolucao da entrada, e em 720p ela pesa muito no processador.
ENTRADA_CPU = 360

AJUSTES_PADRAO = {
    "forca_desfoque": 12,     # 1..40
    "suavidade_borda": 1.0,   # 0..6   desfoque leve so na borda do recorte
    "estabilidade": 50,       # 0..95  memoria entre quadros (menos piscada)
    "firmeza": 20,            # 0..100 limpa transparencias fracas do recorte
    "reducao_ruido": 40,      # 0..100 tira o granulado da webcam no rosto
    "correcao_luz": 30,       # 0..100 clareia/escurece a pessoa ate um brilho bom
    "retoque": 0,             # 0..100 suaviza a pele (so na pessoa)
    "qualidade": "equilibrado",
    "zoom_max": 1.6,          # 1..2.5 enquadramento automatico: zoom maximo
    "velocidade_enquadrar": 4,  # 1..10 rapidez com que a camera acompanha
}

# o que um perfil guarda (troca de "cenario" com um clique)
CHAVES_PERFIL = ["modo", "forca_desfoque", "reducao_ruido", "correcao_luz", "suavidade_borda",
                 "estabilidade", "firmeza", "qualidade", "enquadrar", "zoom_max",
                 "velocidade_enquadrar", "imagem_fundo", "video_fundo", "cor_fundo", "espelhar",
                 "retoque", "redonda", "tamanho_circulo", "cor_fora_circulo", "borda_circulo"]

PERFIS_PADRAO = {
    _("Reunião"): {"modo": "desfoque", "forca_desfoque": 12, "reducao_ruido": 40, "correcao_luz": 30,
                "enquadrar": False},
    _("Ambiente escuro"): {"modo": "desfoque", "forca_desfoque": 14, "reducao_ruido": 70,
                        "correcao_luz": 75, "enquadrar": False},
    _("Apresentação"): {"modo": "desfoque", "forca_desfoque": 18, "reducao_ruido": 40,
                     "correcao_luz": 40, "enquadrar": True, "zoom_max": 1.6},
    _("Chroma verde (OBS)"): {"modo": "cor", "cor_fundo": [0, 255, 0], "reducao_ruido": 40,
                           "correcao_luz": 30, "suavidade_borda": 0.5, "firmeza": 40,
                           "enquadrar": False},
    _("Câmera redonda (OBS)"): {"modo": "desfoque", "redonda": True, "cor_fora_circulo": "verde",
                               "tamanho_circulo": 90, "borda_circulo": 6, "enquadrar": True,
                               "zoom_max": 1.8},
}

from gravacao_ui import PADRAO as _PADRAO_GRAV

CONFIG_PADRAO = {
    "camera": "",             # nome da webcam; vazio = primeira real
    "largura": 1280,
    "altura": 720,
    "fps": 30,
    "modo": "desfoque",       # desfoque | imagem | video | cor | nenhum
    "imagem_fundo": "",
    "video_fundo": "",
    "enquadrar": False,
    "texto_privacidade": _("Volto já"),
    "espera_automatica": True,     # desliga a webcam quando nenhum app usa a camera
    "fechar_para_bandeja": True,   # o X da janela esconde na bandeja em vez de sair
    "aviso_bandeja_mostrado": False,
    "boas_vindas_vistas": False,
    "saida": "720p",               # resolucao da OpenBokeh Camera: 720p | 1080p
    "limite_fps": 30,              # 15 | 24 | 30 (PCs mais fracos)
    "qualidade_automatica": True,  # baixa a qualidade da IA se ficar lento
    "espera_segundos": 5,          # tempo sem uso ate desligar a webcam
    "processador": "auto",         # auto (GPU se houver) | cpu
    "atalho_privacidade": "Ctrl+Alt+B",
    "atalho_efeito": "Ctrl+Alt+N",
    "imagem_privacidade": "",      # imagem propria na tela "Volto ja" (vazio = desfoque)
    "notificacoes": True,          # balaoes do Windows vindos da bandeja
    "modo_anterior": "desfoque",   # para o atalho liga/desliga efeito
    "idioma": "auto",              # auto (idioma do Windows) | pt | en
    "perfis": PERFIS_PADRAO,
    **_PADRAO_GRAV,                # gravacao de tela (gravacao_ui.PADRAO)
    "cor_fundo": [40, 120, 60],   # RGB
    "espelhar": False,
    "redonda": False,              # camera redonda: so um circulo, fora uma cor lisa
    "tamanho_circulo": 90,         # 30..100 % da altura
    "cor_fora_circulo": "verde",   # verde (chroma key no OBS) | preto | branco
    "borda_circulo": 0,            # 0..20 anel branco em volta (px em 720p)
    "microfone_limpo": False,      # microfone sem ruido (RNNoise -> cabo virtual VB-CABLE)
    "microfone_entrada": "",       # nome do microfone; vazio = padrao do Windows
    "microfone_intensidade": 100,  # 50 | 75 | 100
    **AJUSTES_PADRAO,
}

RESOLUCOES = {"720p": (1280, 720), "1080p": (1920, 1080)}

# cameras virtuais nunca devem ser usadas como entrada (faria um loop)
CAMERAS_VIRTUAIS = ("obs virtual", "vcam", "unity video capture",
                    "fundolivre", "openbokeh", "nvidia broadcast", "xsplit")


# ---------------------------------------------------------------- config
def carregar_config():
    cfg = copy.deepcopy(CONFIG_PADRAO)
    if os.path.exists(CONFIG_ARQ):
        try:
            with open(CONFIG_ARQ, encoding="utf-8") as f:
                cfg.update({k: v for k, v in json.load(f).items() if k in CONFIG_PADRAO})
        except Exception as e:
            print(f"[aviso] config.json invalido, usando padrao: {e}")
    return sanear(cfg)


# valores permitidos (o resto volta ao padrao): protege contra config.json corrompido
# ou um arquivo importado com valores estranhos
_ESCOLHAS = {
    "modo": ("desfoque", "imagem", "video", "cor", "nenhum"),
    "saida": tuple(RESOLUCOES), "processador": ("auto", "cpu"), "idioma": ("auto", "pt", "en"),
    "cor_fora_circulo": ("verde", "preto", "branco"),
    "grav_saida": ("auto", "nativa", "1440p", "1080p"), "grav_encaixe": ("inteira", "preencher", "recorte"),
    "grav_fonte": ("tela", "regiao", "janela"),
    "grav_fundo": ("desfocado", "cor"), "grav_preset": ("edicao", "alta", "compacta"), "grav_fps": (30, 60),
    "grav_cam_forma": ("nenhuma", "circulo", "arredondado", "pessoa", "retangulo"),
    "grav_cam_posicao": ("inferior_direito", "inferior_esquerdo", "superior_direito", "superior_esquerdo"),
    "grav_contagem": (0, 3, 5), "limite_fps": (15, 24, 30), "espera_segundos": (5, 30, 120),
    "microfone_intensidade": (50, 75, 100),
}
_FAIXAS = {
    "forca_desfoque": (1, 40), "suavidade_borda": (0, 6), "estabilidade": (0, 95), "firmeza": (0, 100),
    "reducao_ruido": (0, 100), "correcao_luz": (0, 100), "retoque": (0, 100), "zoom_max": (1.0, 2.5),
    "velocidade_enquadrar": (1, 10), "tamanho_circulo": (30, 100), "borda_circulo": (0, 20),
    "grav_monitor": (0, 15), "grav_cam_tamanho": (10, 60), "grav_cam_borda": (0, 20),
}


def sanear(cfg):
    for k, ok in _ESCOLHAS.items():
        if k in cfg and cfg[k] not in ok:
            cfg[k] = CONFIG_PADRAO[k]
    for k, (a, b) in _FAIXAS.items():
        v = cfg.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            cfg[k] = CONFIG_PADRAO[k]
        else:
            cfg[k] = type(CONFIG_PADRAO[k])(min(b, max(a, v)))
    if cfg["qualidade"] not in QUALIDADES:
        cfg["qualidade"] = "equilibrado"
    cor = cfg.get("cor_fundo")
    if not (isinstance(cor, list) and len(cor) == 3 and all(isinstance(x, int) and 0 <= x <= 255 for x in cor)):
        cfg["cor_fundo"] = list(CONFIG_PADRAO["cor_fundo"])
    if not isinstance(cfg.get("perfis"), dict):
        cfg["perfis"] = copy.deepcopy(PERFIS_PADRAO)
    r = cfg.get("grav_regiao")
    if not (isinstance(r, list) and (len(r) == 0 or (len(r) == 4 and all(isinstance(x, int) and 0 <= x <= 16384 for x in r)))):
        cfg["grav_regiao"] = []
    j = cfg.get("grav_janela")
    if not isinstance(j, dict):
        cfg["grav_janela"] = {}
    else:
        cfg["grav_janela"] = {k: v for k, v in j.items()
                              if (k in ("exe", "titulo") and isinstance(v, str) and len(v) < 300)
                              or (k == "hwnd" and isinstance(v, int))}
    gm = cfg.get("ganhos_microfone")
    cfg["ganhos_microfone"] = {k: float(min(24, max(-12, v))) for k, v in gm.items()
                               if isinstance(k, str) and len(k) < 200 and isinstance(v, (int, float))
                               and not isinstance(v, bool)} if isinstance(gm, dict) else {}
    if not isinstance(cfg.get("volume_automatico"), bool):
        cfg["volume_automatico"] = True
    for k in ("grav_mic_entrada", "microfone_entrada"):
        if not isinstance(cfg.get(k), str) or len(cfg[k]) > 200:
            cfg[k] = ""
    for k in ("texto_privacidade",):
        cfg[k] = str(cfg.get(k, ""))[:40]
    return cfg


def aplicar_perfil(cfg, nome):
    """Copia as configuracoes do perfil para o cfg (so as que o perfil tem)."""
    perfil = cfg["perfis"].get(nome)
    if not perfil:
        return False
    for k, v in perfil.items():
        if k in CHAVES_PERFIL:
            cfg[k] = copy.deepcopy(v)
    return True


def salvar_perfil(cfg, nome):
    cfg["perfis"][nome] = {k: copy.deepcopy(cfg[k]) for k in CHAVES_PERFIL}


def salvar_config(cfg):
    try:
        with open(CONFIG_ARQ, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[aviso] nao consegui salvar config: {e}")


# ---------------------------------------------------------------- camera
def listar_cameras():
    """Nomes das cameras DirectShow (o indice e a posicao na lista)."""
    try:
        import ctypes
        # COM e por thread: sem isso, listar a partir de uma thread de fundo
        # (ex.: ao sair do modo espera) falha e a webcam "some"
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)     # COINIT_APARTMENTTHREADED
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception as e:
        print(f"[aviso] nao consegui listar as cameras: {e}")
        return []


def eh_virtual(nome):
    return any(v in nome.lower() for v in CAMERAS_VIRTUAIS)


def escolher_camera(nome_desejado):
    nomes = listar_cameras()
    if nome_desejado:
        for i, n in enumerate(nomes):
            if nome_desejado.lower() in n.lower():
                return i, n
        if str(nome_desejado).isdigit():
            i = int(nome_desejado)
            return i, nomes[i] if i < len(nomes) else f"camera {i}"
        print(f"[aviso] camera '{nome_desejado}' nao encontrada")
    for i, n in enumerate(nomes):
        if not eh_virtual(n):
            return i, n
    return 0, "camera 0"


class Captura:
    """Le a webcam numa thread e guarda sempre o quadro mais novo."""

    def __init__(self, indice, largura, altura, fps):
        self.cap = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        # MJPG precisa vir DEPOIS da resolucao; senao o DirectShow fica em
        # YUY2, que em 720p via USB 2.0 so chega a ~13 fps
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError("webcam nao abriu")
        ok, quadro = self.cap.read()
        if not ok:
            self.cap.release()
            raise RuntimeError("webcam abriu mas nao entregou imagem")
        self.quadro, self.num = quadro, 1
        self.largura, self.altura = quadro.shape[1], quadro.shape[0]
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or fps
        self.cond = threading.Condition()
        self.rodando = True
        self.falhou = False          # True: parou de entregar imagem (desconectada?)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        falhando_desde = None
        while self.rodando:
            ok, quadro = self.cap.read()
            if not ok:
                agora = time.monotonic()
                falhando_desde = falhando_desde or agora
                if agora - falhando_desde > 1.5:
                    self.falhou = True           # o supervisor do motor trata
                time.sleep(0.02)
                continue
            falhando_desde = None
            self._contar_fps()
            with self.cond:
                self.quadro, self.num = quadro, self.num + 1
                self.cond.notify_all()

    def _contar_fps(self):
        agora = time.monotonic()
        if not hasattr(self, "_janela_fps"):
            self._janela_fps, self._quadros_fps, self.fps_real = agora, 0, 0.0
        self._quadros_fps += 1
        if agora - self._janela_fps >= 2.0:
            self.fps_real = self._quadros_fps / (agora - self._janela_fps)
            self._janela_fps, self._quadros_fps = agora, 0

    def ler(self, ultimo_num):
        with self.cond:
            self.cond.wait_for(lambda: self.num != ultimo_num, timeout=1.0)
            return self.quadro, self.num

    def fechar(self):
        self.rodando = False
        self.thread.join(timeout=1.0)
        self.cap.release()


# ---------------------------------------------------------------- IA
def baixar_modelo(precisao):
    arq = MODELO_ARQ.format(precisao)
    if not os.path.exists(arq):
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        print(f"Baixando modelo de IA ({precisao}, so na primeira vez)...")
        urllib.request.urlretrieve(MODELO_URL.format(precisao), arq + ".part")
        os.replace(arq + ".part", arq)
    return arq


def adaptar_modelo(precisao):
    """Cria uma versao do modelo que recebe a imagem da webcam como ela vem
    (uint8, altura x largura x 3) e devolve a cor ja em uint8 e o recorte
    em float32. Essas conversoes passam a rodar na GPU: no CPU elas custavam
    ~12 ms por quadro. Gerado uma vez e guardado em modelos/."""
    arq = MODELO_ARQ.format(precisao).replace(".onnx", "_io.onnx")
    if os.path.exists(arq):                      # instalado: ja vem pronto
        return arq
    base = baixar_modelo(precisao)
    import onnx
    from onnx import TensorProto, helper as hp
    m = onnx.load(base)
    g = m.graph
    t = TensorProto.FLOAT16 if precisao == "fp16" else TensorProto.FLOAT
    dt = np.float16 if precisao == "fp16" else np.float32

    def const(nome, valor):
        return hp.make_node("Constant", [], [nome], value=onnx.numpy_helper.from_array(
            np.array(valor, dt), nome))

    entrada = [i for i in g.input if i.name == "src"][0]
    g.input.remove(entrada)
    g.input.insert(0, hp.make_tensor_value_info("img", TensorProto.UINT8, [1, "h", "w", 3]))
    antes = [
        hp.make_node("Cast", ["img"], ["img_f"], to=t),
        const("k_255inv", 1 / 255),
        hp.make_node("Mul", ["img_f", "k_255inv"], ["img_n"]),
        hp.make_node("Transpose", ["img_n"], ["src"], perm=[0, 3, 1, 2]),
    ]
    depois = [
        hp.make_node("Transpose", ["fgr"], ["fgr_hwc"], perm=[0, 2, 3, 1]),
        const("k_255", 255.0), const("k_meio", 0.5), const("k_0", 0.0), const("k_max", 255.0),
        hp.make_node("Mul", ["fgr_hwc", "k_255"], ["fgr_x"]),
        hp.make_node("Add", ["fgr_x", "k_meio"], ["fgr_r"]),
        hp.make_node("Clip", ["fgr_r", "k_0", "k_max"], ["fgr_c"]),
        hp.make_node("Cast", ["fgr_c"], ["frente"], to=TensorProto.UINT8),
        hp.make_node("Cast", ["pha"], ["alpha"], to=TensorProto.FLOAT),
    ]
    nos = antes + list(g.node) + depois
    del g.node[:]
    g.node.extend(nos)
    saidas = {o.name: o for o in g.output}
    del g.output[:]
    g.output.extend([
        hp.make_tensor_value_info("frente", TensorProto.UINT8, [1, "h", "w", 3]),
        hp.make_tensor_value_info("alpha", TensorProto.FLOAT, [1, 1, "h", "w"]),
        saidas["r1o"], saidas["r2o"], saidas["r3o"], saidas["r4o"],
    ])
    onnx.save(m, arq + ".part")
    os.replace(arq + ".part", arq)
    return arq


def threads_ia_cpu():
    """~1 thread por nucleo fisico disponivel, deixando folga para a captura e a
    composicao (que rodam em paralelo)."""
    logicos = os.cpu_count() or 4
    try:
        import ctypes
        proc, sist = ctypes.c_size_t(), ctypes.c_size_t()
        if ctypes.windll.kernel32.GetProcessAffinityMask(ctypes.windll.kernel32.GetCurrentProcess(),
                                                         ctypes.byref(proc), ctypes.byref(sist)):
            logicos = bin(proc.value).count("1") or logicos
    except Exception:
        pass
    return max(1, min(8, logicos // 2))


class Recortador:
    """Robust Video Matting: alpha 0..1 com detalhe de cabelo, mais a cor
    'limpa' da pessoa (fgr), sem contaminacao do fundo nas bordas."""

    def __init__(self, forcar_cpu=False):
        import onnxruntime as ort
        ort.set_default_logger_severity(3)
        so = ort.SessionOptions()
        so.enable_mem_pattern = False           # exigido pelo DirectML
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = None
        if not forcar_cpu and "DmlExecutionProvider" in ort.get_available_providers():
            try:
                # FP16 na GPU: metade do tempo do FP32
                self.sess = ort.InferenceSession(adaptar_modelo("fp16"), so,
                                                 providers=["DmlExecutionProvider", "CPUExecutionProvider"])
                self.tipo, self.dispositivo = np.float16, _("GPU (DirectML)")
            except Exception as e:
                print(f"[aviso] GPU falhou ({e}); usando CPU")
        if self.sess is None:
            # CPU: limita as threads aos nucleos que o processo pode usar de fato.
            # Sem isso o ONNX Runtime pode abrir mais threads que nucleos e elas
            # brigam entre si (e com a captura/composicao), derrubando o FPS.
            so.intra_op_num_threads = threads_ia_cpu()
            so.inter_op_num_threads = 1
            so.add_session_config_entry("session.intra_op.allow_spinning", "0")
            self.sess = ort.InferenceSession(adaptar_modelo("fp32"), so, providers=["CPUExecutionProvider"])
            self.tipo, self.dispositivo = np.float32, "CPU"
        self.reset()

    def reset(self):
        self.rec = [np.zeros((1, 1, 1, 1), self.tipo)] * 4

    def __call__(self, rgb, downsample):
        frente, alpha, *self.rec = self.sess.run(None, {
            "img": rgb[None],
            "r1i": self.rec[0], "r2i": self.rec[1],
            "r3i": self.rec[2], "r4i": self.rec[3],
            "downsample_ratio": np.array([downsample], np.float32),
        })
        return frente[0], alpha[0, 0]


# ---------------------------------------------------------------- refinamento
def refinar_alpha(a, a_ant, cfg):
    """Ajustes finos do recorte.
    firmeza:      corta transparencias fracas (poeira no fundo, buracos no corpo)
                  com curva suave, sem criar degraus serrilhados
    suavidade:    leve desfoque so na mascara: borda menos 'recortada'
    estabilidade: media com o quadro anterior, mas adaptativa: onde mudou
                  muito (voce se mexeu) segue na hora, sem rastro."""
    f = cfg["firmeza"] / 100.0
    if f > 0:
        lo, hi = 0.4 * f, 1.0 - 0.4 * f
        a = np.clip((a - lo) * (1.0 / (hi - lo)), 0.0, 1.0)
        a = a * a * (3.0 - 2.0 * a)               # smoothstep
    s = cfg["suavidade_borda"]
    if s > 0:
        a = cv2.GaussianBlur(a, (0, 0), s)
    e = cfg["estabilidade"] / 100.0
    if e > 0 and a_ant is not None and a_ant.shape == a.shape:
        dif = cv2.absdiff(a, a_ant)
        peso = np.clip((1.0 - e) + dif * 4.0, 0.0, 1.0)
        a = a_ant + peso * (a - a_ant)
    return a.astype(np.float32, copy=False)


# ---------------------------------------------------------------- ruido
class RedutorRuido:
    """Tira o granulado tipico de webcam, em duas etapas:
    1) temporal: o ruido muda a cada quadro, a pessoa quase nao. Mistura com
       o quadro anterior onde nada se mexeu; onde houve movimento usa o
       quadro novo, entao nao fica rastro.
    2) espacial: filtro bilateral, que alisa a pele mas preserva contornos
       (olhos, oculos, barba)."""

    def __init__(self):
        self.ant = None
        self.lut_chave = None

    def reset(self):
        self.ant = None

    def __call__(self, img, forca):
        if forca <= 0:
            self.ant = None
            return img
        f = forca / 100.0
        if self.ant is not None and self.ant.shape == img.shape:
            h, w = img.shape[:2]
            dif = cv2.cvtColor(cv2.absdiff(img, self.ant), cv2.COLOR_RGB2GRAY)
            # meia resolucao: mais rapido e ja "media" o ruido do proprio dif
            dif = cv2.resize(dif, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
            if self.lut_chave != forca:
                base, limiar = 1.0 - 0.75 * f, 3.0 + 6.0 * f
                d = np.arange(256, dtype=np.float32)
                self.lut = np.clip(base + (d - limiar) / 10.0, base, 1.0).astype(np.float32)
                self.lut_chave = forca
            peso = cv2.resize(self.lut[dif], (w, h), interpolation=cv2.INTER_LINEAR)
            img = cv2.blendLinear(img, self.ant, peso, 1.0 - peso)
        self.ant = img
        return cv2.bilateralFilter(img, 5, 10 + 30 * f, 3)


# ---------------------------------------------------------------- composicao
def fundo_desfocado(rgb, alpha, forca):
    """Desfoque 'consciente da mascara': a pessoa sai antes de borrar, entao
    nao aparece halo em volta do contorno. Feito em 1/4 da resolucao."""
    h, w = alpha.shape
    pw, ph = max(16, w // 4), max(16, h // 4)
    peso = cv2.resize(1.0 - alpha, (pw, ph), interpolation=cv2.INTER_AREA)
    peq = cv2.resize(rgb, (pw, ph), interpolation=cv2.INTER_AREA).astype(np.float32)
    k = int(forca) * 2 + 1
    num = cv2.GaussianBlur(peq * peso[..., None], (k, k), 0)
    den = cv2.GaussianBlur(peso, (k, k), 0)[..., None]
    sem_pessoa = num / np.maximum(den, 1e-3)
    normal = cv2.GaussianBlur(peq, (k, k), 0)
    t = np.clip(den / 0.05, 0, 1)
    peq = np.clip(sem_pessoa * t + normal * (1 - t), 0, 255).astype(np.uint8)
    return cv2.resize(peq, (w, h), interpolation=cv2.INTER_LINEAR)


def carregar_imagem_fundo(caminho, w, h):
    if not caminho or not os.path.exists(caminho):
        return None
    img = cv2.imdecode(np.fromfile(caminho, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)                       # preenche sem distorcer
    img = cv2.resize(img, (int(iw * s + 0.5), int(ih * s + 0.5)), interpolation=cv2.INTER_AREA)
    y0, x0 = (img.shape[0] - h) // 2, (img.shape[1] - w) // 2
    return np.ascontiguousarray(cv2.cvtColor(img[y0:y0 + h, x0:x0 + w], cv2.COLOR_BGR2RGB))


def compor(rgb, frente, alpha, cfg, fundo_img):
    modo = cfg["modo"]
    if modo == "nenhum":
        return rgb
    if modo == "desfoque":
        fundo = fundo_desfocado(rgb, alpha, cfg["forca_desfoque"])
    elif modo in ("imagem", "video") and fundo_img is not None:
        fundo = fundo_img
    else:
        fundo = np.empty_like(rgb)
        fundo[:] = cfg["cor_fundo"]
    # 'frente' e a cor limpa do RVM: entre os fios de cabelo nao vaza a
    # parede nitida (era isso que gerava os pontinhos claros na borda)
    return cv2.blendLinear(frente, fundo, alpha, 1.0 - alpha)


# ---------------------------------------------------------------- motor
class Motor:
    """Junta tudo em duas threads:
      - IA: le a webcam, roda o modelo e refina o recorte
      - saida: compoe o quadro e envia para a camera virtual
    Enquanto a GPU calcula o quadro N+1, a CPU compoe o quadro N."""

    def __init__(self, cfg, forcar_cpu=False, camera_virtual=True):
        self.cfg = cfg
        self.ia = Recortador(forcar_cpu)
        self.ruido = RedutorRuido()
        self.luz = efeitos.CorrecaoLuz()
        self.enquadrar = efeitos.Enquadramento()
        self.retoque = efeitos.Retoque()
        self.microfone = None        # microfone.MicrofoneLimpo (criado pela interface, se disponivel)
        self.gravacao = None         # gravador.Gravacao em andamento (recebe a imagem da webcam)
        self.redonda = efeitos.Redonda()
        self.video = efeitos.FundoVideo()
        self.privacidade = False     # "Volto ja": ligado pelo botao ou pelo atalho
        self._tela_priv = None
        self._ultimo_limpo = None
        self.janela_visivel = True   # a interface avisa quando esta minimizada/na bandeja
        self.sem_webcam = False      # webcam falhou (ocupada/ausente/desconectada): tenta de novo
        self.problemas = {}          # codigo -> dados (a interface mostra como aviso amigavel)
        if self.ia.dispositivo == "CPU":
            if not forcar_cpu:
                self.avisar("gpu_indisponivel")
            # sem placa de video: ja comeca numa qualidade que o processador aguenta
            if self.cfg["qualidade_automatica"] and self.cfg["qualidade"] in ("equilibrado", "maximo"):
                self.cfg["qualidade"] = "rapido"
        self.em_espera = False       # webcam desligada ate algum app usar a camera
        self.camera_virtual = camera_virtual
        self.cap = None
        self.cam = None
        self.cam_desc = "desligada"
        self.nome_camera = ""
        self.saida = None            # ultimo quadro final (RGB) para a previa
        self.alpha = None            # ultimo recorte (para debug/teste)
        self.fps = 0.0
        self.ms_ia = 0.0
        self.erro = ""               # (legado) textos livres; preferir avisar()
        self._res = None
        self._num_res = 0
        self._cond = threading.Condition()
        self._reset_pedido = True
        self._zerar_estab = True
        self._fundo_img = None
        self._fundo_chave = None
        self._rodando = False
        self._lock_cam = threading.Lock()

    # -- ciclo de vida
    # -- problemas (mensagens amigaveis; ver mensagens.py)
    def avisar(self, codigo, **dados):
        if self.problemas.get(codigo) != dados:
            self.problemas[codigo] = dados
            print(f"[aviso] {codigo} {dados}")

    def resolver(self, *codigos):
        for c in codigos:
            self.problemas.pop(c, None)

    def _falha_webcam(self):
        """Descobre POR QUE a webcam nao abriu, para a mensagem certa."""
        reais = [n for n in listar_cameras() if not eh_virtual(n)]
        if not reais:
            codigo, dados = "webcam_ausente", {}
        elif mensagens.camera_bloqueada_pelo_windows():
            codigo, dados = "webcam_bloqueada", {}
        else:
            nome = self.cfg["camera"] if any(self.cfg["camera"] == n for n in reais) else reais[0]
            codigo, dados = "webcam_ocupada", {"camera": nome}
        outros = {"webcam_ocupada", "webcam_ausente", "webcam_bloqueada", "webcam_desconectada"} - {codigo}
        self.resolver(*outros)
        self.avisar(codigo, **dados)

    def iniciar(self, em_espera=False):
        """em_espera=True (app aberto pela bandeja / com o Windows): nao liga a
        webcam agora; ela liga sozinha quando algum app usar a camera."""
        if em_espera:
            self.em_espera = True
            self.janela_visivel = False      # comeca escondido na bandeja
        else:
            try:
                self.abrir_camera(self.cfg["camera"])
            except Exception as e:
                # nao impede o app de abrir: mostra o motivo e tenta de novo sozinho
                print(f"[webcam] nao abriu: {e}")
                self.sem_webcam = True
                self._falha_webcam()
        if self.camera_virtual:
            self._abrir_camera_virtual()
        self._rodando = True
        threading.Thread(target=self._loop_ia, daemon=True).start()
        threading.Thread(target=self._loop_saida, daemon=True).start()
        threading.Thread(target=self._loop_supervisor, daemon=True).start()

    # -- modo espera automatico
    def _loop_supervisor(self):
        """Cuida da webcam em segundo plano:
        - modo espera: so liga se a janela estiver visivel OU algum app
          (Meet, Zoom, OBS...) estiver usando a OpenBokeh Camera;
        - recuperacao: webcam ocupada/ausente/desconectada -> tenta de novo a
          cada 3 s, sem o usuario precisar fazer nada."""
        inativo_desde, ultima_tentativa, lento_desde = None, 0.0, None
        while self._rodando:
            time.sleep(0.5)
            lento_desde = self._qualidade_automatica(lento_desde)
            self._verificar_webcam_lenta()
            cap = self.cap
            if cap is not None and cap.falhou:
                self._perdeu_webcam()
            detecta = self.cfg["espera_automatica"] and hasattr(self.cam, "consumidor_ativo")
            if detecta and (self.em_espera or self.sem_webcam):
                self.cam.verificar_consumidor()
            precisa = (not detecta) or self.janela_visivel or self.cam.consumidor_ativo() or \
                (self.gravacao is not None and self.gravacao.usa_webcam)
            agora = time.monotonic()
            if precisa:
                inativo_desde = None
                pausa = 3.0 if self.sem_webcam else 0.0
                if (self.em_espera or self.sem_webcam) and agora - ultima_tentativa >= pausa:
                    ultima_tentativa = agora
                    self._retomar()
            elif not self.em_espera and not self.sem_webcam:
                if inativo_desde is None:
                    inativo_desde = agora
                elif agora - inativo_desde > float(self.cfg["espera_segundos"]):
                    self._suspender()

    def _verificar_webcam_lenta(self):
        """A propria webcam entregando poucos quadros (quase sempre pouca luz:
        ela aumenta a exposicao e reduz o FPS). Nao e culpa da IA: avisa e
        aponta para os ajustes da webcam."""
        cap = self.cap
        fps = getattr(cap, "fps_real", 0.0) if cap is not None else 0.0
        if cap is None or fps <= 0:
            return
        if fps < 18 and (getattr(cap, "fps", 30) or 30) >= 25:
            self._webcam_lenta = getattr(self, "_webcam_lenta", 0) + 1
            if self._webcam_lenta >= 8:            # ~4 s seguidos
                self.avisar("webcam_lenta", fps=f"{fps:.0f}", camera=self.nome_camera or "webcam")
        else:
            self._webcam_lenta = 0
            if fps >= 22:
                self.resolver("webcam_lenta")

    def _qualidade_automatica(self, lento_desde):
        """Se ficar abaixo de ~80% do FPS desejado por 6 s, baixa a qualidade
        da IA um degrau (Maxima -> Equilibrada -> Rapida) e avisa."""
        ativo = self.cap is not None and not self.em_espera and not self.sem_webcam
        alvo = min(self.cfg["limite_fps"], getattr(self.cap, "fps", 30) or 30)
        real = getattr(self.cap, "fps_real", 0.0)
        if real > 0:
            alvo = min(alvo, real)           # webcam lenta: nao adianta baixar a qualidade da IA
        if not (self.cfg["qualidade_automatica"] and ativo and self.fps > 0 and self.fps < alvo * 0.8):
            return None
        agora = time.monotonic()
        if lento_desde is None:
            return agora
        if agora - lento_desde < 6.0:
            return lento_desde
        degraus = {"maximo": "equilibrado", "equilibrado": "rapido", "rapido": "leve"}
        nova = degraus.get(self.cfg["qualidade"])
        if nova:
            self.cfg["qualidade"] = nova
            self.pedir_reset()
            self.avisar("qualidade_reduzida",
                        qualidade={"equilibrado": _("Equilibrada"), "rapido": _("Rápida"), "leve": _("Leve")}[nova])
        return None

    def definir_saida(self, nome):
        """Troca a resolucao da OpenBokeh Camera (720p/1080p)."""
        self.cfg["saida"] = nome
        if self.cam is not None and hasattr(self.cam, "consumidor_ativo"):
            import camera_propria
            antiga = self.cam
            w, h = RESOLUCOES.get(nome, RESOLUCOES["720p"])
            self.cam = camera_propria.criar(w, h, 30)
            antiga.close()

    def reabrir_webcam(self):
        """Reabre a webcam (ex.: depois de trocar a resolucao de captura)."""
        if self.cap is not None:
            self.tentar_webcam_agora()

    def abrir_ajustes_webcam(self):
        """Janela do proprio driver (exposicao, foco, balanco de branco...).
        Nao trava a imagem: o Windows abre em outra thread."""
        cap = self.cap
        if cap is None:
            return False
        try:
            return bool(cap.cap.set(cv2.CAP_PROP_SETTINGS, 1))
        except Exception as e:
            print(f"[webcam] ajustes do driver: {e}")
            return False

    def alternar_efeito(self):
        """Atalho: desliga o efeito (imagem direta) ou volta ao ultimo efeito."""
        if self.cfg["modo"] != "nenhum":
            self.cfg["modo_anterior"] = self.cfg["modo"]
            self.cfg["modo"] = "nenhum"
        else:
            self.cfg["modo"] = self.cfg.get("modo_anterior") or "desfoque"
        return self.cfg["modo"]

    def tentar_webcam_agora(self):
        """Botao "Tentar agora" dos avisos."""
        threading.Thread(target=self._retomar, daemon=True).start()

    def _perdeu_webcam(self):
        with self._lock_cam:
            cap, self.cap = self.cap, None
            self.sem_webcam = True
        if cap:
            cap.fechar()
        self.fps = 0.0
        self.avisar("webcam_desconectada", camera=self.nome_camera or "webcam")
        print("[webcam] parou de responder")

    def _suspender(self):
        with self._lock_cam:
            cap, self.cap = self.cap, None
            self.em_espera = True
        if cap:
            cap.fechar()
        self.fps = 0.0
        print("[espera] webcam desligada: nenhum app usando a camera")

    def _retomar(self):
        try:
            self.abrir_camera(self.cfg["camera"])
            self.em_espera = False
            self.sem_webcam = False
            self.resolver("webcam_ocupada", "webcam_ausente", "webcam_bloqueada", "webcam_desconectada")
            print("[webcam] ligada")
        except Exception as e:
            print(f"[webcam] nao abriu: {e}")
            self.em_espera = False
            self.sem_webcam = True
            self._falha_webcam()        # mostra o motivo; o supervisor tenta de novo

    def parar(self):
        self._rodando = False
        if self.microfone is not None:
            self.microfone.encerrar()
        time.sleep(0.1)
        with self._lock_cam:
            if self.cap:
                self.cap.fechar()
                self.cap = None
        if self.cam:
            self.cam.close()
            self.cam = None
        self.video.fechar()

    def abrir_camera(self, nome):
        idx, nome_real = escolher_camera(nome)
        nova = Captura(idx, self.cfg["largura"], self.cfg["altura"], self.cfg["fps"])
        with self._lock_cam:
            antiga, self.cap = self.cap, nova
            self.nome_camera = nome_real
            self._reset_pedido = True
        if antiga:
            antiga.fechar()
        if not nome_real.startswith("camera "):          # so grava nomes reais
            self.cfg["camera"] = nome_real
        return nome_real

    def alternar_privacidade(self, ligar=None):
        """Liga/desliga a tela "Volto ja" (botao na janela ou Ctrl+Alt+B)."""
        self.privacidade = (not self.privacidade) if ligar is None else bool(ligar)
        self._tela_priv = None
        return self.privacidade

    def pedir_reset(self):
        """Zera a memoria da IA (ao espelhar, trocar qualidade ou camera)."""
        self._reset_pedido = True

    def _abrir_camera_virtual(self):
        # 1o: camera propria "OpenBokeh Camera" (instalada pelo instalador)
        try:
            import camera_propria
            if camera_propria.instalada() or camera_propria.instalada_mf():
                w, h = RESOLUCOES.get(self.cfg["saida"], RESOLUCOES["720p"])
                self.cam = camera_propria.criar(w, h, 30)
                self.cam_desc = self.cam.device
                return
        except Exception as e:
            print(f"[aviso] camera propria indisponivel: {e}")
        # 2o: camera virtual do OBS (so na versao de desenvolvimento; o pacote
        # instalado nao inclui o pyvirtualcam, que e GPLv2 e ja traz a camera propria)
        try:
            import pyvirtualcam
        except ImportError:
            self.cam_desc = _("não instalada")
            self.avisar("camera_virtual_ausente")
            return
        try:
            w, h, fps = ((self.cap.largura, self.cap.altura, self.cap.fps) if self.cap
                         else (self.cfg["largura"], self.cfg["altura"], self.cfg["fps"]))
            self.cam = pyvirtualcam.Camera(width=w, height=h, fps=int(round(fps)) or 30,
                                           fmt=pyvirtualcam.PixelFormat.RGB, backend="obs")
            self.cam_desc = self.cam.device
        except Exception as e:
            self.cam_desc = _("não instalada")
            print(f"[camera virtual] {e}")
            self.avisar("camera_virtual_ausente")

    # -- threads
    def _loop_ia(self):
        num, ds_ant, t_ultimo = 0, None, 0.0
        while self._rodando:
            with self._lock_cam:
                cap = self.cap
            if cap is None:
                time.sleep(0.05)
                continue
            bgr, num = cap.ler(num)
            limite = self.cfg["limite_fps"]
            if limite < 30:                       # pula quadros: menos GPU/CPU em PCs fracos
                agora = time.perf_counter()
                if agora - t_ultimo < 1.0 / limite - 0.004:
                    continue
                t_ultimo = agora
            if self.cfg["espelhar"]:
                bgr = cv2.flip(bgr, 1)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            reduzir = self.ia.dispositivo == "CPU" and min(rgb.shape[:2]) > ENTRADA_CPU
            if reduzir:
                h0, w0 = rgb.shape[:2]
                ent = cv2.resize(rgb, (round(w0 * ENTRADA_CPU / h0), ENTRADA_CPU), interpolation=cv2.INTER_AREA)
            else:
                ent = rgb
            ds = float(np.clip(QUALIDADES[self.cfg["qualidade"]] / min(ent.shape[:2]), 0.1, 1.0))
            if self._reset_pedido or ds != ds_ant:
                self.ia.reset()
                self.ruido.reset()
                self.luz.reset()
                ds_ant, self._reset_pedido = ds, False
                self._zerar_estab = True
            t0 = time.perf_counter()
            try:
                frente, alpha = self.ia(ent, ds)
                if reduzir:
                    # recorte ampliado; a pessoa usa a imagem original (nitida, em 720p)
                    alpha = cv2.resize(alpha, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
                    frente = rgb
                frente = self.ruido(frente, self.cfg["reducao_ruido"])
                rgb, frente = self.luz(rgb, alpha, self.cfg["correcao_luz"], rgb, frente)
            except Exception as e:
                self.avisar("ia_falhou", detalhe=type(e).__name__)
                print(f"[ia] {e}")
                self.ia.reset()
                time.sleep(0.2)
                continue
            if "ia_falhou" in self.problemas:
                self.resolver("ia_falhou")
            self.ms_ia = 0.9 * self.ms_ia + 0.1 * 1000 * (time.perf_counter() - t0)
            with self._cond:
                self._res = (rgb, frente, alpha)
                self._num_res += 1
                self._cond.notify_all()

    def _fundo(self, w, h):
        chave = (self.cfg["imagem_fundo"], w, h)
        if chave != self._fundo_chave:
            self._fundo_img = carregar_imagem_fundo(self.cfg["imagem_fundo"], w, h)
            self._fundo_chave = chave
        return self._fundo_img

    def _loop_saida(self):
        num, t_ant, a_ant = 0, time.perf_counter(), None
        while self._rodando:
            with self._cond:
                self._cond.wait_for(lambda: self._num_res != num, timeout=1.0)
                if self._num_res == num or self._res is None:
                    continue
                (rgb, frente, alpha), num = self._res, self._num_res
            if self._zerar_estab:
                a_ant, self._zerar_estab = None, False
            alpha = refinar_alpha(alpha, a_ant, self.cfg)
            a_ant = alpha
            h, w = alpha.shape
            modo = self.cfg["modo"]
            fundo = None
            if modo == "imagem":
                fundo = self._fundo(w, h)
                if fundo is None and self.cfg["imagem_fundo"]:
                    self.avisar("fundo_imagem", arquivo=os.path.basename(self.cfg["imagem_fundo"]))
                else:
                    self.resolver("fundo_imagem")
            elif modo == "video":
                fundo = self.video.obter(self.cfg["video_fundo"], w, h)
                if fundo is None and self.cfg["video_fundo"]:
                    self.avisar("fundo_video", arquivo=os.path.basename(self.cfg["video_fundo"]))
                else:
                    self.resolver("fundo_video")
            if modo != "imagem":
                self.resolver("fundo_imagem")
            if modo != "video":
                self.resolver("fundo_video")
            out = compor(rgb, frente, alpha, self.cfg, fundo)
            out = self.retoque(out, alpha, self.cfg["retoque"])
            alpha_saida = alpha                 # recorte alinhado com a imagem que sai
            if self.cfg["enquadrar"]:
                out = self.enquadrar(out, alpha, self.cfg["zoom_max"], self.cfg["velocidade_enquadrar"])
                alpha_saida = self.enquadrar.aplicar(alpha)
            else:
                self.enquadrar.reset()
            if self.privacidade:
                if self._tela_priv is None:
                    self._tela_priv = efeitos.tela_privacidade(self._ultimo_limpo, self.cfg["texto_privacidade"], w, h,
                                                               self.cfg["imagem_privacidade"])
                out = self._tela_priv
            else:
                self._tela_priv = None
                self._ultimo_limpo = out
            grav = self.gravacao
            if grav is not None and grav.usa_webcam:
                try:        # a gravacao recorta o formato (circulo etc.) na placa de video
                    grav.webcam(out, None if self.privacidade else alpha_saida)
                except Exception as e:
                    print(f"[aviso] gravacao/webcam: {e}")
            if self.cfg["redonda"]:
                out = self.redonda(out, self.cfg["tamanho_circulo"], self.cfg["cor_fora_circulo"],
                                   self.cfg["borda_circulo"])
            if self.cam is not None:
                if (w, h) != (self.cam.width, self.cam.height):
                    out = cv2.resize(out, (self.cam.width, self.cam.height), interpolation=cv2.INTER_AREA)
                self.cam.send(out)
            self.saida, self.alpha = out, alpha_saida
            agora = time.perf_counter()
            inst = 1.0 / max(agora - t_ant, 1e-6)
            self.fps = inst if not self.fps else 0.9 * self.fps + 0.1 * inst
            t_ant = agora
            self.num_saida = num
