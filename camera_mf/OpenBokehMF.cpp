/*
  OpenBokeh Camera (Windows 11 / Media Foundation)

  Camera virtual no padrao novo do Windows 11 (MFCreateVirtualCamera). E vista
  pelo app Camera do Windows, apps da Microsoft Store, o novo Teams e qualquer
  programa que use Media Foundation / Windows.Media.Capture.

  Como funciona:
  - Esta DLL e uma "fonte de midia" (IMFMediaSource). Quem a carrega e o
    servico de camera do Windows (Frame Server, conta LocalService, sessao 0).
  - O app OpenBokeh (sessao do usuario) escreve os quadros numa memoria
    compartilhada GLOBAL criada aqui, com permissoes explicitas (servico +
    usuario interativo). O formato e o mesmo da camera DirectShow: cabecalho de
    32 bytes + imagem RGBA de baixo para cima.
  - Sem quadros do app, mostramos a tela "OpenBokeh esta fechado".

  Copyright (c) 2026 Projeto OpenBokeh - GPL-3.0-or-later
*/
#define WIN32_LEAN_AND_MEAN
#include <initguid.h>
#include <windows.h>
#include <sddl.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mferror.h>
#include <ks.h>
#include <ksmedia.h>
#include <new>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>

// ---------------------------------------------------------------- definicoes que o MinGW nao tem
// (valores oficiais, conferidos nos metadados da Microsoft)
DEFINE_GUID(OB_MF_DEVICESTREAM_STREAM_CATEGORY, 0x2939e7b8, 0xa62e, 0x4579, 0xb6, 0x74, 0xd4, 0x07, 0x3d, 0xfa, 0xbb, 0xba);
DEFINE_GUID(OB_MF_DEVICESTREAM_STREAM_ID, 0x11bd5120, 0xd124, 0x446b, 0x88, 0xe6, 0x17, 0x06, 0x02, 0x57, 0xff, 0xf9);
DEFINE_GUID(OB_MF_DEVICESTREAM_FRAMESERVER_SHARED, 0x1cb378e9, 0xb279, 0x41d4, 0xaf, 0x97, 0x34, 0xa2, 0x43, 0xe6, 0x83, 0x20);
DEFINE_GUID(OB_MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES, 0x17145fd1, 0x1b2b, 0x423c, 0x80, 0x01, 0x2b, 0x68, 0x33, 0xed, 0x35, 0x88);
DEFINE_GUID(OB_PINNAME_VIDEO_CAPTURE, 0xfb6c4281, 0x0353, 0x11d1, 0x90, 0x5f, 0x00, 0x00, 0xc0, 0xcc, 0x16, 0xba);
DEFINE_GUID(OB_IID_IMFMediaStream2, 0xc5bc37d6, 0x75c7, 0x46a1, 0xa1, 0x32, 0x81, 0xb5, 0xf7, 0x23, 0xc2, 0x0f);
DEFINE_GUID(OB_IID_IKsControl, 0x28f54685, 0x06fd, 0x11d2, 0xb2, 0x7a, 0x00, 0xa0, 0xc9, 0x22, 0x31, 0x96);
DEFINE_GUID(OB_IID_IMFSampleAllocatorControl, 0xda62b958, 0x3a38, 0x4a97, 0xbd, 0x27, 0x14, 0x9c, 0x64, 0x0c, 0x07, 0x71);
DEFINE_GUID(OB_IID_IMFVirtualCamera, 0x1c08a864, 0xef6c, 0x4c75, 0xaf, 0x59, 0x5f, 0x2d, 0x68, 0xda, 0x95, 0x63);
// identificador desta fonte de midia (proprio do OpenBokeh)
DEFINE_GUID(CLSID_OpenBokehMF, 0x65a67ffa, 0xde61, 0x49b4, 0x95, 0x49, 0x9a, 0x91, 0xb6, 0xab, 0x97, 0xd0);
#define CLSID_TEXTO L"{65A67FFA-DE61-49B4-9549-9A91B6AB97D0}"
#define NOME_CAMERA L"OpenBokeh Camera"

enum { OB_MFFrameSourceTypes_Color = 1 };

struct IObKsControl : IUnknown {
    virtual HRESULT STDMETHODCALLTYPE KsProperty(PKSPROPERTY, ULONG, LPVOID, ULONG, ULONG*) = 0;
    virtual HRESULT STDMETHODCALLTYPE KsMethod(PKSMETHOD, ULONG, LPVOID, ULONG, ULONG*) = 0;
    virtual HRESULT STDMETHODCALLTYPE KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG*) = 0;
};

// IMFSampleAllocatorControl: o servico pergunta quem aloca os quadros
struct IObMFSampleAllocatorControl : IUnknown {
    virtual HRESULT STDMETHODCALLTYPE SetDefaultAllocator(DWORD, IUnknown*) = 0;
    virtual HRESULT STDMETHODCALLTYPE GetAllocatorUsage(DWORD, DWORD*, int*) = 0;
};
enum { OB_MFSampleAllocatorUsage_UsesCustomAllocator = 1 };

// ---- registro de diagnostico (so quando a variavel OB_LOG existir no ambiente do servico
// ou o arquivo C:\ProgramData\OpenBokehTeste\log.ativo existir)
static void Log(const char* fmt, ...) {
    static int ativo = -1;
    if (ativo < 0) ativo = GetFileAttributesW(L"C:\\ProgramData\\OpenBokehTeste\\log.ativo") != INVALID_FILE_ATTRIBUTES;
    if (!ativo) return;
    char linha[512];
    va_list ap; va_start(ap, fmt);
    int n = wvsprintfA(linha, fmt, ap);
    va_end(ap);
    HANDLE f = CreateFileW(L"C:\\ProgramData\\OpenBokehTeste\\mf_log.txt", FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                           NULL, OPEN_ALWAYS, 0, NULL);
    if (f != INVALID_HANDLE_VALUE) { DWORD w; WriteFile(f, linha, n, &w, NULL); WriteFile(f, "\r\n", 2, &w, NULL); CloseHandle(f); }
}
static void LogIID(const char* onde, REFIID r) {
    Log("%s: QI nao suportada {%08lX-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X}", onde, r.Data1, r.Data2, r.Data3,
        r.Data4[0], r.Data4[1], r.Data4[2], r.Data4[3], r.Data4[4], r.Data4[5], r.Data4[6], r.Data4[7]);
}

struct IObMFMediaStream2 : IMFMediaStream {
    virtual HRESULT STDMETHODCALLTYPE SetStreamState(MF_STREAM_STATE) = 0;
    virtual HRESULT STDMETHODCALLTYPE GetStreamState(MF_STREAM_STATE*) = 0;
};

struct IObMFVirtualCamera : IMFAttributes {
    virtual HRESULT STDMETHODCALLTYPE AddDeviceSourceInfo(LPCWSTR) = 0;
    virtual HRESULT STDMETHODCALLTYPE AddProperty(const void*, ULONG, const BYTE*, ULONG) = 0;
    virtual HRESULT STDMETHODCALLTYPE AddRegistryEntry(LPCWSTR, LPCWSTR, DWORD, const BYTE*, ULONG) = 0;
    virtual HRESULT STDMETHODCALLTYPE Start(IMFAsyncCallback*) = 0;
    virtual HRESULT STDMETHODCALLTYPE Stop() = 0;
    virtual HRESULT STDMETHODCALLTYPE Remove() = 0;
    virtual HRESULT STDMETHODCALLTYPE GetMediaSource(IMFMediaSource**) = 0;
    virtual HRESULT STDMETHODCALLTYPE SendCameraProperty(const GUID*, ULONG, ULONG, void*, ULONG, void*, ULONG, ULONG*) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateSyncEvent(const GUID*, ULONG, ULONG, HANDLE, void**) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateSyncSemaphore(const GUID*, ULONG, ULONG, HANDLE, LONG, void**) = 0;
    virtual HRESULT STDMETHODCALLTYPE Shutdown() = 0;
};
typedef HRESULT (WINAPI *PFN_MFCreateVirtualCamera)(int, int, int, LPCWSTR, LPCWSTR, const GUID*, ULONG, IObMFVirtualCamera**);

static HMODULE g_modulo = NULL;
static volatile LONG g_objetos = 0;

template <class T> static void Liberar(T*& p) { if (p) { p->Release(); p = NULL; } }

// ---------------------------------------------------------------- memoria compartilhada (receptor)
// Mesmo cabecalho da camera DirectShow (camera_virtual/shared.inl)
struct Cabecalho { DWORD maxSize; int width, height, stride, format, resizemode, mirrormode, timeout; };
static const DWORD MAX_IMAGEM = 1920 * 1080 * 4;                 // ate Full HD RGBA

class Receptor {
public:
    Receptor() : m_mutex(NULL), m_want(NULL), m_sent(NULL), m_mapa(NULL), m_buf(NULL) {}
    ~Receptor() {
        if (m_buf) UnmapViewOfFile(m_buf);
        HANDLE hs[] = { m_mapa, m_sent, m_want, m_mutex };
        for (HANDLE h : hs) if (h) CloseHandle(h);
    }
    // Cria os objetos no espaco GLOBAL com permissao para: sistema, administradores,
    // o servico de camera (LocalService) e o usuario interativo (o app OpenBokeh).
    bool Abrir() {
        if (m_buf) return true;
        SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, FALSE };
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
                L"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;LS)(A;;GA;;;IU)", SDDL_REVISION_1,
                &sa.lpSecurityDescriptor, NULL))
            return false;
        if (!m_mutex) m_mutex = CreateMutexW(&sa, FALSE, L"Global\\OpenBokehMF_Mutx");
        if (!m_want)  m_want  = CreateEventW(&sa, FALSE, FALSE, L"Global\\OpenBokehMF_Want");
        if (!m_sent)  m_sent  = CreateEventW(&sa, FALSE, FALSE, L"Global\\OpenBokehMF_Sent");
        if (!m_mapa)  m_mapa  = CreateFileMappingW(INVALID_HANDLE_VALUE, &sa, PAGE_READWRITE, 0,
                                                   sizeof(Cabecalho) + MAX_IMAGEM, L"Global\\OpenBokehMF_Data");
        LocalFree(sa.lpSecurityDescriptor);
        if (!m_mutex || !m_want || !m_sent || !m_mapa) return false;
        m_buf = (uint8_t*)MapViewOfFile(m_mapa, FILE_MAP_ALL_ACCESS, 0, 0, 0);
        if (!m_buf) return false;
        ((Cabecalho*)m_buf)->maxSize = MAX_IMAGEM;
        return true;
    }
    // Copia o quadro mais novo (RGBA, de baixo para cima) se for valido.
    // Devolve true se ha imagem do app (nova ou recente).
    bool Receber(uint8_t* destino, int& w, int& h, ULONGLONG& ultimo) {
        if (!Abrir()) return false;
        SetEvent(m_want);
        bool novo = WaitForSingleObject(m_sent, 40) == WAIT_OBJECT_0;
        DWORD r = WaitForSingleObject(m_mutex, 100);
        if (r != WAIT_OBJECT_0 && r != WAIT_ABANDONED) return false;
        Cabecalho c = *(Cabecalho*)m_buf;
        bool ok = c.format == 0 && c.width > 0 && c.height > 0 && c.width <= 1920 && c.height <= 1080 &&
                  c.stride == c.width && (size_t)c.width * c.height * 4 <= MAX_IMAGEM;
        if (ok && novo) {
            memcpy(destino, m_buf + sizeof(Cabecalho), (size_t)c.width * c.height * 4);
            w = c.width; h = c.height;
            ultimo = GetTickCount64();
        }
        ReleaseMutex(m_mutex);
        return ok && ultimo && GetTickCount64() - ultimo < 1500;
    }
private:
    HANDLE m_mutex, m_want, m_sent, m_mapa;
    uint8_t* m_buf;
};

// ---------------------------------------------------------------- imagem
static void TelaEspera(uint8_t* bgra, int W, int H) {
    // fundo escuro com luzes desfocadas + texto (mesma identidade da camera DirectShow)
    BITMAPINFO bmi; ZeroMemory(&bmi, sizeof(bmi));
    bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bmi.bmiHeader.biWidth = W; bmi.bmiHeader.biHeight = -H;      // de cima para baixo
    bmi.bmiHeader.biPlanes = 1; bmi.bmiHeader.biBitCount = 32; bmi.bmiHeader.biCompression = BI_RGB;
    void* bits = NULL;
    HDC dc = CreateCompatibleDC(0);
    HBITMAP bmp = dc ? CreateDIBSection(dc, &bmi, DIB_RGB_COLORS, &bits, NULL, 0) : NULL;
    if (!bmp || !bits) {
        if (bmp) DeleteObject(bmp);
        if (dc) DeleteDC(dc);
        memset(bgra, 0, (size_t)W * H * 4);
        return;
    }
    HGDIOBJ antigo = SelectObject(dc, bmp);
    RECT r = { 0, 0, W, H };
    HBRUSH fundo = CreateSolidBrush(RGB(13, 10, 24)); FillRect(dc, &r, fundo); DeleteObject(fundo);
    struct { int x, y, raio; COLORREF cor; } luzes[] = {
        { W * 18 / 100, H * 28 / 100, H / 4, RGB(38, 28, 86) }, { W * 82 / 100, H * 24 / 100, H / 5, RGB(70, 22, 54) },
        { W * 78 / 100, H * 78 / 100, H / 4, RGB(14, 58, 70) }, { W * 22 / 100, H * 80 / 100, H / 6, RGB(66, 48, 22) } };
    HGDIOBJ caneta = SelectObject(dc, GetStockObject(NULL_PEN));
    for (auto& l : luzes) {
        HBRUSH b = CreateSolidBrush(l.cor); HGDIOBJ ba = SelectObject(dc, b);
        Ellipse(dc, l.x - l.raio, l.y - l.raio, l.x + l.raio, l.y + l.raio);
        SelectObject(dc, ba); DeleteObject(b);
    }
    SelectObject(dc, caneta);
    SetBkMode(dc, TRANSPARENT);
    HFONT f1 = CreateFontW(-(H / 13), 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    HFONT f2 = CreateFontW(-(H / 26), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    HGDIOBJ fa = SelectObject(dc, f1);
    SetTextColor(dc, RGB(238, 235, 250));
    RECT t1 = { 0, H / 2 - H / 9, W, H / 2 };
    DrawTextW(dc, (((GetSystemDefaultUILanguage() & 0x3FF) == 0x16) ? L"OpenBokeh est\u00e1 fechado" : L"OpenBokeh is closed"), -1, &t1, DT_CENTER | DT_BOTTOM | DT_SINGLELINE);
    SelectObject(dc, f2);
    SetTextColor(dc, RGB(156, 149, 190));
    RECT t2 = { 0, H / 2 + H / 40, W, H / 2 + H / 8 };
    DrawTextW(dc, (((GetSystemDefaultUILanguage() & 0x3FF) == 0x16) ? L"Abra o OpenBokeh para ligar a c\u00e2mera" : L"Open OpenBokeh to turn on the camera"), -1, &t2, DT_CENTER | DT_TOP | DT_SINGLELINE);
    SelectObject(dc, fa); DeleteObject(f1); DeleteObject(f2);
    GdiFlush();
    memcpy(bgra, bits, (size_t)W * H * 4);
    for (size_t i = 3; i < (size_t)W * H * 4; i += 4) bgra[i] = 255;
    SelectObject(dc, antigo); DeleteObject(bmp); DeleteDC(dc);
}

// RGBA de baixo para cima (iw x ih) -> BGRA de cima para baixo (ow x oh), bilinear "cobrindo" o quadro
static void ConverterRGBA(const uint8_t* src, int iw, int ih, uint8_t* dst, int ow, int oh) {
    const double esc = (double)iw / ow < (double)ih / oh ? (double)iw / ow : (double)ih / oh;
    const double ox = (iw - ow * esc) / 2.0, oy = (ih - oh * esc) / 2.0;
    for (int y = 0; y < oh; y++) {
        double fy = oy + (y + 0.5) * esc - 0.5;
        if (fy < 0) fy = 0;
        if (fy > ih - 1) fy = ih - 1;
        const int y0 = (int)fy, y1 = y0 + 1 < ih ? y0 + 1 : y0, wy = (int)((fy - y0) * 256);
        // origem esta de baixo para cima
        const uint8_t* l0 = src + (size_t)(ih - 1 - y0) * iw * 4;
        const uint8_t* l1 = src + (size_t)(ih - 1 - y1) * iw * 4;
        uint8_t* d = dst + (size_t)y * ow * 4;
        for (int x = 0; x < ow; x++, d += 4) {
            double fx = ox + (x + 0.5) * esc - 0.5;
            if (fx < 0) fx = 0;
            if (fx > iw - 1) fx = iw - 1;
            const int x0 = (int)fx, x1 = x0 + 1 < iw ? x0 + 1 : x0, wx = (int)((fx - x0) * 256);
            const uint8_t *a = l0 + x0 * 4, *b = l0 + x1 * 4, *c = l1 + x0 * 4, *e = l1 + x1 * 4;
            for (int k = 0; k < 3; k++) {     // RGBA -> BGRA
                int cima = a[k] * (256 - wx) + b[k] * wx, baixo = c[k] * (256 - wx) + e[k] * wx;
                d[2 - k] = (uint8_t)((cima * (256 - wy) + baixo * wy + 32768) >> 16);
            }
            d[3] = 255;
        }
    }
}

// BGRA -> NV12 (BT.601, faixa limitada), o formato preferido das cameras no Windows
static void BGRAparaNV12(const uint8_t* bgra, int W, int H, uint8_t* nv12) {
    uint8_t* Y = nv12;
    uint8_t* UV = nv12 + (size_t)W * H;
    for (int y = 0; y < H; y++) {
        const uint8_t* p = bgra + (size_t)y * W * 4;
        for (int x = 0; x < W; x++, p += 4)
            Y[(size_t)y * W + x] = (uint8_t)(((66 * p[2] + 129 * p[1] + 25 * p[0] + 128) >> 8) + 16);
    }
    for (int y = 0; y < H; y += 2) {
        for (int x = 0; x < W; x += 2) {
            int r = 0, g = 0, b = 0;
            for (int dy = 0; dy < 2; dy++)
                for (int dx = 0; dx < 2; dx++) {
                    const uint8_t* p = bgra + ((size_t)(y + dy) * W + x + dx) * 4;
                    b += p[0]; g += p[1]; r += p[2];
                }
            r >>= 2; g >>= 2; b >>= 2;
            uint8_t* uv = UV + (size_t)(y / 2) * W + x;
            uv[0] = (uint8_t)(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
            uv[1] = (uint8_t)(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
        }
    }
}

// ---------------------------------------------------------------- stream
class Fonte;

class Stream : public IObMFMediaStream2, public IObKsControl {
public:
    Stream(Fonte* fonte, IMFStreamDescriptor* sd) : m_ref(1), m_fonte(fonte), m_sd(sd), m_fila(NULL),
        m_estado(MF_STREAM_STATE_STOPPED), m_desligado(false), m_rgba(NULL), m_bgra(NULL), m_iw(0), m_ih(0), m_ultimo(0) {
        InterlockedIncrement(&g_objetos);
        InitializeCriticalSection(&m_cs);
        m_sd->AddRef();
        MFCreateEventQueue(&m_fila);
        m_rgba = new (std::nothrow) uint8_t[MAX_IMAGEM];
        m_bgra = new (std::nothrow) uint8_t[MAX_IMAGEM];
    }
    virtual ~Stream() {
        Liberar(m_sd); Liberar(m_fila);
        delete[] m_rgba; delete[] m_bgra;
        DeleteCriticalSection(&m_cs);
        InterlockedDecrement(&g_objetos);
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator || riid == IID_IMFMediaStream || riid == OB_IID_IMFMediaStream2)
            *ppv = static_cast<IObMFMediaStream2*>(this);
        else if (riid == OB_IID_IKsControl) *ppv = static_cast<IObKsControl*>(this);
        else { *ppv = NULL; LogIID("Stream", riid); return E_NOINTERFACE; }
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&m_ref); if (!r) delete this; return r; }

    // IMFMediaEventGenerator
    STDMETHODIMP GetEvent(DWORD f, IMFMediaEvent** e) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->GetEvent(f, e); q->Release(); return hr; }
    STDMETHODIMP BeginGetEvent(IMFAsyncCallback* cb, IUnknown* st) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->BeginGetEvent(cb, st); q->Release(); return hr; }
    STDMETHODIMP EndGetEvent(IMFAsyncResult* r, IMFMediaEvent** e) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->EndGetEvent(r, e); q->Release(); return hr; }
    STDMETHODIMP QueueEvent(MediaEventType t, REFGUID g, HRESULT s, const PROPVARIANT* v) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->QueueEventParamVar(t, g, s, v); q->Release(); return hr; }

    // IMFMediaStream
    STDMETHODIMP GetMediaSource(IMFMediaSource** pp) override;
    STDMETHODIMP GetStreamDescriptor(IMFStreamDescriptor** pp) override {
        if (!pp) return E_POINTER;
        EnterCriticalSection(&m_cs);
        HRESULT hr = m_desligado ? MF_E_SHUTDOWN : S_OK;
        if (SUCCEEDED(hr)) { *pp = m_sd; m_sd->AddRef(); }
        LeaveCriticalSection(&m_cs);
        return hr;
    }
    STDMETHODIMP RequestSample(IUnknown* token) override {
        EnterCriticalSection(&m_cs);
        HRESULT hr = S_OK;
        IMFSample* amostra = NULL;
        if (m_desligado) hr = MF_E_SHUTDOWN;
        else if (m_estado != MF_STREAM_STATE_RUNNING) hr = MF_E_INVALIDREQUEST;
        if (SUCCEEDED(hr)) hr = GerarAmostra(&amostra);
        if (SUCCEEDED(hr) && token) hr = amostra->SetUnknown(MFSampleExtension_Token, token);
        if (SUCCEEDED(hr)) hr = m_fila->QueueEventParamUnk(MEMediaSample, GUID_NULL, S_OK, amostra);
        Liberar(amostra);
        LeaveCriticalSection(&m_cs);
        return hr;
    }

    // IMFMediaStream2
    STDMETHODIMP SetStreamState(MF_STREAM_STATE st) override {
        EnterCriticalSection(&m_cs);
        bool mudou = st != m_estado;
        m_estado = st;
        LeaveCriticalSection(&m_cs);
        if (mudou) {
            if (st == MF_STREAM_STATE_RUNNING) return QueueEvent(MEStreamStarted, GUID_NULL, S_OK, NULL);
            if (st == MF_STREAM_STATE_STOPPED) return QueueEvent(MEStreamStopped, GUID_NULL, S_OK, NULL);
        }
        return S_OK;
    }
    STDMETHODIMP GetStreamState(MF_STREAM_STATE* st) override {
        if (!st) return E_POINTER;
        EnterCriticalSection(&m_cs); *st = m_estado; LeaveCriticalSection(&m_cs);
        return S_OK;
    }

    // IKsControl: nenhuma propriedade de hardware
    STDMETHODIMP KsProperty(PKSPROPERTY, ULONG, LPVOID, ULONG, ULONG*) override { return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND); }
    STDMETHODIMP KsMethod(PKSMETHOD, ULONG, LPVOID, ULONG, ULONG*) override { return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND); }
    STDMETHODIMP KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG*) override { return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND); }

    HRESULT Iniciar() { return SetStreamState(MF_STREAM_STATE_RUNNING); }
    HRESULT Parar() { return SetStreamState(MF_STREAM_STATE_STOPPED); }
    void Desligar() {
        EnterCriticalSection(&m_cs);
        m_desligado = true;
        if (m_fila) m_fila->Shutdown();
        LeaveCriticalSection(&m_cs);
    }

private:
    IMFMediaEventQueue* Fila() {
        EnterCriticalSection(&m_cs);
        IMFMediaEventQueue* q = m_desligado ? NULL : m_fila;
        if (q) q->AddRef();
        LeaveCriticalSection(&m_cs);
        return q;
    }

    HRESULT GerarAmostra(IMFSample** saida) {
        if (!m_rgba || !m_bgra) return E_OUTOFMEMORY;
        IMFMediaTypeHandler* mh = NULL; IMFMediaType* mt = NULL;
        HRESULT hr = m_sd->GetMediaTypeHandler(&mh);
        if (SUCCEEDED(hr)) hr = mh->GetCurrentMediaType(&mt);
        UINT32 W = 1280, H = 720;
        GUID sub = MFVideoFormat_NV12;
        if (SUCCEEDED(hr)) { MFGetAttributeSize(mt, MF_MT_FRAME_SIZE, &W, &H); mt->GetGUID(MF_MT_SUBTYPE, &sub); }
        Liberar(mt); Liberar(mh);
        if (FAILED(hr)) return hr;
        if (W > 1920 || H > 1080 || (W & 1) || (H & 1)) return MF_E_INVALIDMEDIATYPE;

        if (m_receptor.Receber(m_rgba, m_iw, m_ih, m_ultimo) && m_iw > 0)
            ConverterRGBA(m_rgba, m_iw, m_ih, m_bgra, (int)W, (int)H);
        else
            TelaEspera(m_bgra, (int)W, (int)H);

        const bool nv12 = (sub == MFVideoFormat_NV12);
        const DWORD tam = nv12 ? W * H * 3 / 2 : W * H * 4;
        IMFMediaBuffer* buf = NULL; IMFSample* s = NULL;
        hr = MFCreateMemoryBuffer(tam, &buf);
        BYTE* p = NULL;
        if (SUCCEEDED(hr)) hr = buf->Lock(&p, NULL, NULL);
        if (SUCCEEDED(hr)) {
            if (nv12) BGRAparaNV12(m_bgra, (int)W, (int)H, p);
            else memcpy(p, m_bgra, tam);
            buf->Unlock();
            hr = buf->SetCurrentLength(tam);
        }
        if (SUCCEEDED(hr)) hr = MFCreateSample(&s);
        if (SUCCEEDED(hr)) hr = s->AddBuffer(buf);
        if (SUCCEEDED(hr)) hr = s->SetSampleTime(MFGetSystemTime());
        if (SUCCEEDED(hr)) hr = s->SetSampleDuration(333333);
        Liberar(buf);
        if (FAILED(hr)) { Liberar(s); return hr; }
        *saida = s;
        return S_OK;
    }

    volatile LONG m_ref;
    Fonte* m_fonte;
    IMFStreamDescriptor* m_sd;
    IMFMediaEventQueue* m_fila;
    MF_STREAM_STATE m_estado;
    bool m_desligado;
    CRITICAL_SECTION m_cs;
    Receptor m_receptor;
    uint8_t *m_rgba, *m_bgra;
    int m_iw, m_ih;
    ULONGLONG m_ultimo;
};

// ---------------------------------------------------------------- fonte de midia
class Fonte : public IMFMediaSourceEx, public IMFGetService, public IObKsControl, public IObMFSampleAllocatorControl {
public:
    Fonte() : m_ref(1), m_fila(NULL), m_pd(NULL), m_attr(NULL), m_stream(NULL), m_desligado(false), m_iniciado(false) {
        InterlockedIncrement(&g_objetos);
        InitializeCriticalSection(&m_cs);
    }
    virtual ~Fonte() {
        Liberar(m_stream); Liberar(m_pd); Liberar(m_attr); Liberar(m_fila);
        DeleteCriticalSection(&m_cs);
        InterlockedDecrement(&g_objetos);
    }

    HRESULT Inicializar() {
        HRESULT hr = MFCreateEventQueue(&m_fila);
        if (SUCCEEDED(hr)) hr = MFCreateAttributes(&m_attr, 4);
        // tipos oferecidos: NV12 e RGB32, em 720p e 1080p, 30 fps
        IMFMediaType* tipos[4] = {};
        const GUID subs[2] = { MFVideoFormat_NV12, MFVideoFormat_RGB32 };
        const UINT32 tamanhos[2][2] = { { 1280, 720 }, { 1920, 1080 } };
        int n = 0;
        for (int t = 0; t < 2 && SUCCEEDED(hr); t++)
            for (int s = 0; s < 2 && SUCCEEDED(hr); s++) {
                IMFMediaType* mt = NULL;
                hr = MFCreateMediaType(&mt);
                if (SUCCEEDED(hr)) hr = mt->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
                if (SUCCEEDED(hr)) hr = mt->SetGUID(MF_MT_SUBTYPE, subs[s]);
                if (SUCCEEDED(hr)) hr = MFSetAttributeSize(mt, MF_MT_FRAME_SIZE, tamanhos[t][0], tamanhos[t][1]);
                if (SUCCEEDED(hr)) hr = MFSetAttributeRatio(mt, MF_MT_FRAME_RATE, 30, 1);
                if (SUCCEEDED(hr)) hr = MFSetAttributeRatio(mt, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
                if (SUCCEEDED(hr)) hr = mt->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
                if (SUCCEEDED(hr)) hr = mt->SetUINT32(MF_MT_ALL_SAMPLES_INDEPENDENT, TRUE);
                if (SUCCEEDED(hr)) hr = mt->SetUINT32(MF_MT_DEFAULT_STRIDE, s == 0 ? tamanhos[t][0] : tamanhos[t][0] * 4);
                if (SUCCEEDED(hr)) tipos[n++] = mt; else Liberar(mt);
            }
        IMFStreamDescriptor* sd = NULL;
        if (SUCCEEDED(hr)) hr = MFCreateStreamDescriptor(0, n, tipos, &sd);
        IMFMediaTypeHandler* mh = NULL;
        if (SUCCEEDED(hr)) hr = sd->GetMediaTypeHandler(&mh);
        if (SUCCEEDED(hr)) hr = mh->SetCurrentMediaType(tipos[0]);
        Liberar(mh);
        if (SUCCEEDED(hr)) hr = sd->SetGUID(OB_MF_DEVICESTREAM_STREAM_CATEGORY, OB_PINNAME_VIDEO_CAPTURE);
        if (SUCCEEDED(hr)) hr = sd->SetUINT32(OB_MF_DEVICESTREAM_STREAM_ID, 0);
        if (SUCCEEDED(hr)) hr = sd->SetUINT32(OB_MF_DEVICESTREAM_FRAMESERVER_SHARED, 1);
        if (SUCCEEDED(hr)) hr = sd->SetUINT32(OB_MF_DEVICESTREAM_ATTRIBUTE_FRAMESOURCE_TYPES, OB_MFFrameSourceTypes_Color);
        if (SUCCEEDED(hr)) hr = MFCreatePresentationDescriptor(1, &sd, &m_pd);
        if (SUCCEEDED(hr)) hr = m_pd->SelectStream(0);
        if (SUCCEEDED(hr)) {
            m_stream = new (std::nothrow) Stream(this, sd);
            if (!m_stream) hr = E_OUTOFMEMORY;
        }
        Liberar(sd);
        for (int i = 0; i < n; i++) Liberar(tipos[i]);
        return hr;
    }

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFMediaEventGenerator || riid == IID_IMFMediaSource || riid == IID_IMFMediaSourceEx)
            *ppv = static_cast<IMFMediaSourceEx*>(this);
        else if (riid == IID_IMFGetService) *ppv = static_cast<IMFGetService*>(this);
        else if (riid == OB_IID_IKsControl) *ppv = static_cast<IObKsControl*>(this);
        else if (riid == OB_IID_IMFSampleAllocatorControl) *ppv = static_cast<IObMFSampleAllocatorControl*>(this);
        else { *ppv = NULL; LogIID("Fonte", riid); return E_NOINTERFACE; }
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&m_ref); if (!r) delete this; return r; }

    // IMFSampleAllocatorControl: nos mesmos alocamos os quadros (memoria comum)
    STDMETHODIMP SetDefaultAllocator(DWORD, IUnknown*) override { return S_OK; }
    STDMETHODIMP GetAllocatorUsage(DWORD id, DWORD* entrada, int* uso) override {
        if (!entrada || !uso) return E_POINTER;
        if (id != 0) return MF_E_INVALIDSTREAMNUMBER;
        *entrada = 0;
        *uso = OB_MFSampleAllocatorUsage_UsesCustomAllocator;
        return S_OK;
    }

    // IMFMediaEventGenerator
    STDMETHODIMP GetEvent(DWORD f, IMFMediaEvent** e) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->GetEvent(f, e); q->Release(); return hr; }
    STDMETHODIMP BeginGetEvent(IMFAsyncCallback* cb, IUnknown* st) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->BeginGetEvent(cb, st); q->Release(); return hr; }
    STDMETHODIMP EndGetEvent(IMFAsyncResult* r, IMFMediaEvent** e) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->EndGetEvent(r, e); q->Release(); return hr; }
    STDMETHODIMP QueueEvent(MediaEventType t, REFGUID g, HRESULT s, const PROPVARIANT* v) override { IMFMediaEventQueue* q = Fila(); if (!q) return MF_E_SHUTDOWN; HRESULT hr = q->QueueEventParamVar(t, g, s, v); q->Release(); return hr; }

    // IMFMediaSource
    STDMETHODIMP GetCharacteristics(DWORD* c) override {
        if (!c) return E_POINTER;
        *c = MFMEDIASOURCE_IS_LIVE;
        return m_desligado ? MF_E_SHUTDOWN : S_OK;
    }
    STDMETHODIMP CreatePresentationDescriptor(IMFPresentationDescriptor** pp) override {
        if (!pp) return E_POINTER;
        EnterCriticalSection(&m_cs);
        HRESULT hr = m_desligado ? MF_E_SHUTDOWN : m_pd->Clone(pp);
        LeaveCriticalSection(&m_cs);
        return hr;
    }
    STDMETHODIMP Start(IMFPresentationDescriptor* pd, const GUID* formato, const PROPVARIANT* inicio) override {
        if (!pd || (formato && *formato != GUID_NULL)) return E_INVALIDARG;
        EnterCriticalSection(&m_cs);
        HRESULT hr = m_desligado ? MF_E_SHUTDOWN : S_OK;
        BOOL selecionado = FALSE;
        IMFStreamDescriptor* sd = NULL;
        if (SUCCEEDED(hr)) hr = pd->GetStreamDescriptorByIndex(0, &selecionado, &sd);
        if (SUCCEEDED(hr) && selecionado) {
            // aplica o formato escolhido pelo app ao nosso stream
            IMFMediaTypeHandler *mh = NULL, *meu = NULL; IMFMediaType* mt = NULL; IMFStreamDescriptor* nosso = NULL;
            if (SUCCEEDED(sd->GetMediaTypeHandler(&mh)) && SUCCEEDED(mh->GetCurrentMediaType(&mt)) &&
                SUCCEEDED(m_stream->GetStreamDescriptor(&nosso)) && SUCCEEDED(nosso->GetMediaTypeHandler(&meu)))
                meu->SetCurrentMediaType(mt);
            Liberar(mt); Liberar(mh); Liberar(meu); Liberar(nosso);
            hr = m_fila->QueueEventParamUnk(m_iniciado ? MEUpdatedStream : MENewStream, GUID_NULL, S_OK,
                                            static_cast<IObMFMediaStream2*>(m_stream));
            if (SUCCEEDED(hr)) hr = m_stream->Iniciar();
            m_iniciado = true;
        }
        Liberar(sd);
        PROPVARIANT agora; PropVariantInit(&agora);
        agora.vt = VT_I8; agora.hVal.QuadPart = MFGetSystemTime();
        if (SUCCEEDED(hr)) hr = m_fila->QueueEventParamVar(MESourceStarted, GUID_NULL, S_OK,
                                                           inicio && inicio->vt == VT_I8 ? inicio : &agora);
        LeaveCriticalSection(&m_cs);
        return hr;
    }
    STDMETHODIMP Stop() override {
        EnterCriticalSection(&m_cs);
        HRESULT hr = m_desligado ? MF_E_SHUTDOWN : m_stream->Parar();
        if (SUCCEEDED(hr)) hr = m_fila->QueueEventParamVar(MESourceStopped, GUID_NULL, S_OK, NULL);
        LeaveCriticalSection(&m_cs);
        return hr;
    }
    STDMETHODIMP Pause() override { return MF_E_INVALID_STATE_TRANSITION; }
    STDMETHODIMP Shutdown() override {
        EnterCriticalSection(&m_cs);
        m_desligado = true;
        if (m_stream) m_stream->Desligar();
        if (m_fila) m_fila->Shutdown();
        LeaveCriticalSection(&m_cs);
        return S_OK;
    }

    // IMFMediaSourceEx
    STDMETHODIMP GetSourceAttributes(IMFAttributes** pp) override {
        if (!pp) return E_POINTER;
        *pp = m_attr; m_attr->AddRef();
        return S_OK;
    }
    STDMETHODIMP GetStreamAttributes(DWORD id, IMFAttributes** pp) override {
        if (!pp) return E_POINTER;
        if (id != 0) return MF_E_INVALIDSTREAMNUMBER;
        IMFStreamDescriptor* sd = NULL;
        HRESULT hr = m_stream->GetStreamDescriptor(&sd);
        if (SUCCEEDED(hr)) hr = sd->QueryInterface(IID_IMFAttributes, (void**)pp);
        Liberar(sd);
        return hr;
    }
    STDMETHODIMP SetD3DManager(IUnknown*) override { return S_OK; }

    // IMFGetService
    STDMETHODIMP GetService(REFGUID, REFIID, LPVOID*) override { return MF_E_UNSUPPORTED_SERVICE; }

    // IKsControl
    STDMETHODIMP KsProperty(PKSPROPERTY, ULONG, LPVOID, ULONG, ULONG*) override { return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND); }
    STDMETHODIMP KsMethod(PKSMETHOD, ULONG, LPVOID, ULONG, ULONG*) override { return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND); }
    STDMETHODIMP KsEvent(PKSEVENT, ULONG, LPVOID, ULONG, ULONG*) override { return HRESULT_FROM_WIN32(ERROR_SET_NOT_FOUND); }

private:
    IMFMediaEventQueue* Fila() {
        EnterCriticalSection(&m_cs);
        IMFMediaEventQueue* q = m_desligado ? NULL : m_fila;
        if (q) q->AddRef();
        LeaveCriticalSection(&m_cs);
        return q;
    }
    volatile LONG m_ref;
    IMFMediaEventQueue* m_fila;
    IMFPresentationDescriptor* m_pd;
    IMFAttributes* m_attr;
    Stream* m_stream;
    bool m_desligado, m_iniciado;
    CRITICAL_SECTION m_cs;
};

STDMETHODIMP Stream::GetMediaSource(IMFMediaSource** pp) {
    if (!pp) return E_POINTER;
    EnterCriticalSection(&m_cs);
    HRESULT hr = m_desligado ? MF_E_SHUTDOWN : static_cast<IMFMediaSourceEx*>(m_fonte)->QueryInterface(IID_IMFMediaSource, (void**)pp);
    LeaveCriticalSection(&m_cs);
    return hr;
}

// ---------------------------------------------------------------- ativador
// O servico de camera do Windows nao cria a fonte direto: pede um IMFActivate,
// que cria a fonte de midia quando a camera e aberta.
#define DELEGAR_ATRIBUTOS(a) \
    STDMETHODIMP GetItem(REFGUID k, PROPVARIANT* v) override { return a->GetItem(k, v); } \
    STDMETHODIMP GetItemType(REFGUID k, MF_ATTRIBUTE_TYPE* t) override { return a->GetItemType(k, t); } \
    STDMETHODIMP CompareItem(REFGUID k, REFPROPVARIANT v, BOOL* r) override { return a->CompareItem(k, v, r); } \
    STDMETHODIMP Compare(IMFAttributes* t, MF_ATTRIBUTES_MATCH_TYPE m, BOOL* r) override { return a->Compare(t, m, r); } \
    STDMETHODIMP GetUINT32(REFGUID k, UINT32* v) override { return a->GetUINT32(k, v); } \
    STDMETHODIMP GetUINT64(REFGUID k, UINT64* v) override { return a->GetUINT64(k, v); } \
    STDMETHODIMP GetDouble(REFGUID k, double* v) override { return a->GetDouble(k, v); } \
    STDMETHODIMP GetGUID(REFGUID k, GUID* v) override { return a->GetGUID(k, v); } \
    STDMETHODIMP GetStringLength(REFGUID k, UINT32* v) override { return a->GetStringLength(k, v); } \
    STDMETHODIMP GetString(REFGUID k, LPWSTR v, UINT32 n, UINT32* l) override { return a->GetString(k, v, n, l); } \
    STDMETHODIMP GetAllocatedString(REFGUID k, LPWSTR* v, UINT32* l) override { return a->GetAllocatedString(k, v, l); } \
    STDMETHODIMP GetBlobSize(REFGUID k, UINT32* v) override { return a->GetBlobSize(k, v); } \
    STDMETHODIMP GetBlob(REFGUID k, UINT8* v, UINT32 n, UINT32* l) override { return a->GetBlob(k, v, n, l); } \
    STDMETHODIMP GetAllocatedBlob(REFGUID k, UINT8** v, UINT32* l) override { return a->GetAllocatedBlob(k, v, l); } \
    STDMETHODIMP GetUnknown(REFGUID k, REFIID r, LPVOID* v) override { return a->GetUnknown(k, r, v); } \
    STDMETHODIMP SetItem(REFGUID k, REFPROPVARIANT v) override { return a->SetItem(k, v); } \
    STDMETHODIMP DeleteItem(REFGUID k) override { return a->DeleteItem(k); } \
    STDMETHODIMP DeleteAllItems() override { return a->DeleteAllItems(); } \
    STDMETHODIMP SetUINT32(REFGUID k, UINT32 v) override { return a->SetUINT32(k, v); } \
    STDMETHODIMP SetUINT64(REFGUID k, UINT64 v) override { return a->SetUINT64(k, v); } \
    STDMETHODIMP SetDouble(REFGUID k, double v) override { return a->SetDouble(k, v); } \
    STDMETHODIMP SetGUID(REFGUID k, REFGUID v) override { return a->SetGUID(k, v); } \
    STDMETHODIMP SetString(REFGUID k, LPCWSTR v) override { return a->SetString(k, v); } \
    STDMETHODIMP SetBlob(REFGUID k, const UINT8* v, UINT32 n) override { return a->SetBlob(k, v, n); } \
    STDMETHODIMP SetUnknown(REFGUID k, IUnknown* v) override { return a->SetUnknown(k, v); } \
    STDMETHODIMP LockStore() override { return a->LockStore(); } \
    STDMETHODIMP UnlockStore() override { return a->UnlockStore(); } \
    STDMETHODIMP GetCount(UINT32* n) override { return a->GetCount(n); } \
    STDMETHODIMP GetItemByIndex(UINT32 i, GUID* k, PROPVARIANT* v) override { return a->GetItemByIndex(i, k, v); } \
    STDMETHODIMP CopyAllItems(IMFAttributes* d) override { return a->CopyAllItems(d); }

class Ativador : public IMFActivate {
public:
    Ativador() : m_ref(1), m_attr(NULL), m_fonte(NULL) {
        InterlockedIncrement(&g_objetos);
        InitializeCriticalSection(&m_cs);
        MFCreateAttributes(&m_attr, 4);
    }
    virtual ~Ativador() { Liberar(m_fonte); Liberar(m_attr); DeleteCriticalSection(&m_cs); InterlockedDecrement(&g_objetos); }
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IMFAttributes || riid == IID_IMFActivate) *ppv = static_cast<IMFActivate*>(this);
        else { *ppv = NULL; LogIID("Ativador", riid); return E_NOINTERFACE; }
        AddRef();
        return S_OK;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&m_ref); }
    STDMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&m_ref); if (!r) delete this; return r; }
    DELEGAR_ATRIBUTOS(m_attr)
    STDMETHODIMP ActivateObject(REFIID riid, void** ppv) override {
        EnterCriticalSection(&m_cs);
        HRESULT hr = S_OK;
        if (!m_fonte) {
            m_fonte = new (std::nothrow) Fonte();
            hr = m_fonte ? m_fonte->Inicializar() : E_OUTOFMEMORY;
            if (FAILED(hr)) Liberar(m_fonte);
        }
        if (SUCCEEDED(hr)) hr = m_fonte->QueryInterface(riid, ppv);
        LeaveCriticalSection(&m_cs);
        Log("ActivateObject: 0x%08lX", (unsigned long)hr);
        return hr;
    }
    STDMETHODIMP ShutdownObject() override {
        EnterCriticalSection(&m_cs);
        if (m_fonte) { m_fonte->Shutdown(); Liberar(m_fonte); }
        LeaveCriticalSection(&m_cs);
        return S_OK;
    }
    STDMETHODIMP DetachObject() override {
        EnterCriticalSection(&m_cs); Liberar(m_fonte); LeaveCriticalSection(&m_cs);
        return S_OK;
    }
private:
    volatile LONG m_ref;
    IMFAttributes* m_attr;
    Fonte* m_fonte;
    CRITICAL_SECTION m_cs;
};

// ---------------------------------------------------------------- fabrica COM
class Fabrica : public IClassFactory {
public:
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) { *ppv = this; return S_OK; }
        *ppv = NULL; return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override { return 2; }
    STDMETHODIMP_(ULONG) Release() override { return 1; }
    STDMETHODIMP CreateInstance(IUnknown* externo, REFIID riid, void** ppv) override {
        Log("CreateInstance (processo %lu)", GetCurrentProcessId());
        if (externo) return CLASS_E_NOAGGREGATION;
        if (riid == IID_IMFActivate || riid == IID_IMFAttributes || riid == IID_IUnknown) {
            Ativador* a = new (std::nothrow) Ativador();
            if (!a) return E_OUTOFMEMORY;
            HRESULT hr = a->QueryInterface(riid, ppv);
            a->Release();
            return hr;
        }
        Fonte* f = new (std::nothrow) Fonte();
        if (!f) return E_OUTOFMEMORY;
        HRESULT hr = f->Inicializar();
        Log("Inicializar: 0x%08lX", (unsigned long)hr);
        if (SUCCEEDED(hr)) hr = f->QueryInterface(riid, ppv);
        f->Release();
        return hr;
    }
    STDMETHODIMP LockServer(BOOL trava) override { trava ? InterlockedIncrement(&g_objetos) : InterlockedDecrement(&g_objetos); return S_OK; }
};
static Fabrica g_fabrica;

extern "C" BOOL WINAPI DllMain(HINSTANCE h, DWORD motivo, LPVOID) {
    if (motivo == DLL_PROCESS_ATTACH) { g_modulo = h; DisableThreadLibraryCalls(h); }
    return TRUE;
}
STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv) {
    if (clsid != CLSID_OpenBokehMF) return CLASS_E_CLASSNOTAVAILABLE;
    return g_fabrica.QueryInterface(riid, ppv);
}
STDAPI DllCanUnloadNow() { return g_objetos == 0 ? S_OK : S_FALSE; }

static LONG GravarChave(HKEY raiz, LPCWSTR caminho, LPCWSTR nome, LPCWSTR valor) {
    HKEY k; LONG r = RegCreateKeyExW(raiz, caminho, 0, NULL, 0, KEY_WRITE, NULL, &k, NULL);
    if (r == ERROR_SUCCESS) { r = RegSetValueExW(k, nome, 0, REG_SZ, (const BYTE*)valor, (DWORD)((wcslen(valor) + 1) * 2)); RegCloseKey(k); }
    return r;
}
STDAPI DllRegisterServer() {
    wchar_t caminho[MAX_PATH];
    GetModuleFileNameW(g_modulo, caminho, MAX_PATH);
    LONG r = GravarChave(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Classes\\CLSID\\" CLSID_TEXTO, NULL, NOME_CAMERA L" (Windows 11)");
    if (r == ERROR_SUCCESS) r = GravarChave(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Classes\\CLSID\\" CLSID_TEXTO L"\\InprocServer32", NULL, caminho);
    if (r == ERROR_SUCCESS) r = GravarChave(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Classes\\CLSID\\" CLSID_TEXTO L"\\InprocServer32", L"ThreadingModel", L"Both");
    return HRESULT_FROM_WIN32(r);
}
STDAPI DllUnregisterServer() {
    RegDeleteTreeW(HKEY_LOCAL_MACHINE, L"SOFTWARE\\Classes\\CLSID\\" CLSID_TEXTO);
    return S_OK;
}

// ---------------------------------------------------------------- criar/remover a camera
// Usado pelo instalador (via rundll32, como administrador: camera permanente para
// todos os usuarios) e pelos testes (camera so desta sessao, sem administrador).
static IObMFVirtualCamera* g_camera = NULL;

extern "C" __declspec(dllexport) HRESULT ObCriarCamera(int permanente) {
    HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (hr == RPC_E_CHANGED_MODE) hr = S_OK;
    MFStartup(MF_VERSION, MFSTARTUP_FULL);
    HMODULE m = LoadLibraryExW(L"mfsensorgroup.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    PFN_MFCreateVirtualCamera criar = m ? (PFN_MFCreateVirtualCamera)GetProcAddress(m, "MFCreateVirtualCamera") : NULL;
    if (!criar) return HRESULT_FROM_WIN32(ERROR_PROC_NOT_FOUND);      // Windows 10: sem suporte
    if (g_camera) return S_OK;
    Log("MFCreateVirtualCamera(permanente=%d)...", permanente);
    hr = criar(0 /*SoftwareCameraSource*/, permanente ? 1 : 0 /*System|Session*/, permanente ? 1 : 0 /*AllUsers|CurrentUser*/,
               NOME_CAMERA, CLSID_TEXTO, NULL, 0, &g_camera);
    Log("  criar: 0x%08lX", (unsigned long)hr);
    if (SUCCEEDED(hr)) hr = g_camera->Start(NULL);
    Log("  Start: 0x%08lX", (unsigned long)hr);
    if (FAILED(hr) && g_camera) { g_camera->Shutdown(); g_camera->Release(); g_camera = NULL; }
    return hr;
}

extern "C" __declspec(dllexport) HRESULT ObRemoverCamera(int permanente) {
    // remove de vez (desinstalar); para a camera de sessao basta encerrar
    if (!g_camera) {
        HRESULT hr = ObCriarCamera(permanente);
        if (FAILED(hr)) return hr;
    }
    HRESULT hr = g_camera->Remove();
    g_camera->Shutdown(); g_camera->Release(); g_camera = NULL;
    return hr;
}

extern "C" __declspec(dllexport) void ObEncerrarCamera() {
    if (g_camera) { g_camera->Shutdown(); g_camera->Release(); g_camera = NULL; }
}

// rundll32 OpenBokehMF.dll,Instalar  /  ,Desinstalar  (o instalador chama como administrador)
extern "C" __declspec(dllexport) void CALLBACK Instalar(HWND, HINSTANCE, LPSTR, int) {
    HRESULT hr = ObCriarCamera(1);
    ObEncerrarCamera();
    ExitProcess(SUCCEEDED(hr) ? 0 : 1);
}
extern "C" __declspec(dllexport) void CALLBACK Desinstalar(HWND, HINSTANCE, LPSTR, int) {
    HRESULT hr = ObRemoverCamera(1);
    ExitProcess(SUCCEEDED(hr) ? 0 : 1);
}
