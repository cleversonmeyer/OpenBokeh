# Receita do PyInstaller: gera a pasta do app (sem precisar de Python instalado).
# Uso (na pasta do projeto, no Windows):
#   venv\Scripts\python -m PyInstaller empacotar\openbokeh.spec --noconfirm
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(RAIZ, "assets"), "assets"),
    (os.path.join(RAIZ, "modelos", "rvm_mobilenetv3_fp16_io.onnx"), "modelos"),
    (os.path.join(RAIZ, "modelos", "rvm_mobilenetv3_fp32_io.onnx"), "modelos"),
    (os.path.join(RAIZ, "LICENSE"), "."),
    (os.path.join(RAIZ, "PRIVACIDADE.md"), "."),
    (os.path.join(RAIZ, "PRIVACY.md"), "."),
    (os.path.join(RAIZ, "TERCEIROS.md"), "."),
    (os.path.join(RAIZ, "audio_rnnoise", "COPYING"), "licencas/rnnoise"),
]
datas += collect_data_files("customtkinter")
binaries = collect_dynamic_libs("onnxruntime")      # inclui DirectML.dll
# microfone sem ruido: RNNoise compilado (audio_rnnoise/compilar.sh) + PortAudio do sounddevice
binaries += [(os.path.join(RAIZ, "audio_rnnoise", "build", "rnnoise.dll"), ".")]
# gravacao de tela (gravador/compilar.sh)
binaries += [(os.path.join(RAIZ, "gravador", "build", "OpenBokehGravador.dll"), ".")]
import _sounddevice_data
_pa = os.path.join(list(_sounddevice_data.__path__)[0], "portaudio-binaries", "libportaudio64bit.dll")
binaries += [(_pa, os.path.join("_sounddevice_data", "portaudio-binaries"))]   # so a de 64 bits

a = Analysis(
    [os.path.join(RAIZ, "openbokeh.py")],
    pathex=[RAIZ],
    binaries=binaries,
    datas=datas,
    hiddenimports=["camera_propria", "efeitos", "atalho", "sobre", "versao", "bandeja", "sistema", "mensagens", "ajuda", "menu_ui", "configuracoes", "i18n", "traducoes_en", "microfone", "gravador", "gravacao_ui", "pagina_gravacao", "captura", "sounddevice", "_sounddevice_data", "_cffi_backend", "pystray._win32", "pygrabber.dshow_graph", "PIL._tkinter_finder"],
    excludes=["onnx", "pyvirtualcam", "matplotlib", "pytest", "IPython",
              # nao usados pelo app: imagens AVIF, internet/SSL, criptografia
              "PIL.AvifImagePlugin", "PIL._avif", "ssl", "_ssl", "_hashlib"],
    noarchive=False,
)
# o video de fundo usa o decodificador do Windows (Media Foundation): o FFmpeg
# embutido no OpenCV (~40 MB) nao e necessario
a.binaries = [b for b in a.binaries if "opencv_videoio_ffmpeg" not in b[0].lower()]
a.datas = [d for d in a.datas if "opencv_videoio_ffmpeg" not in d[0].lower()]
# PortAudio: so a de 64 bits (o hook tambem traz 32 bits, ARM, ASIO e macOS)
_sobra_pa = lambda n: "libportaudio" in n.lower() and not n.lower().endswith("libportaudio64bit.dll")
a.binaries = [b for b in a.binaries if not _sobra_pa(b[0])]
a.datas = [d for d in a.datas if not _sobra_pa(d[0])]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="OpenBokeh",
    icon=os.path.join(RAIZ, "assets", "icone.ico"),
    console=False,
    version=os.path.join(SPECPATH, "versao_app.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="OpenBokeh")
