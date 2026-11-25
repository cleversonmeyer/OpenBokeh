"""
Instalador / desinstalador do OpenBokeh (vira OpenBokeh-Setup.exe).

Instala em C:\\Program Files\\OpenBokeh, registra a camera virtual
"OpenBokeh Camera", cria atalhos e a entrada em "Aplicativos instalados"
do Windows. O mesmo executavel, copiado para a pasta do programa, serve de
desinstalador (opcao --desinstalar).

Precisa de administrador (pasta Program Files e registro da camera); o
manifesto do .exe ja pede isso ao Windows.
"""

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import winreg
import zipfile

from versao import NOME, VERSAO
from i18n import _
PASTA_INSTALACAO = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), NOME)
_WINDIR = os.environ.get("WINDIR", r"C:\Windows")
# 64 bits: Chrome, Zoom, Teams, OBS novos... / 32 bits: programas antigos.
# Cada uma e registrada pelo regsvr32 do seu "lado" do Windows.
DLLS_CAMERA = [
    (os.path.join("camera", "OpenBokehCamera64.dll"), os.path.join(_WINDIR, "System32", "regsvr32.exe")),
    (os.path.join("camera", "OpenBokehCamera32.dll"), os.path.join(_WINDIR, "SysWOW64", "regsvr32.exe")),
]
CHAVE_DESINSTALAR = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{NOME}"
DESINSTALADOR = "Desinstalar OpenBokeh.exe"
SEM_JANELA = 0x08000000   # CREATE_NO_WINDOW

BG, CARD, CARD_2, BORDA = "#0D0A18", "#16122A", "#211B3D", "#2C2552"
TEXTO, SUAVE, ACENTO, ACENTO_HOVER, ERRO = "#EEEBFA", "#9C95BE", "#7C5CFF", "#6847F0", "#FF6B81"


def recurso(nome):
    """Arquivo embutido no .exe (PyInstaller) ou ao lado do script."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


def rodar(cmd):
    """cmd: lista, ou texto pronto. rundll32 precisa de texto: ele mesmo le a linha
    de comando e so aceita aspas em volta do caminho ("dll",Funcao) - com a lista,
    o Python poe aspas em tudo ("dll,Funcao") e o rundll32 nao faz nada, sem erro."""
    return subprocess.run(cmd, creationflags=SEM_JANELA, capture_output=True, text=True)


def pasta_especial(nome_ps):
    r = rodar(["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{nome_ps}')"])
    return r.stdout.strip()


def criar_atalho(caminho_lnk, alvo, icone):
    os.makedirs(os.path.dirname(caminho_lnk), exist_ok=True)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
          "$s.TargetPath=$env:ALVO;$s.WorkingDirectory=(Split-Path $env:ALVO);"
          "$s.IconLocation=$env:ICONE;$s.Description='Fundo desfocado com IA';$s.Save()")
    env = dict(os.environ, LNK=caminho_lnk, ALVO=alvo, ICONE=icone)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env,
                       creationflags=SEM_JANELA, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Falha ao criar atalho: {r.stderr.strip()}")


def atalhos():
    menu = os.path.join(pasta_especial("CommonPrograms"), f"{NOME}.lnk")
    area = os.path.join(pasta_especial("CommonDesktopDirectory"), f"{NOME}.lnk")
    return menu, area


def fechar_app():
    rodar(["taskkill", "/f", "/im", "OpenBokeh.exe"])


def registrar_camera(pasta, registrar=True):
    """Registra (ou remove) as cameras de 64 e 32 bits. True se a de 64 existe."""
    principal = False
    for rel, regsvr in DLLS_CAMERA:
        dll = os.path.join(pasta, rel)
        if not os.path.exists(dll) or not os.path.exists(regsvr):
            continue
        r = rodar([regsvr, "/s"] + ([] if registrar else ["/u"]) + [dll])
        registrar_log(f"{'registrar' if registrar else 'remover'} {rel} -> {r.returncode}")
        if registrar and r.returncode != 0:
            raise RuntimeError(f"Não consegui registrar a câmera virtual ({os.path.basename(dll)}, "
                               f"código {r.returncode}).")
        if rel.endswith("64.dll"):
            principal = True
    camera_windows11(pasta, registrar)
    return principal


DLL_MF = os.path.join("camera", "OpenBokehMF.dll")


def camera_windows11(pasta, registrar=True):
    """Camera no padrao do Windows 11 (Media Foundation): vista pelo app Camera,
    apps da Store e novo Teams. Registra a DLL e cria a camera de forma
    permanente para todos os usuarios. No Windows 10 (sem o recurso) nao faz nada."""
    dll = os.path.join(pasta, DLL_MF)
    if not os.path.exists(dll):
        return False
    regsvr = os.path.join(_WINDIR, "System32", "regsvr32.exe")
    rundll = os.path.join(_WINDIR, "System32", "rundll32.exe")
    if registrar:
        if not windows_tem_camera_virtual():
            registrar_log("camera Windows 11: recurso ausente neste Windows (ok no Windows 10)")
            return False
        r = rodar([regsvr, "/s", dll])
        registrar_log(f"camera Windows 11: regsvr32 -> {r.returncode}")
        if r.returncode != 0:
            return False
        # Sem "Desinstalar" antes: a remocao feita pelo servico de camera do Windows
        # termina depois, e apagava a camera recem-criada. A remocao da versao
        # anterior ja acontece no inicio da atualizacao; aqui so cria e confere.
        for tentativa in range(1, 4):
            codigo = rodar(f'"{rundll}" "{dll}",Instalar').returncode
            visivel = codigo == 0 and camera_windows11_visivel()
            registrar_log(f"camera Windows 11: Instalar (tentativa {tentativa}) -> {codigo}, visivel: {visivel}")
            if codigo == 0 and visivel:
                return True
            time.sleep(2)
        return False
    codigo = rodar(f'"{rundll}" "{dll}",Desinstalar').returncode
    registrar_log(f"camera Windows 11: Desinstalar -> {codigo}")
    registrar_log(f"camera Windows 11: regsvr32 /u -> {rodar([regsvr, '/s', '/u', dll]).returncode}")
    return True


def windows_tem_camera_virtual():
    """Windows 11 (build 22000+) tem MFCreateVirtualCamera."""
    try:
        return bool(ctypes.WinDLL("mfsensorgroup.dll").MFCreateVirtualCamera)
    except (OSError, AttributeError):
        return False


_PS_CAMERAS = (
    "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
    "$null=[Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime];"
    "$m=([System.WindowsRuntimeSystemExtensions].GetMethods()|?{$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1"
    " -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0];"
    "$t=$m.MakeGenericMethod([Windows.Devices.Enumeration.DeviceInformationCollection]).Invoke($null,"
    "@([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([Windows.Devices.Enumeration.DeviceClass]::VideoCapture)));"
    "$t.Wait();$t.Result|%{$_.Name}")


def camera_windows11_visivel(espera=6.0):
    """A "OpenBokeh Camera" aparece na lista de cameras do Windows 11?
    Confere algumas vezes: a camera leva um instante para surgir (ou sumir)."""
    fim = time.time() + espera
    while True:
        time.sleep(1.5)
        r = rodar(["powershell", "-NoProfile", "-Command", _PS_CAMERAS])
        if r.returncode == 0 and f"{NOME} Camera" in r.stdout:
            # confirma que nao sumiu logo em seguida (remocao atrasada)
            time.sleep(1.5)
            r = rodar(["powershell", "-NoProfile", "-Command", _PS_CAMERAS])
            return f"{NOME} Camera" in r.stdout
        if time.time() > fim:
            return False


ARQUIVO_LOG = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "OpenBokeh", "instalacao.log")


def registrar_log(texto):
    """Anota os passos da instalacao (ajuda a descobrir o que falhou)."""
    try:
        os.makedirs(os.path.dirname(ARQUIVO_LOG), exist_ok=True)
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + texto + "\n")
    except OSError:
        pass


MOVEFILE_DELAY_UNTIL_REBOOT = 0x4


def apagar_no_reinicio(caminho):
    ctypes.windll.kernel32.MoveFileExW(ctypes.c_wchar_p(caminho), None, MOVEFILE_DELAY_UNTIL_REBOOT)


def apagar_ou_adiar(caminho):
    """Apaga o arquivo. Se estiver em uso (ex.: a DLL da camera carregada pelo
    Chrome, Discord, Teams...), o Windows nao deixa apagar, mas deixa
    RENOMEAR: renomeia para liberar o nome e agenda a remocao no reinicio."""
    try:
        os.remove(caminho)
        return
    except FileNotFoundError:
        return
    except OSError:
        pass
    if ".antigo-" in os.path.basename(caminho):
        apagar_no_reinicio(caminho)       # ja e uma sobra renomeada: so reagenda
        return
    antigo = f"{caminho}.antigo-{int(time.time() * 1000)}"
    os.replace(caminho, antigo)
    apagar_no_reinicio(antigo)


def limpar_pasta(pasta, manter=()):
    """Remove o conteudo da pasta, contornando arquivos em uso."""
    if not os.path.isdir(pasta):
        return
    for raiz, dirs, arqs in os.walk(pasta, topdown=False):
        for a in arqs:
            caminho = os.path.join(raiz, a)
            if os.path.basename(caminho) in manter and raiz == pasta:
                continue
            try:
                apagar_ou_adiar(caminho)
            except OSError:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(raiz, d))
            except OSError:
                apagar_no_reinicio(os.path.join(raiz, d))   # sobrou arquivo em uso


def tamanho_kb(pasta):
    total = 0
    for raiz, _dirs, arqs in os.walk(pasta):
        for a in arqs:
            try:
                total += os.path.getsize(os.path.join(raiz, a))
            except OSError:
                pass
    return total // 1024


# ---------------------------------------------------------------- instalar
def instalar(atalho_area, progresso):
    registrar_log(f"=== instalando {NOME} {VERSAO}")
    progresso(0.02, _("Fechando o OpenBokeh, se estiver aberto..."))
    fechar_app()
    if os.path.isdir(PASTA_INSTALACAO):
        progresso(0.05, _("Removendo a versão anterior..."))
        registrar_camera(PASTA_INSTALACAO, registrar=False)
        limpar_pasta(PASTA_INSTALACAO)
    os.makedirs(PASTA_INSTALACAO, exist_ok=True)

    with zipfile.ZipFile(recurso("pacote.zip")) as z:
        itens = z.infolist()
        for i, item in enumerate(itens):
            destino = os.path.join(PASTA_INSTALACAO, item.filename)
            if os.path.isfile(destino):
                apagar_ou_adiar(destino)      # sobra de arquivo em uso
            z.extract(item, PASTA_INSTALACAO)
            if i % 25 == 0:
                progresso(0.08 + 0.75 * i / len(itens), _("Copiando arquivos..."))

    progresso(0.85, _("Registrando a câmera “OpenBokeh Camera”..."))
    tem_camera = registrar_camera(PASTA_INSTALACAO)

    progresso(0.9, _("Criando atalhos..."))
    exe = os.path.join(PASTA_INSTALACAO, "OpenBokeh.exe")
    icone = os.path.join(PASTA_INSTALACAO, "_internal", "assets", "icone.ico")
    menu, area = atalhos()
    criar_atalho(menu, exe, icone)
    if atalho_area:
        criar_atalho(area, exe, icone)

    progresso(0.95, _("Registrando no Windows..."))
    desinst = os.path.join(PASTA_INSTALACAO, DESINSTALADOR)
    # desinstalador pequeno (sem o app embutido); antes o instalador inteiro era
    # copiado como desinstalador, ocupando ~140 MB a mais
    origem = recurso("OpenBokeh-Desinstalar.exe")
    if not os.path.isfile(origem):           # (pacote antigo) usa o proprio instalador
        origem = sys.executable
    shutil.copy2(origem, desinst)
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, CHAVE_DESINSTALAR, 0,
                            winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as k:
        for nome, valor in [("DisplayName", NOME), ("DisplayVersion", VERSAO),
                            ("Publisher", _("Projeto OpenBokeh")), ("DisplayIcon", icone),
                            ("InstallLocation", PASTA_INSTALACAO),
                            ("UninstallString", f'"{desinst}" --desinstalar'),
                            ("QuietUninstallString", f'"{desinst}" --desinstalar --silencioso')]:
            winreg.SetValueEx(k, nome, 0, winreg.REG_SZ, valor)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, tamanho_kb(PASTA_INSTALACAO))
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
    progresso(1.0, _("Pronto!"))
    return tem_camera


# ---------------------------------------------------------------- desinstalar
def desinstalar(apagar_config, progresso):
    progresso(0.1, _("Fechando o OpenBokeh..."))
    fechar_app()
    progresso(0.3, _("Removendo a câmera virtual..."))
    registrar_camera(PASTA_INSTALACAO, registrar=False)
    progresso(0.5, _("Removendo atalhos..."))
    # "Iniciar com o Windows" (registrado pelo proprio app, por usuario)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NOME)
    except OSError:
        pass
    for lnk in atalhos():
        try:
            os.remove(lnk)
        except OSError:
            pass
    try:
        winreg.DeleteKeyEx(winreg.HKEY_LOCAL_MACHINE, CHAVE_DESINSTALAR, winreg.KEY_WOW64_64KEY, 0)
    except OSError:
        pass
    if apagar_config:
        shutil.rmtree(os.path.join(os.environ.get("APPDATA", ""), NOME), ignore_errors=True)
    shutil.rmtree(os.path.dirname(ARQUIVO_LOG), ignore_errors=True)     # log da instalacao
    progresso(0.8, _("Removendo arquivos..."))
    # o desinstalador esta dentro da pasta: apaga o resto agora (arquivos em
    # uso ficam para o reinicio) e a pasta logo depois que este processo terminar
    limpar_pasta(PASTA_INSTALACAO, manter=(DESINSTALADOR,))
    apagar_no_reinicio(os.path.join(PASTA_INSTALACAO, DESINSTALADOR))
    apagar_no_reinicio(PASTA_INSTALACAO)
    subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{PASTA_INSTALACAO}"',
                     creationflags=SEM_JANELA, cwd=tempfile.gettempdir())
    progresso(1.0, _("OpenBokeh foi removido."))


# ---------------------------------------------------------------- interface
def janela(modo):
    import customtkinter as ctk
    from PIL import Image

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenBokeh.Setup")
    except Exception:
        pass
    ctk.set_appearance_mode("dark")
    root = ctk.CTk(fg_color=BG)
    root.title(_("Instalar OpenBokeh") if modo == "instalar" else _("Desinstalar OpenBokeh"))
    root.resizable(False, False)
    try:
        root.iconbitmap(recurso("icone.ico"))
        root.after(250, lambda: root.iconbitmap(recurso("icone.ico")))
    except Exception:
        pass

    F = "Segoe UI"
    corpo = ctk.CTkFrame(root, fg_color="transparent")
    corpo.pack(padx=32, pady=28)

    topo = ctk.CTkFrame(corpo, fg_color="transparent")
    topo.pack(anchor="w")
    try:
        logo = ctk.CTkImage(Image.open(recurso("logo.png")), size=(64, 64))
        ctk.CTkLabel(topo, image=logo, text="").pack(side="left")
    except Exception:
        pass
    t = ctk.CTkFrame(topo, fg_color="transparent")
    t.pack(side="left", padx=(16, 0))
    ctk.CTkLabel(t, text=NOME, font=ctk.CTkFont(F, 26, "bold"), text_color=TEXTO, height=30).pack(anchor="w")
    ctk.CTkLabel(t, text=_("versão {versao} · fundo desfocado com IA · grátis e livre").format(versao=VERSAO),
                 font=ctk.CTkFont(F, 12), text_color=SUAVE, height=18).pack(anchor="w")

    cartao = ctk.CTkFrame(corpo, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDA)
    cartao.pack(fill="x", pady=(22, 0))
    dentro = ctk.CTkFrame(cartao, fg_color="transparent")
    dentro.pack(fill="x", padx=18, pady=16)

    var_opcao = ctk.BooleanVar(value=(modo == "instalar"))
    if modo == "instalar":
        texto = _("O OpenBokeh será instalado em:\n"
                  "{pasta}\n\n"
                  "Também será instalada a câmera virtual “OpenBokeh Camera”,\n"
                  "que aparece no Google Meet, Zoom, Teams, Discord e OBS.").format(pasta=PASTA_INSTALACAO)
        opcao = _("Criar atalho na área de trabalho")
    else:
        texto = (_("O OpenBokeh e a câmera virtual “OpenBokeh Camera”\n"
                 "serão removidos deste computador."))
        opcao = _("Apagar também minhas configurações")
    ctk.CTkLabel(dentro, text=texto, font=ctk.CTkFont(F, 13), text_color=TEXTO,
                 justify="left", anchor="w").pack(anchor="w")
    chk = ctk.CTkCheckBox(dentro, text=opcao, variable=var_opcao, font=ctk.CTkFont(F, 13),
                          text_color=TEXTO, fg_color=ACENTO, hover_color=ACENTO_HOVER,
                          border_color=BORDA, checkbox_width=20, checkbox_height=20, corner_radius=6)
    chk.pack(anchor="w", pady=(14, 0))

    if modo == "instalar":
        def ver_licenca(_evento=None):
            destino = os.path.join(tempfile.gettempdir(), "OpenBokeh-LICENSE.txt")
            shutil.copy2(recurso("LICENSE"), destino)
            os.startfile(destino)
        lic = ctk.CTkLabel(corpo, text=_("OpenBokeh é software livre, distribuído sob a licença GNU GPL v3.  Ler a licença"),
                           font=ctk.CTkFont(F, 11, underline=True), text_color=SUAVE, cursor="hand2", anchor="w")
        lic.pack(fill="x", pady=(10, 0))
        lic.bind("<Button-1>", ver_licenca)

    barra = ctk.CTkProgressBar(corpo, height=8, corner_radius=4, fg_color=CARD_2, progress_color=ACENTO)
    barra.set(0)
    status = ctk.CTkLabel(corpo, text="", font=ctk.CTkFont(F, 12), text_color=SUAVE, anchor="w")

    botoes = ctk.CTkFrame(corpo, fg_color="transparent")
    botoes.pack(fill="x", pady=(22, 0))
    estilo = dict(height=40, corner_radius=10, font=ctk.CTkFont(F, 14))
    bt_cancelar = ctk.CTkButton(botoes, text=_("Cancelar"), command=root.destroy, fg_color="transparent",
                                hover_color=CARD_2, text_color=SUAVE, border_width=1, border_color=BORDA,
                                width=120, **estilo)
    bt_cancelar.pack(side="right")
    bt_ok = ctk.CTkButton(botoes, text=_("Instalar") if modo == "instalar" else _("Desinstalar"),
                          fg_color=ACENTO, hover_color=ACENTO_HOVER, text_color="#FFFFFF",
                          width=160, **estilo)
    bt_ok.pack(side="right", padx=(0, 10))

    def progresso(v, msg):
        root.after(0, lambda: (barra.set(v), status.configure(text=msg)))

    def concluir(erro=None, tem_camera=True):
        bt_cancelar.configure(text=_("Fechar"), command=root.destroy, state="normal")
        if erro:
            status.configure(text=_("Erro: {erro}").format(erro=erro), text_color=ERRO)
            return
        if modo == "instalar":
            aviso = "" if tem_camera else _("  (sem câmera própria: usando a do OBS)")
            status.configure(text=_("Instalado com sucesso!") + aviso)
            bt_ok.configure(text=_("Abrir OpenBokeh"), state="normal", command=abrir_app)
        else:
            status.configure(text=_("OpenBokeh foi removido. Obrigado por usar!"))

    def abrir_app():
        # abre pelo Explorer para o app NAO herdar o modo administrador
        subprocess.Popen(["explorer.exe", os.path.join(PASTA_INSTALACAO, "OpenBokeh.exe")])
        root.destroy()

    def executar():
        chk.configure(state="disabled")
        bt_ok.configure(state="disabled")
        bt_cancelar.configure(state="disabled")
        barra.pack(fill="x", pady=(18, 0), before=botoes)
        status.pack(fill="x", pady=(6, 0), before=botoes)

        def tarefa():
            try:
                if modo == "instalar":
                    cam = instalar(var_opcao.get(), progresso)
                    root.after(0, lambda: concluir(tem_camera=cam))
                else:
                    desinstalar(var_opcao.get(), progresso)
                    root.after(0, concluir)
            except Exception as e:
                msg = str(e)
                root.after(0, lambda: concluir(erro=msg))
        threading.Thread(target=tarefa, daemon=True).start()

    bt_ok.configure(command=executar)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desinstalar", action="store_true")
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args()
    # o desinstalador nao traz o pacote do app: aberto sozinho, so desinstala
    sem_pacote = not os.path.exists(recurso("pacote.zip"))
    modo = "desinstalar" if (args.desinstalar or sem_pacote) else "instalar"
    if args.silencioso:
        def nada(*_args):
            pass
        if modo == "instalar":
            instalar(True, nada)
        else:
            desinstalar(False, nada)
        return
    janela(modo)


if __name__ == "__main__":
    main()
