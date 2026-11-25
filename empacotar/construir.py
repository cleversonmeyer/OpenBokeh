"""Gera dist\\OpenBokeh-Setup.exe.

Uso (Windows, na pasta do projeto):  venv\\Scripts\\python empacotar\\construir.py

1. empacota o app com o PyInstaller (dist\\OpenBokeh)
2. junta a DLL da camera virtual (camera_virtual\\build), se ja compilada
3. compacta tudo em empacotar\\pacote.zip
4. empacota o instalador com o pacote dentro
"""
import os
import subprocess
import sys
import zipfile

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST = os.path.join(RAIZ, "dist")
DLL = os.path.join(RAIZ, "camera_virtual", "build", "OpenBokehCamera64.dll")
ZIP = os.path.join(RAIZ, "empacotar", "pacote.zip")


def pyinstaller(spec):
    subprocess.run([sys.executable, "-m", "PyInstaller", spec, "--noconfirm", "--log-level", "WARN",
                    "--distpath", DIST, "--workpath", os.path.join(RAIZ, "build")],
                   check=True, cwd=RAIZ)


sys.path.insert(0, RAIZ)
import versao as V  # noqa: E402


def arquivo_versao(destino, nome_interno, descricao):
    """Propriedades do .exe (Windows Explorer > Propriedades > Detalhes)."""
    n = [int(x) for x in V.VERSAO.split(".")] + [0]
    texto = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({n[0]}, {n[1]}, {n[2]}, 0), prodvers=({n[0]}, {n[1]}, {n[2]}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'Projeto OpenBokeh'),
      StringStruct('FileDescription', '{descricao}'),
      StringStruct('FileVersion', '{V.VERSAO}'),
      StringStruct('InternalName', '{nome_interno}'),
      StringStruct('LegalCopyright', '{V.COPYRIGHT} - {V.LICENCA}'),
      StringStruct('OriginalFilename', '{nome_interno}.exe'),
      StringStruct('ProductName', '{V.NOME}'),
      StringStruct('ProductVersion', '{V.VERSAO}')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])]
)
"""
    with open(destino, "w", encoding="utf-8") as f:
        f.write(texto)


def verificar_instalador(setup):
    """Confere o que vai DENTRO do instalador antes de entregar: um arquivo no
    lugar errado so apareceria no fim da instalacao, no PC do usuario."""
    from PyInstaller.archive.readers import CArchiveReader
    nomes = set(CArchiveReader(setup).toc.keys())
    exigidos = ["pacote.zip", "OpenBokeh-Desinstalar.exe", "logo.png", "icone.ico", "LICENSE"]
    faltando = [n for n in exigidos if n not in nomes]
    if faltando:
        raise SystemExit(f"ERRO: faltam no instalador: {faltando}")
    with zipfile.ZipFile(ZIP) as z:
        dentro = set(z.namelist())
    exigidos_app = ["OpenBokeh.exe", "camera/OpenBokehCamera64.dll", "camera/OpenBokehCamera32.dll",
                    "camera/OpenBokehMF.dll", "LICENSE", "PRIVACY.md"]
    faltando = [n for n in exigidos_app if n not in dentro]
    # microfone sem ruido: RNNoise e PortAudio (ficam dentro de _internal)
    for fim in ("rnnoise.dll", "libportaudio64bit.dll", "OpenBokehGravador.dll"):
        if not any(n.lower().endswith(fim.lower()) for n in dentro):
            faltando.append(fim)
    if faltando:
        raise SystemExit(f"ERRO: faltam no pacote do app: {faltando}")
    print("   conferido: instalador e pacote com todos os arquivos no lugar certo")


def main():
    arquivo_versao(os.path.join(RAIZ, "empacotar", "versao_app.txt"), "OpenBokeh", V.DESCRICAO)
    arquivo_versao(os.path.join(RAIZ, "empacotar", "versao_setup.txt"), "OpenBokeh-Setup",
                   f"Instalador do {V.NOME}")
    print(f"versao {V.VERSAO}")
    # modelos ja adaptados (entrada uint8 e conversoes na GPU): num clone novo eles ainda nao existem
    sys.path.insert(0, RAIZ)
    import motor
    for precisao in ("fp16", "fp32"):
        motor.adaptar_modelo(precisao)
    print("1/3 empacotando o app...")
    pyinstaller(os.path.join(RAIZ, "empacotar", "openbokeh.spec"))

    print("2/3 compactando...")
    app = os.path.join(DIST, "OpenBokeh")
    # LZMA: compressao bem mais forte que o ZIP comum (instalador menor)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_LZMA) as z:
        for raiz, _, arqs in os.walk(app):
            for a in arqs:
                caminho = os.path.join(raiz, a)
                z.write(caminho, os.path.relpath(caminho, app))
        for doc in ("LICENSE", "PRIVACIDADE.md", "PRIVACY.md", "TERCEIROS.md"):
            z.write(os.path.join(RAIZ, doc), doc)
        if os.path.exists(DLL):
            z.write(DLL, os.path.join("camera", "OpenBokehCamera64.dll"))
            dll_mf = os.path.join(RAIZ, "camera_mf", "build", "OpenBokehMF.dll")
            if os.path.exists(dll_mf):
                z.write(dll_mf, os.path.join("camera", "OpenBokehMF.dll"))
                print("   camera do Windows 11 incluida")
            dll32 = DLL.replace("OpenBokehCamera64.dll", "OpenBokehCamera32.dll")
            if os.path.exists(dll32):
                z.write(dll32, os.path.join("camera", "OpenBokehCamera32.dll"))
                print("   camera virtual 32 bits incluida")
            z.write(os.path.join(RAIZ, "camera_virtual", "LICENCA-UnityCapture.txt"),
                    os.path.join("camera", "LICENCA-UnityCapture.txt"))
            print("   camera virtual incluida")
        else:
            print("   AVISO: camera virtual nao compilada; o instalador nao tera a OpenBokeh Camera")

    print("3/3 empacotando o desinstalador e o instalador...")
    pyinstaller(os.path.join(RAIZ, "empacotar", "desinstalador.spec"))
    pyinstaller(os.path.join(RAIZ, "empacotar", "instalador.spec"))
    setup = os.path.join(DIST, "OpenBokeh-Setup.exe")
    verificar_instalador(setup)
    print(f"pronto: {setup} ({os.path.getsize(setup) / 1e6:.0f} MB)")
    desinst = os.path.join(DIST, "OpenBokeh-Desinstalar.exe")
    app_mb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(app) for f in fs) / 1e6
    print(f"   app instalado: {app_mb:.0f} MB  |  desinstalador: {os.path.getsize(desinst) / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
