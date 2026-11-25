"""
OpenBokeh - efeitos da fase 2: correcao de luz, enquadramento automatico,
fundo em video, tela de privacidade, retoque de pele e camera redonda.

Todos usam o recorte (alpha) que a IA ja calcula, entao nao precisam de
nenhum modelo extra: o custo e de poucos milissegundos por quadro.
"""

import os
import time

import cv2
import numpy as np
from i18n import _


def cobrir(img, w, h):
    """Redimensiona para preencher w x h sem distorcer (corta o excesso no centro)."""
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    nw, nh = max(w, int(iw * s + 0.5)), max(h, int(ih * s + 0.5))
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    y0, x0 = (nh - h) // 2, (nw - w) // 2
    return np.ascontiguousarray(img[y0:y0 + h, x0:x0 + w])


# ---------------------------------------------------------------- luz
class CorrecaoLuz:
    """Ajusta a exposicao para a PESSOA (medida so dentro do recorte, nao no
    fundo) chegar a um brilho agradavel. Usa ganho de exposicao, como subir o
    ISO de uma camera: preserva contraste e cor (uma curva gamma deixava a
    imagem 'lavada'). Os brilhos altos sao comprimidos suavemente para nao
    estourar. A mudanca e suavizada no tempo: nada de piscar quando a luz varia."""

    ALVO = 0.50            # brilho medio desejado da pessoa (0..1)

    def __init__(self):
        self.ganho = 1.0
        self.lut = None
        self.ganho_lut = None

    def reset(self):
        self.ganho = 1.0

    @staticmethod
    def _curva(ganho):
        x = np.arange(256, dtype=np.float32) / 255.0 * ganho
        joelho = 0.80                       # acima disso, comprime em vez de cortar
        y = np.where(x < joelho, x, joelho + (1 - joelho) * (1 - np.exp(-(x - joelho) / (1 - joelho))))
        return np.clip(y * 255.0 + 0.5, 0, 255).astype(np.uint8)

    def __call__(self, rgb, alpha, forca, *imagens):
        if forca <= 0:
            self.ganho = 1.0
            return imagens
        h, w = rgb.shape[:2]
        peq = cv2.resize(rgb, (w // 8, h // 8), interpolation=cv2.INTER_AREA)
        y = cv2.cvtColor(peq, cv2.COLOR_RGB2GRAY).astype(np.float32) * (1 / 255)
        m = cv2.resize(alpha, (peq.shape[1], peq.shape[0]), interpolation=cv2.INTER_AREA)
        peso = float(m.sum())
        if peso < m.size * 0.03:                 # quase ninguem na frente: usa o centro
            ph, pw = y.shape
            media = float(y[ph // 4:3 * ph // 4, pw // 4:3 * pw // 4].mean())
        else:
            media = float((y * m).sum() / peso)
        ganho = float(np.clip(self.ALVO / max(media, 0.02), 0.6, 3.0))
        ganho = 1.0 + (ganho - 1.0) * (forca / 100.0)
        self.ganho += (ganho - self.ganho) * 0.06
        if abs(self.ganho - 1.0) < 0.01:
            return imagens
        if self.ganho_lut is None or abs(self.ganho - self.ganho_lut) > 0.005:
            self.lut = self._curva(self.ganho)
            self.ganho_lut = self.ganho
        return tuple(cv2.LUT(im, self.lut) for im in imagens)


# ---------------------------------------------------------------- enquadramento
class Enquadramento:
    """Zoom automatico que acompanha a pessoa, usando o recorte da IA.
    Mantem a cabeca perto do topo e a pessoa ocupando ~55% da largura.
    Uma 'zona morta' ignora movimentos pequenos e a camera desliza devagar ate
    o novo enquadramento, como um operador de camera, sem tremer."""

    def __init__(self):
        self.caixa = None          # [centro_x, centro_y, largura] suavizados

    def reset(self):
        self.caixa = None
        self.ultimo = None

    def __call__(self, img, alpha, zoom_max=1.6, velocidade=5):
        H, W = img.shape[:2]
        f = 8
        m = cv2.resize(alpha, (W // f, H // f), interpolation=cv2.INTER_AREA) > 0.5
        linhas = np.flatnonzero(m.any(axis=1))
        if len(linhas) < 3:
            alvo = [W / 2, H / 2, W]                       # ninguem: volta ao quadro inteiro
        else:
            topo, base = linhas[0], linhas[-1] + 1
            cabeca = m[topo:topo + max(2, (base - topo) // 3)]   # terco de cima da pessoa
            cols_cab = np.flatnonzero(cabeca.any(axis=0))
            cols = np.flatnonzero(m.any(axis=0))
            cx = (cols_cab.mean() + 0.5) * f if len(cols_cab) else W / 2
            largura = (cols[-1] - cols[0] + 1) * f / 0.55
            largura = float(np.clip(largura, W / max(zoom_max, 1.0), W))
            altura = largura * H / W
            cy = topo * f - 0.10 * altura + altura / 2           # 10% de folga acima da cabeca
            alvo = [cx, cy, largura]
        if self.caixa is None:
            self.caixa = alvo
        else:
            passo = 0.015 + 0.012 * velocidade
            for i in range(3):
                d = alvo[i] - self.caixa[i]
                if abs(d) > W * 0.02:                         # zona morta
                    self.caixa[i] += d * passo
        cx, cy, lg = self.caixa
        al = lg * H / W
        if lg >= W - 2:
            self.ultimo = None
            return img
        x0 = int(np.clip(cx - lg / 2, 0, W - lg))
        y0 = int(np.clip(cy - al / 2, 0, H - al))
        self.ultimo = (x0, y0, int(lg), int(al))
        recorte = img[y0:y0 + int(al), x0:x0 + int(lg)]
        return cv2.resize(recorte, (W, H), interpolation=cv2.INTER_LINEAR)

    def aplicar(self, arr):
        """Aplica o mesmo zoom do ultimo quadro em outra imagem (ex.: o recorte da IA),
        para a mascara continuar alinhada com o rosto."""
        if getattr(self, "ultimo", None) is None or arr is None:
            return arr
        x0, y0, lg, al = self.ultimo
        H, W = arr.shape[:2]
        return cv2.resize(arr[y0:y0 + al, x0:x0 + lg], (W, H), interpolation=cv2.INTER_LINEAR)


# ---------------------------------------------------------------- video
class FundoVideo:
    """Toca um video (mp4, mov, webm...) em loop como fundo, no ritmo do video."""

    def __init__(self):
        self.caminho = None
        self.cap = None
        self.quadro = None
        self.tam = None

    def _abrir(self, caminho, w, h):
        if self.cap is not None:
            self.cap.release()
        self.cap, self.quadro, self.caminho, self.tam = None, None, caminho, (w, h)
        if caminho and os.path.exists(caminho):
            cap = self._novo_cap(caminho)
            if cap is not None:
                self.cap = cap
                self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                if not (1 <= self.fps <= 120):
                    self.fps = 30.0
                self.t0 = time.monotonic()
                self.n = 0

    @staticmethod
    def _novo_cap(caminho):
        """Usa o decodificador de video do proprio Windows (Media Foundation):
        MP4 (H.264/HEVC), MOV, WMV, AVI. Assim o app nao precisa carregar o
        FFmpeg (~40 MB a menos na instalacao)."""
        for api in (cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(caminho, api)
            if cap.isOpened():
                return cap
            cap.release()
        return None

    def obter(self, caminho, w, h):
        if caminho != self.caminho or (w, h) != self.tam:
            self._abrir(caminho, w, h)
        if self.cap is None:
            return None
        alvo = int((time.monotonic() - self.t0) * self.fps)
        if alvo - self.n > 15:                 # ficou muito para tras: pula em vez de correr
            self.t0 = time.monotonic() - self.n / self.fps
            alvo = self.n
        novo = None
        while self.n <= alvo:
            ok, q = self.cap.read()
            if not ok:                         # fim do video: recomeca (reabre: o MSMF nao volta ao inicio)
                self.cap.release()
                self.cap = self._novo_cap(self.caminho)
                self.t0, self.n, alvo = time.monotonic(), 0, 0
                if self.cap is None:
                    return self.quadro
                ok, q = self.cap.read()
                if not ok:
                    return self.quadro
            self.n += 1
            novo = q
        if novo is not None:
            self.quadro = cobrir(cv2.cvtColor(novo, cv2.COLOR_BGR2RGB), w, h)
        return self.quadro

    def fechar(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


# ---------------------------------------------------------------- privacidade
def _fonte(tamanho, negrito=False):
    from PIL import ImageFont
    pasta = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for nome in (("segoeuib.ttf", "arialbd.ttf") if negrito else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(os.path.join(pasta, nome), tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def tela_privacidade(ultimo, texto, w, h, imagem=""):
    """Congela o ultimo quadro, desfoca bem forte (nada do ambiente fica
    reconhecivel), escurece na cor da marca e escreve o aviso. Com `imagem`,
    usa a imagem escolhida pelo usuario como fundo."""
    from PIL import Image, ImageDraw
    propria = None
    if imagem and os.path.exists(imagem):
        bruta = cv2.imdecode(np.fromfile(imagem, np.uint8), cv2.IMREAD_COLOR)
        if bruta is not None:
            propria = cobrir(cv2.cvtColor(bruta, cv2.COLOR_BGR2RGB), w, h)
    if propria is not None:
        fundo = propria.astype(np.float32) * 0.55 + np.array([13, 10, 24], np.float32) * 0.45
    else:
        base = ultimo if ultimo is not None and ultimo.shape[:2] == (h, w) else np.zeros((h, w, 3), np.uint8)
        peq = cv2.resize(base, (max(8, w // 32), max(8, h // 32)), interpolation=cv2.INTER_AREA)
        peq = cv2.GaussianBlur(peq, (0, 0), 1.5)
        fundo = cv2.resize(peq, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
        fundo = fundo * 0.35 + np.array([13, 10, 24], np.float32) * 0.65
    img = Image.fromarray(np.clip(fundo, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    texto = (texto or _("Volto já")).strip()[:40]
    d.text((w / 2, h / 2 - h * 0.02), texto, font=_fonte(int(h / 9), True), fill=(238, 235, 250), anchor="ms")
    d.text((w / 2, h / 2 + h * 0.05), _("câmera pausada"), font=_fonte(int(h / 28)), fill=(156, 149, 190), anchor="mt")
    raio, cx, cy = h * 0.012, w / 2, h / 2 + h * 0.13      # tres pontinhos com as cores da logo
    for i, cor in enumerate([(124, 92, 255), (255, 79, 163), (34, 211, 238)]):
        x = cx + (i - 1) * raio * 4
        d.ellipse((x - raio, cy - raio, x + raio, cy + raio), fill=cor)
    return np.asarray(img)


# ---------------------------------------------------------------- retoque de pele
class Retoque:
    """Suaviza a pele (manchas, poros, olheiras leves) sem borrar olhos, boca,
    cabelo e oculos: o filtro bilateral preserva bordas fortes, e a mascara
    vale so na pessoa (alpha) e em tons de pele (YCrCb). Roda em meia
    resolucao para custar poucos milissegundos."""

    def __call__(self, img, alpha, intensidade):
        if intensidade <= 0:
            return img
        h, w = img.shape[:2]
        # trabalha so no retangulo da pessoa (o resto da imagem nao muda)
        ys, xs = np.nonzero(alpha[::8, ::8] > 0.5)
        if len(ys) == 0:
            return img
        y0, y1 = max(0, ys.min() * 8 - 8), min(h, ys.max() * 8 + 16)
        x0, x1 = max(0, xs.min() * 8 - 8), min(w, xs.max() * 8 + 16)
        reg = img[y0:y1, x0:x1]
        rh, rw = reg.shape[:2]
        pw, ph = max(8, rw // 2), max(8, rh // 2)
        peq = cv2.resize(reg, (pw, ph), interpolation=cv2.INTER_AREA)
        k = intensidade / 100.0
        liso = cv2.bilateralFilter(peq, 7, 18 + 32 * k, 5)
        # pele: faixa classica de Cr/Cb (vale para todos os tons de pele)
        ycc = cv2.cvtColor(peq, cv2.COLOR_RGB2YCrCb)
        pele = cv2.inRange(ycc, (40, 135, 80), (250, 175, 130))
        a = cv2.resize(alpha[y0:y1, x0:x1], (pw, ph), interpolation=cv2.INTER_AREA)
        masc = cv2.GaussianBlur(pele.astype(np.float32) * (a * (0.85 * k / 255.0)), (0, 0), 3)
        liso = cv2.resize(liso, (rw, rh), interpolation=cv2.INTER_LINEAR)
        masc = cv2.resize(masc, (rw, rh), interpolation=cv2.INTER_LINEAR)
        out = img.copy()
        out[y0:y1, x0:x1] = cv2.blendLinear(liso, reg, masc, 1.0 - masc)
        return out


# ---------------------------------------------------------------- camera redonda
CORES_FORA = {"verde": (0, 255, 0), "preto": (0, 0, 0), "branco": (255, 255, 255)}


class Redonda:
    """Deixa so um circulo com a imagem; fora dele, uma cor lisa. Com o verde,
    o OBS recorta com o filtro "Chroma Key" e sobra a camera redonda por cima
    da tela (estilo "facecam"). Opcional: um anel colorido em volta."""

    def __init__(self):
        self._chave = None

    def __call__(self, img, tamanho=90, cor="verde", borda=0):
        h, w = img.shape[:2]
        raio = max(8, int(min(w, h) * max(30, min(100, tamanho)) / 200))
        rgb = CORES_FORA.get(cor, CORES_FORA["verde"])
        chave = (w, h, raio, rgb)
        if chave != self._chave:
            # desenha 4x maior e reduz: borda do circulo lisa, sem serrilhado
            g = np.zeros((h * 4, w * 4), np.uint8)
            cv2.circle(g, (w * 2, h * 2), raio * 4, 255, -1, cv2.LINE_AA)
            m = cv2.resize(g, (w, h), interpolation=cv2.INTER_AREA)
            self._fora = (m == 0).astype(np.uint8)          # mascara p/ cv2.copyTo (rapido)
            self._ys, self._xs = np.nonzero((m > 0) & (m < 255))   # so o contorno e misturado
            self._peso = (m[self._ys, self._xs].astype(np.float32) / 255.0)[:, None]
            self._cor = np.empty((h, w, 3), np.uint8)
            self._cor[:] = rgb
            self._chave = chave
        out = img.copy()
        cv2.copyTo(self._cor, self._fora, out)
        p = self._peso
        out[self._ys, self._xs] = (img[self._ys, self._xs] * p + np.array(rgb, np.float32) * (1 - p)).astype(np.uint8)
        if borda > 0:
            esp = max(1, int(round(borda * h / 720)))
            cv2.circle(out, (w // 2, h // 2), raio - esp // 2, (255, 255, 255), esp, cv2.LINE_AA)
        return out
