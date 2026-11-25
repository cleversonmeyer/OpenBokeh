# Receita do instalador (OpenBokeh-Setup.exe, arquivo unico, pede administrador).
# Gerado pelo empacotar\construir.py depois que o pacote.zip existe.
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
from PyInstaller.utils.hooks import collect_data_files

datas = [
    (os.path.join(SPECPATH, "pacote.zip"), "."),
    (os.path.join(RAIZ, "assets", "logo.png"), "."),
    (os.path.join(RAIZ, "assets", "icone.ico"), "."),
    (os.path.join(RAIZ, "LICENSE"), "."),
    # o 2o campo e a PASTA de destino dentro do pacote (nao o nome do arquivo)
    (os.path.join(RAIZ, "dist", "OpenBokeh-Desinstalar.exe"), "."),
] + collect_data_files("customtkinter")

a = Analysis([os.path.join(RAIZ, "instalador.py")], pathex=[RAIZ], datas=datas,
             hiddenimports=["PIL._tkinter_finder", "lzma", "_lzma", "i18n", "traducoes_en"],
             excludes=["numpy", "cv2", "onnxruntime", "onnx", "pyvirtualcam", "matplotlib",
                       "PIL.AvifImagePlugin", "PIL._avif", "ssl", "_ssl", "_hashlib"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name="OpenBokeh-Setup",
          icon=os.path.join(RAIZ, "assets", "icone.ico"),
          console=False, uac_admin=True, upx=False,
          version=os.path.join(SPECPATH, "versao_setup.txt"))
