"""
Envio de quadros para a camera virtual propria "OpenBokeh Camera".

A camera e uma DLL DirectShow (pasta camera_virtual/) que roda dentro do
programa que usa a camera (Chrome, Zoom, OBS...). Ela cria uma memoria
compartilhada com nome fixo; aqui o OpenBokeh abre essa memoria e escreve
cada quadro. Enquanto nenhum programa estiver usando a camera, a memoria nao
existe e os quadros sao simplesmente descartados (sem custo).

Protocolo (igual ao camera_virtual/shared.inl):
  mutex  OpenBokehCam_Mutx   protege a memoria
  evento OpenBokehCam_Want   a camera pede um quadro (criado aqui)
  evento OpenBokehCam_Sent   avisamos que ha quadro novo
  memoria OpenBokehCam_Data  cabecalho de 32 bytes + imagem RGBA
"""

import ctypes
import time
import winreg
from ctypes import wintypes

import cv2
import numpy as np

NOME = "OpenBokeh Camera"
CLSID = "{D5599B38-27C3-4577-B099-AA2C56D01610}"   # 64 bits (ver OpenBokehCamera.cpp)

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenMutexA.restype = wintypes.HANDLE
_k32.OpenMutexA.argtypes = [wintypes.DWORD, wintypes.BOOL, ctypes.c_char_p]
_k32.CreateEventA.restype = wintypes.HANDLE
_k32.CreateEventA.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, ctypes.c_char_p]
_k32.OpenEventA.restype = wintypes.HANDLE
_k32.OpenEventA.argtypes = [wintypes.DWORD, wintypes.BOOL, ctypes.c_char_p]
_k32.OpenFileMappingA.restype = wintypes.HANDLE
_k32.OpenFileMappingA.argtypes = [wintypes.DWORD, wintypes.BOOL, ctypes.c_char_p]
_k32.MapViewOfFile.restype = ctypes.c_void_p
_k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
_k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
_k32.SetEvent.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002
FILE_MAP_WRITE = 0x0002
WAIT_OBJECT_0, WAIT_ABANDONED = 0x0, 0x80
CABECALHO = 32          # DWORD maxSize + 7 int32


CLSID_MF = "{65A67FFA-DE61-49B4-9549-9A91B6AB97D0}"   # camera do Windows 11 (camera_mf/)


def _registrada(clsid):
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\InprocServer32"):
            return True
    except OSError:
        return False


def instalada():
    """A DLL da camera (DirectShow) esta registrada no Windows?"""
    return _registrada(CLSID)


def instalada_mf():
    """A camera do Windows 11 (Media Foundation) esta registrada?"""
    return _registrada(CLSID_MF)


class CameraPropria:
    """Mesma interface que o pyvirtualcam.Camera usada pelo motor."""

    def __init__(self, largura, altura, fps=30, prefixo="OpenBokehCam_", global_=False):
        """prefixo/global_: a camera do Windows 11 roda dentro do servico de
        camera do Windows (outra sessao), entao usa nomes globais
        ("Global\\OpenBokehMF_...") e la quem cria o evento "Want" e a DLL."""
        self.width, self.height, self.fps = largura, altura, fps
        self.device = NOME
        self._nomes = {k: (prefixo + k).encode() for k in ("Mutx", "Want", "Sent", "Data")}
        self._global = global_
        self._mutex = self._want = self._sent = self._mapa = None
        self._ptr = None
        self._tentativa = 0.0
        self._rgba = np.empty((altura, largura, 4), np.uint8)
        self._ultimo_pedido = 0.0      # ultima vez que algum programa pediu quadro

    # -- conexao com a camera (so existe enquanto algum programa a usa)
    def _abrir(self):
        agora = time.monotonic()
        if agora - self._tentativa < 0.5:       # nao tenta a cada quadro
            return False
        self._tentativa = agora
        # Handshake em etapas (igual ao original): a camera cria o mutex; nos
        # criamos o evento "Want"; so DEPOIS de ver o "Want" a camera cria o
        # "Sent" e a memoria. Por isso o que ja foi aberto fica guardado entre
        # tentativas; fechar o "Want" aqui faria os dois esperarem para sempre.
        if not self._mutex:
            self._mutex = _k32.OpenMutexA(SYNCHRONIZE, False, self._nomes["Mutx"])
            if not self._mutex:
                return False
        r = _k32.WaitForSingleObject(self._mutex, 200)
        if r not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            return False
        try:
            if not self._want:
                if self._global:
                    self._want = _k32.OpenEventA(EVENT_MODIFY_STATE | SYNCHRONIZE, False, self._nomes["Want"])
                else:
                    self._want = _k32.CreateEventA(None, False, False, self._nomes["Want"])
                if not self._want:
                    return False
            if not self._sent:
                self._sent = _k32.OpenEventA(EVENT_MODIFY_STATE, False, self._nomes["Sent"])
                if not self._sent:
                    return False
            if not self._mapa:
                self._mapa = _k32.OpenFileMappingA(FILE_MAP_WRITE, False, self._nomes["Data"])
                if not self._mapa:
                    return False
            self._ptr = _k32.MapViewOfFile(self._mapa, FILE_MAP_WRITE, 0, 0, 0) or None
            if self._ptr is not None:
                self._ultimo_pedido = time.monotonic()
            return self._ptr is not None
        finally:
            _k32.ReleaseMutex(self._mutex)

    def preparar(self, rgb):
        """RGB -> RGBA de baixo para cima (o formato que as duas cameras leem)."""
        if self._rgba.shape[:2] != rgb.shape[:2]:
            self._rgba = np.empty((rgb.shape[0], rgb.shape[1], 4), np.uint8)
        cv2.cvtColor(cv2.flip(rgb, 0), cv2.COLOR_RGB2RGBA, dst=self._rgba)
        return self._rgba

    def send(self, rgb):
        if self._ptr is None and not self._abrir():
            return
        self.enviar_rgba(self.preparar(rgb))

    def enviar_rgba(self, rgba):
        if self._ptr is None and not self._abrir():
            return
        h, w = rgba.shape[:2]
        tam = w * h * 4
        cab = (ctypes.c_int32 * 8).from_address(self._ptr)
        if ctypes.c_uint32.from_address(self._ptr).value < tam:
            return
        if _k32.WaitForSingleObject(self._mutex, 100) not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            return
        try:
            cab[1], cab[2], cab[3] = w, h, w     # largura, altura, passo (em pixels)
            cab[4] = 0                           # formato: RGBA 8 bits
            cab[5] = 1                           # redimensiona se o app pedir outra resolucao
            cab[6] = 0                           # sem espelho
            cab[7] = 1500                        # ms sem quadro ate mostrar a tela de espera
            ctypes.memmove(self._ptr + CABECALHO, rgba.ctypes.data, tam)
        finally:
            _k32.ReleaseMutex(self._mutex)
        _k32.SetEvent(self._sent)
        self._anotar_pedido()

    # -- algum programa (Meet, Zoom, OBS...) esta usando a camera agora?
    def _anotar_pedido(self):
        # a DLL sinaliza o evento "Want" a cada quadro que o programa pede
        if self._want and _k32.WaitForSingleObject(self._want, 0) == WAIT_OBJECT_0:
            self._ultimo_pedido = time.monotonic()

    def verificar_consumidor(self):
        """Chamado periodicamente quando nao estamos enviando (modo espera)."""
        if self._ptr is None:
            self._abrir()
        else:
            self._anotar_pedido()

    def consumidor_ativo(self, segundos=3.0):
        return time.monotonic() - self._ultimo_pedido < segundos

    def sleep_until_next_frame(self):
        time.sleep(1 / self.fps)

    def close(self):
        if self._ptr:
            _k32.UnmapViewOfFile(self._ptr)
        for h in (self._want, self._sent, self._mapa, self._mutex):
            if h:
                _k32.CloseHandle(h)
        self._ptr = self._mutex = self._want = self._sent = self._mapa = None


class Conjunto:
    """Envia o mesmo quadro para varias cameras (a DirectShow, vista pelo Chrome,
    Zoom, OBS..., e a do Windows 11, vista pelo app Camera, Store e novo Teams),
    preparando a imagem uma vez so."""

    def __init__(self, cameras):
        self.cameras = cameras
        self.width, self.height, self.fps = cameras[0].width, cameras[0].height, cameras[0].fps
        self.device = NOME

    def send(self, rgb):
        rgba = self.cameras[0].preparar(rgb)
        for c in self.cameras:
            c.enviar_rgba(rgba)

    def verificar_consumidor(self):
        for c in self.cameras:
            c.verificar_consumidor()

    def consumidor_ativo(self, segundos=3.0):
        return any(c.consumidor_ativo(segundos) for c in self.cameras)

    def sleep_until_next_frame(self):
        time.sleep(1 / self.fps)

    def close(self):
        for c in self.cameras:
            c.close()


def criar(largura, altura, fps=30):
    """Todas as cameras proprias instaladas neste computador."""
    cams = []
    if instalada():
        cams.append(CameraPropria(largura, altura, fps))
    if instalada_mf():
        cams.append(CameraPropria(largura, altura, fps, prefixo="Global\\OpenBokehMF_", global_=True))
    if not cams:
        return None
    return cams[0] if len(cams) == 1 else Conjunto(cams)
