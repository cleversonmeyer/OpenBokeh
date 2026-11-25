"""
Testes automaticos do OpenBokeh (partes que nao precisam de webcam nem da placa de video).
Rodar no Windows, na pasta do projeto:  venv\\Scripts\\python -m unittest discover -s testes -v
"""
import ast
import copy
import glob
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import numpy as np  # noqa: E402


class Traducoes(unittest.TestCase):
    def test_todo_texto_da_interface_tem_traducao(self):
        from traducoes_en import EN
        faltam = []
        for arq in glob.glob(os.path.join(RAIZ, "*.py")):
            if os.path.basename(arq) in ("traducoes_en.py", "gerar_logo.py"):
                continue
            with open(arq, encoding="utf-8") as f:
                arvore = ast.parse(f.read())
            for n in ast.walk(arvore):
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_" and n.args \
                        and isinstance(n.args[0], ast.Constant) and n.args[0].value not in EN:
                    faltam.append((os.path.basename(arq), n.args[0].value[:60]))
        self.assertEqual(faltam, [])

    def test_variaveis_dos_textos_iguais_nas_duas_linguas(self):
        import re
        from traducoes_en import EN
        for pt, en in EN.items():
            self.assertEqual(sorted(re.findall(r"\{(\w+)\}", pt)), sorted(re.findall(r"\{(\w+)\}", en)), pt[:50])


class Configuracoes(unittest.TestCase):
    def setUp(self):
        import motor
        self.M = motor

    def test_padrao_ja_e_valido(self):
        c = copy.deepcopy(self.M.CONFIG_PADRAO)
        self.assertEqual(self.M.sanear(copy.deepcopy(c)), c)

    def test_valores_estranhos_voltam_ao_padrao(self):
        c = copy.deepcopy(self.M.CONFIG_PADRAO)
        c.update(grav_preset="xx", grav_fps=999, forca_desfoque=500, zoom_max="a", cor_fundo=[1, 2],
                 grav_cam_forma="hack", texto_privacidade="x" * 99, retoque=True, grav_regiao=[1, "a"],
                 grav_janela={"exe": 5, "titulo": "ok", "outro": 1}, grav_mic_entrada=None, modo="??")
        self.M.sanear(c)
        self.assertEqual((c["grav_preset"], c["grav_fps"], c["forca_desfoque"], c["zoom_max"]), ("alta", 60, 40, 1.6))
        self.assertEqual(c["cor_fundo"], self.M.CONFIG_PADRAO["cor_fundo"])
        self.assertEqual((c["grav_cam_forma"], c["modo"], c["retoque"]), ("circulo", "desfoque", 0))
        self.assertEqual(len(c["texto_privacidade"]), 40)
        self.assertEqual(c["grav_regiao"], [])
        self.assertEqual(c["grav_janela"], {"titulo": "ok"})
        self.assertEqual(c["grav_mic_entrada"], "")


class LayoutGravacao(unittest.TestCase):
    def setUp(self):
        import gravador
        self.L = gravador.layout_tela

    def test_ultrawide_em_1440p_fica_1x1_com_faixas(self):
        area, dest, esc = self.L(2560, 1080, 2560, 1440, "inteira")
        self.assertEqual((area, dest, esc), ((0, 0, 2560, 1080), (0, 180, 2560, 1080), 1.0))

    def test_preencher_nao_deixa_faixas(self):
        area, dest, _e = self.L(2560, 1080, 1920, 1080, "preencher")
        self.assertEqual(dest, (0, 0, 1920, 1080))
        self.assertEqual(area, (320, 0, 1920, 1080))          # centro da tela, 1:1

    def test_recorte_e_sempre_1x1(self):
        for area in (None, (100, 50, 1200, 800), (0, 0, 2560, 1080)):
            self.assertEqual(self.L(2560, 1080, 1920, 1080, "recorte", area)[2], 1.0)

    def test_area_fora_da_tela_e_limitada(self):
        area, _d, _e = self.L(1920, 1080, 1920, 1080, "inteira", (1800, 1000, 900, 900))
        x, y, w, h = area
        self.assertTrue(x + w <= 1920 and y + h <= 1080 and w >= 16 and h >= 16)

    def test_destino_sempre_dentro_do_video(self):
        for enc in ("inteira", "preencher", "recorte"):
            for area in (None, (0, 0, 640, 480), (10, 10, 2500, 300)):
                _a, (x, y, w, h), _e = self.L(2560, 1080, 1920, 1080, enc, area)
                self.assertTrue(0 <= x and 0 <= y and x + w <= 1920 and y + h <= 1080, (enc, area))


class Captura(unittest.TestCase):
    def test_area_no_monitor(self):
        import captura
        m = {"x": 1920, "y": 0, "largura": 1920, "altura": 1080}
        self.assertEqual(captura.no_monitor((2000, 100, 2800, 700), m), (80, 100, 800, 600))
        self.assertIsNone(captura.no_monitor((0, 0, 500, 500), m))           # outro monitor
        mons = [{"x": 0, "y": 0, "largura": 1920, "altura": 1080}, m]
        self.assertIs(captura.monitor_da_area((1800, 0, 2600, 500), mons), m)  # maior parte no 2o


class Atalhos(unittest.TestCase):
    def test_interpretar(self):
        import atalho
        self.assertEqual(atalho.interpretar("Ctrl+Alt+R"), (0x0002 | 0x0001, ord("R")))
        self.assertIsNone(atalho.interpretar(atalho.DESATIVADO))
        self.assertIsNone(atalho.interpretar("R"))                            # sem modificador
        for o in atalho.OPCOES:
            self.assertTrue(o == atalho.DESATIVADO or atalho.interpretar(o))


class Efeitos(unittest.TestCase):
    def test_enquadramento_mantem_o_recorte_alinhado(self):
        import cv2
        import efeitos
        alpha = np.zeros((720, 1280), np.float32)
        cv2.circle(alpha, (900, 380), 160, 1.0, -1)
        img = np.dstack([alpha * 255] * 3).astype(np.uint8)
        e = efeitos.Enquadramento()
        for _ in range(80):
            out = e(img, alpha, 2.0, 10)
        self.assertIsNotNone(e.ultimo)                                        # houve zoom
        self.assertLess(np.abs(out[..., 0] / 255.0 - e.aplicar(alpha)).mean(), 0.01)

    def test_camera_redonda_e_retoque_nao_mudam_o_tamanho(self):
        import efeitos
        img = (np.random.rand(720, 1280, 3) * 255).astype(np.uint8)
        alpha = np.ones((720, 1280), np.float32)
        self.assertEqual(efeitos.Redonda()(img, 90, "verde", 6).shape, img.shape)
        self.assertEqual(efeitos.Retoque()(img, alpha, 80).shape, img.shape)


class Mensagens(unittest.TestCase):
    def test_todos_os_avisos_montam(self):
        import mensagens
        for cod in mensagens.MENSAGENS:
            self.assertTrue(mensagens.montar(cod, camera="X", arquivo="a.jpg", atalho="Ctrl+Alt+B"))


if __name__ == "__main__":
    unittest.main()
