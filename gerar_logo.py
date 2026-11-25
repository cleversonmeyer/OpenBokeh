"""Gera a logo e o icone do OpenBokeh em assets/ (rodar uma vez).

Conceito: o diafragma de uma lente (iris de 6 laminas), nitido, na frente de
luzes coloridas desfocadas: o efeito 'bokeh'. Foco no que importa, fundo
suave atras.
"""

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
S = 1024  # desenha grande e reduz no fim: bordas lisas

FUNDO_1 = (14, 11, 30)
FUNDO_2 = (34, 22, 72)
LUZES = [  # (x, y, raio, cor, intensidade)
    (300, 330, 230, (124, 92, 255), 0.95),   # violeta
    (720, 300, 200, (255, 79, 163), 0.85),   # magenta
    (690, 730, 240, (34, 211, 238), 0.80),   # ciano
    (300, 740, 170, (255, 184, 77), 0.70),   # ambar
    (520, 520, 140, (180, 140, 255), 0.45),
]


def degrade_vertical(w, h, c1, c2):
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        img.putpixel((0, y), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return img.resize((w, h))


def squircle(w, h, raio):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), raio, fill=255)
    return m


def desenhar(tamanho):
    base = degrade_vertical(S, S, FUNDO_1, FUNDO_2)

    # luzes desfocadas, somadas como luz de verdade (modo 'screen')
    for x, y, r, cor, k in LUZES:
        camada = Image.new("RGB", (S, S), (0, 0, 0))
        d = ImageDraw.Draw(camada)
        d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(int(c * k) for c in cor))
        # borda levemente mais clara: tipico do bokeh de lente
        d.ellipse((x - r, y - r, x + r, y + r), outline=tuple(min(255, int(c * k * 1.25)) for c in cor),
                  width=10)
        camada = camada.filter(ImageFilter.GaussianBlur(34))
        base = ImageChops.screen(base, camada)

    # diafragma nitido em branco
    iris = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(iris)
    cx = cy = S / 2
    R, r, E = 330, 128, 40
    d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=255, width=E)
    vert = [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90)))
            for i in range(6)]
    for i in range(6):
        x0, y0 = vert[i]
        xa, ya = vert[i - 1]
        dx, dy = x0 - xa, y0 - ya
        n = math.hypot(dx, dy)
        dx, dy = dx / n, dy / n
        # anda na direcao da aresta ate encostar no anel
        b = (x0 - cx) * dx + (y0 - cy) * dy
        c = (x0 - cx) ** 2 + (y0 - cy) ** 2 - (R - E / 2) ** 2
        t = -b + math.sqrt(b * b - c)
        d.line([(xa, ya), (x0 + dx * t, y0 + dy * t)], fill=255, width=E)
        for px_, py_ in [(xa, ya)]:
            d.ellipse((px_ - E / 2, py_ - E / 2, px_ + E / 2, py_ + E / 2), fill=255)

    # brilho suave em volta do diafragma
    brilho = Image.new("RGB", (S, S), (255, 255, 255))
    base = Image.composite(brilho, base, iris.filter(ImageFilter.GaussianBlur(18)).point(lambda v: v * 0.35))
    base = Image.composite(brilho, base, iris)

    final = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    final.paste(base, (0, 0), squircle(S, S, 232))
    return final.resize((tamanho, tamanho), Image.LANCZOS)


def main():
    os.makedirs(PASTA, exist_ok=True)
    grande = desenhar(1024)
    grande.save(os.path.join(PASTA, "logo.png"))
    grande.resize((256, 256), Image.LANCZOS).save(os.path.join(PASTA, "logo_256.png"))
    grande.resize((64, 64), Image.LANCZOS).save(os.path.join(PASTA, "logo_64.png"))
    grande.save(os.path.join(PASTA, "icone.ico"),
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("assets gerados em", PASTA)


if __name__ == "__main__":
    main()
