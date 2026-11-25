# Desinstalador pequeno (OpenBokeh-Desinstalar.exe): o mesmo instalador.py, sem o
# pacote do app dentro. Gerado pelo empacotar\\construir.py.
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
from PyInstaller.utils.hooks import collect_data_files

datas = [
    (os.path.join(RAIZ, "assets", "logo.png"), "."),
    (os.path.join(RAIZ, "assets", "icone.ico"), "."),
] + collect_data_files("customtkinter")

a = Analysis([os.path.join(RAIZ, "instalador.py")], pathex=[RAIZ], datas=datas,
             hiddenimports=["PIL._tkinter_finder", "i18n", "traducoes_en"],
             excludes=["numpy", "cv2", "onnxruntime", "onnx", "pyvirtualcam", "matplotlib",
                       "PIL.AvifImagePlugin", "PIL._avif", "ssl", "_ssl", "_hashlib"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name="OpenBokeh-Desinstalar",
          icon=os.path.join(RAIZ, "assets", "icone.ico"),
          console=False, uac_admin=True, upx=False,
          version=os.path.join(SPECPATH, "versao_setup.txt"))
