/*
  OpenBokeh - gravador de tela (DLL nativa, 64 bits).

  Tudo acontece na placa de video, sem passar quadros pela CPU:

    tela (DXGI Desktop Duplication) --+
                                      +--> composicao (shader D3D11) --> RGB->NV12 BT.709 faixa
    webcam (RGBA + alpha, do Python) -+    (escala, faixas, PIP,          limitada (Video Processor)
                                            cursor)                              |
                                                                                 v
    audio PCM 16 bits 48 kHz (do Python) ------------------> AAC    H.264/HEVC por hardware (MF)
                                                              \__________ MP4 fragmentado ___/

  Regra de nitidez: quando a tela cabe na saida, ela entra em 1:1 (Load, sem filtro).
  Reduzir usa mipmaps (media por area); ampliar usa bilinear.

  Interface C (usada pelo gravador.py via ctypes):
    GrListarMonitores, GrIniciar, GrAtualizar, GrQuadroWebcam, GrAudio, GrPausar, GrParar, GrEstado
  Licenca: GPL-3.0-or-later (projeto OpenBokeh).
*/
#define WIN32_LEAN_AND_MEAN
#include <initguid.h>
#include <windows.h>
#include <d3d11_1.h>
#include <d3d10.h>
#include <dxgi1_2.h>
#include <d3dcompiler.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <mftransform.h>
#include <codecapi.h>
#include <cguid.h>
#include <strmif.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <ksmedia.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <wchar.h>

DEFINE_GUID(OB_IID_ICodecAPI, 0x901db4c7, 0x31ce, 0x41a2, 0x85, 0xdc, 0x8f, 0xa0, 0xbf, 0x41, 0xb8, 0xda);

// ------------------------------------------------------------------ utilitarios
template <class T> struct Com {
    T* p = nullptr;
    Com() {}
    ~Com() { reset(); }
    Com(const Com&) = delete;
    Com& operator=(const Com&) = delete;
    void reset() { if (p) { p->Release(); p = nullptr; } }
    T** operator&() { reset(); return &p; }
    T* operator->() const { return p; }
    operator T*() const { return p; }
};

static CRITICAL_SECTION g_trava;          // protege config viva, webcam, audio e estado
static bool g_trava_ok = false;
static void trava() { if (!g_trava_ok) { InitializeCriticalSection(&g_trava); g_trava_ok = true; } EnterCriticalSection(&g_trava); }
static void solta() { LeaveCriticalSection(&g_trava); }

static int64_t agora100ns() {
    static LARGE_INTEGER f = {};
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (int64_t)((c.QuadPart / f.QuadPart) * 10000000LL + (c.QuadPart % f.QuadPart) * 10000000LL / f.QuadPart);
}

// ------------------------------------------------------------------ configuracao (igual ao ctypes)
#pragma pack(push, 4)
struct GrConfig {
    int monitor;            // indice de GrListarMonitores
    int saidaW, saidaH;     // tamanho do video
    int fps;                // 30 | 60
    int codec;              // 0 = H.264, 1 = HEVC
    int qualidade;          // 1..100 (modo qualidade constante)
    int bitrateKbps;        // usado se o codificador nao aceitar qualidade constante
    int gopSegundos;        // quadro-chave a cada N s
    int cursor;             // 1 = desenha o cursor
    // tela -> saida (ao vivo)
    int areaX, areaY, areaW, areaH;   // regiao da tela usada (px); areaW = 0 -> tela inteira
    int telaX, telaY, telaW, telaH;   // onde ela entra na saida (px)
    int fundo;              // 0 = cor, 1 = tela desfocada
    unsigned corFundo;      // 0xRRGGBB
    // webcam (ao vivo)
    int camForma;           // 0 nenhuma, 1 circulo, 2 retangulo arredondado, 3 so a pessoa, 4 retangulo
    int camX, camY, camW, camH;
    int camBorda;           // px
    unsigned camCorBorda;   // 0xRRGGBB
    int audio;              // 1 = ha trilha de audio (PCM 16 bits, 2 canais, 48 kHz)
    wchar_t arquivo[520];
};
struct GrEstadoInfo {
    int gravando, pausado;
    int64_t quadros, perdidos;
    double segundos;
    int64_t bytes;
    int hardware;           // 1 = codificador da placa de video
    int modoQualidade;      // 1 = qualidade constante aceita; 0 = VBR
    int fragmentado;        // 1 = MP4 fragmentado
    wchar_t codificador[128];
    wchar_t erro[256];
};
#pragma pack(pop)

static GrConfig g_cfg;                    // copia viva (GrAtualizar)
static GrEstadoInfo g_est;
static HANDLE g_thread = NULL;
static volatile LONG g_rodar = 0;
static volatile LONG g_pausar = 0;
static HANDLE g_pronto = NULL;            // a thread sinaliza depois de iniciar (ou falhar)
static HRESULT g_hr_inicio = S_OK;

static void erro(const wchar_t* fmt, ...) {
    wchar_t b[256];
    va_list ap; va_start(ap, fmt);
    _vsnwprintf(b, 255, fmt, ap);
    va_end(ap);
    b[255] = 0;
    trava(); wcsncpy(g_est.erro, b, 255); solta();
}

// webcam vinda do Python
static uint8_t* g_cam = nullptr;
static int g_camW = 0, g_camH = 0;
static bool g_camNovo = false;

// audio vindo do Python (fila simples)
struct BlocoAudio { int16_t* pcm; int quadros; int64_t tempo; BlocoAudio* prox; };
static BlocoAudio* g_audioIni = nullptr;
static BlocoAudio* g_audioFim = nullptr;
static int64_t g_audioBase = -1;          // tempo (100 ns) do 1o bloco
static int64_t g_audioAmostras = 0;

// ------------------------------------------------------------------ monitores
struct Monitor { Com<IDXGIAdapter1> adaptador; Com<IDXGIOutput1> saida; DXGI_OUTPUT_DESC desc; };

static int listar(Monitor* lista, int max) {
    Com<IDXGIFactory1> fab;
    if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory1), (void**)&fab))) return 0;
    int n = 0;
    for (UINT a = 0; n < max; a++) {
        Com<IDXGIAdapter1> ad;
        if (fab->EnumAdapters1(a, &ad) == DXGI_ERROR_NOT_FOUND) break;
        for (UINT o = 0; n < max; o++) {
            Com<IDXGIOutput> out;
            if (ad->EnumOutputs(o, &out) == DXGI_ERROR_NOT_FOUND) break;
            DXGI_OUTPUT_DESC d; out->GetDesc(&d);
            if (!d.AttachedToDesktop) continue;
            if (lista) {
                out->QueryInterface(__uuidof(IDXGIOutput1), (void**)&lista[n].saida);
                lista[n].adaptador.p = ad.p; ad.p->AddRef();
                lista[n].desc = d;
            }
            n++;
        }
    }
    return n;
}

// "nome|x|y|largura|altura\n" por monitor
extern "C" __declspec(dllexport) int GrListarMonitores(wchar_t* buf, int tamanho) {
    Monitor m[16];
    int n = listar(m, 16);
    if (buf && tamanho > 0) {
        buf[0] = 0;
        for (int i = 0; i < n; i++) {
            RECT r = m[i].desc.DesktopCoordinates;
            wchar_t linha[160];
            _snwprintf(linha, 159, L"%ls|%ld|%ld|%ld|%ld\n", m[i].desc.DeviceName, r.left, r.top,
                       r.right - r.left, r.bottom - r.top);
            linha[159] = 0;
            if ((int)(wcslen(buf) + wcslen(linha)) < tamanho - 1) wcscat(buf, linha);
        }
    }
    return n;
}

// ------------------------------------------------------------------ shaders
static const char* HLSL = R"(
cbuffer P : register(b0) {
    float4 telaRect;    // destino na saida: x, y, w, h (px)
    float4 areaRect;    // origem na tela: x, y, w, h (px)
    float4 camRect;     // destino da webcam
    float4 corFundo;
    float4 corBorda;    // a = espessura (px)
    float4 cursorRect;  // na tela: x, y, w, h (px); w = 0 -> sem cursor
    float2 telaTam;     // tamanho da textura da tela
    float2 camTam;      // tamanho da imagem da webcam
    float  escala;      // px da tela por px da saida (1 = 1:1)
    float  lodTela;
    float  lodFundo;
    float  camForma;
    float  fundoModo;
    float2 saidaTam;
    float  _pad;
};
Texture2D tTela : register(t0);
Texture2D tCam : register(t1);
Texture2D tCursor : register(t2);
SamplerState sLin : register(s0);

float4 VS(uint id : SV_VertexID) : SV_Position {
    float2 uv = float2((id << 1) & 2, id & 2);
    return float4(uv * float2(2, -2) + float2(-1, 1), 0, 1);
}

float3 amostraTela(float2 src) {          // src = px na tela
    float3 c;
    if (escala == 1.0) c = tTela.Load(int3(floor(src), 0)).rgb;          // 1:1, nitido
    else c = tTela.SampleLevel(sLin, src / telaTam, lodTela).rgb;
    if (cursorRect.z > 0) {
        float2 q = (src - cursorRect.xy) / cursorRect.zw;
        if (all(q >= 0) && all(q < 1)) {
            float4 k = tCursor.SampleLevel(sLin, q, 0);
            if (escala == 1.0) k = tCursor.Load(int3(floor(src - cursorRect.xy), 0));
            c = lerp(c, k.rgb, k.a);
        }
    }
    return c;
}

float4 PS(float4 pos : SV_Position) : SV_Target {
    float2 p = pos.xy;
    float3 col;
    float2 t = (p - telaRect.xy) / telaRect.zw;
    if (all(t >= 0) && all(t < 1)) {
        col = amostraTela(areaRect.xy + (p - telaRect.xy) * escala);
    } else if (fundoModo > 0.5) {
        // faixas: a propria tela, "cobrindo" a saida, num mip bem baixo (desfoque barato) e escurecida
        float s = max(saidaTam.x / areaRect.z, saidaTam.y / areaRect.w);
        float2 src = areaRect.xy + areaRect.zw * 0.5 + (p - saidaTam * 0.5) / s;
        col = tTela.SampleLevel(sLin, src / telaTam, lodFundo).rgb * 0.55;
    } else {
        col = corFundo.rgb;
    }

    if (camForma > 0.5) {
        float2 c = camRect.xy + camRect.zw * 0.5;
        float2 d = p - c;
        float2 meia = camRect.zw * 0.5;
        if (all(abs(d) <= meia + 2)) {
            // imagem da webcam "cobrindo" o retangulo, sem distorcer
            float s = max(camRect.z / camTam.x, camRect.w / camTam.y);
            float2 uv = (camTam * 0.5 + d / s) / camTam;
            float4 k = tCam.SampleLevel(sLin, uv, 0);
            float m, dist;
            if (camForma < 1.5) {                       // circulo
                float r = min(meia.x, meia.y);
                dist = length(d) - r;
            } else if (camForma < 2.5 || camForma > 3.5) {  // retangulo (arredondado)
                float raio = camForma < 2.5 ? min(meia.x, meia.y) * 0.18 : 0.0;
                float2 q = abs(d) - meia + raio;
                dist = length(max(q, 0)) + min(max(q.x, q.y), 0) - raio;
            } else {                                    // so a pessoa (alpha da IA)
                dist = all(abs(d) <= meia) ? -1 : 1;
            }
            m = saturate(0.5 - dist);
            if (camForma > 2.5 && camForma < 3.5) m *= k.a;
            col = lerp(col, k.rgb, m);
            float b = corBorda.a;
            if (b > 0 && (camForma < 2.5 || camForma > 3.5)) {
                float anel = saturate(0.5 - dist) * saturate(dist + b + 0.5);
                col = lerp(col, corBorda.rgb, anel);
            }
        }
    }
    return float4(col, 1);
}
)";

struct Params {
    float telaRect[4], areaRect[4], camRect[4], corFundo[4], corBorda[4], cursorRect[4];
    float telaTam[2], camTam[2];
    float escala, lodTela, lodFundo, camForma, fundoModo, saidaTam[2], pad;
};

typedef HRESULT(WINAPI* PFN_D3DCompile)(LPCVOID, SIZE_T, LPCSTR, const D3D_SHADER_MACRO*, ID3DInclude*, LPCSTR, LPCSTR,
                                        UINT, UINT, ID3DBlob**, ID3DBlob**);

// ------------------------------------------------------------------ o gravador
struct Gravador {
    Monitor mon;
    Com<ID3D11Device> dev;
    Com<ID3D11DeviceContext> ctx;
    Com<IDXGIOutputDuplication> dup;
    int telaW = 0, telaH = 0;
    Com<ID3D11Texture2D> texTela; Com<ID3D11ShaderResourceView> srvTela;
    Com<ID3D11Texture2D> texCam; Com<ID3D11ShaderResourceView> srvCam; int camW = 0, camH = 0;
    Com<ID3D11Texture2D> texCursor; Com<ID3D11ShaderResourceView> srvCursor;
    int curX = 0, curY = 0, curW = 0, curH = 0; bool curVisivel = false;
    Com<ID3D11Texture2D> texSaida; Com<ID3D11RenderTargetView> rtvSaida;
    Com<ID3D11VertexShader> vs; Com<ID3D11PixelShader> ps;
    Com<ID3D11Buffer> cb; Com<ID3D11SamplerState> amostrador;
    // NV12
    Com<ID3D11VideoDevice> vdev; Com<ID3D11VideoContext> vctx;
    Com<ID3D11VideoProcessorEnumerator> vpEnum; Com<ID3D11VideoProcessor> vp;
    Com<ID3D11VideoProcessorInputView> vpIn;
    // Media Foundation
    Com<IMFDXGIDeviceManager> dxgiMan; UINT tokenMan = 0;
    Com<IMFSinkWriter> escritor; DWORD fluxoVideo = 0, fluxoAudio = 0;
    Com<IMFVideoSampleAllocatorEx> alocador;
    bool gpu = true;                    // amostras na GPU (senao copia para a memoria)
    Com<ID3D11Texture2D> texNV12; Com<ID3D11Texture2D> texStaging;   // caminho por software
    GrConfig cfg;
    int saidaW = 0, saidaH = 0;
    bool temQuadro = false;
    bool mipsSujos = true;
};

static HRESULT criarDuplicacao(Gravador& g) {
    g.dup.reset();
    HRESULT hr = g.mon.saida->DuplicateOutput(g.dev, &g.dup);
    if (FAILED(hr)) return hr;
    DXGI_OUTDUPL_DESC d; g.dup->GetDesc(&d);
    int w = (int)d.ModeDesc.Width, h = (int)d.ModeDesc.Height;
    if (w != g.telaW || h != g.telaH || !g.texTela) {
        g.telaW = w; g.telaH = h;
        D3D11_TEXTURE2D_DESC td = {};
        td.Width = w; td.Height = h; td.MipLevels = 0; td.ArraySize = 1;
        td.Format = DXGI_FORMAT_B8G8R8A8_UNORM; td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_DEFAULT;
        td.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
        td.MiscFlags = D3D11_RESOURCE_MISC_GENERATE_MIPS;
        hr = g.dev->CreateTexture2D(&td, nullptr, &g.texTela);
        if (FAILED(hr)) return hr;
        hr = g.dev->CreateShaderResourceView(g.texTela, nullptr, &g.srvTela);
        if (FAILED(hr)) return hr;
        g.temQuadro = false;
    }
    return S_OK;
}

// converte o formato do cursor do Windows para BGRA com alpha
static void atualizarCursor(Gravador& g, const DXGI_OUTDUPL_POINTER_SHAPE_INFO& info, const uint8_t* buf) {
    int w = (int)info.Width;
    int h = (int)(info.Type == DXGI_OUTDUPL_POINTER_SHAPE_TYPE_MONOCHROME ? info.Height / 2 : info.Height);
    if (w <= 0 || h <= 0 || w > 256 || h > 256) return;
    uint32_t px[256 * 256];
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            uint32_t v = 0;
            if (info.Type == DXGI_OUTDUPL_POINTER_SHAPE_TYPE_COLOR) {
                v = ((const uint32_t*)(buf + y * info.Pitch))[x];
            } else if (info.Type == DXGI_OUTDUPL_POINTER_SHAPE_TYPE_MASKED_COLOR) {
                uint32_t c = ((const uint32_t*)(buf + y * info.Pitch))[x];
                bool xorm = (c >> 24) != 0;
                v = xorm ? ((c & 0xFFFFFF) ? (0xFF000000 | (c & 0xFFFFFF)) : 0) : (0xFF000000 | c);
            } else {  // monocromatico: AND em cima, XOR embaixo
                int bit = 0x80 >> (x % 8);
                bool a = buf[y * info.Pitch + x / 8] & bit;
                bool xo = buf[(y + h) * info.Pitch + x / 8] & bit;
                v = !a ? (xo ? 0xFFFFFFFF : 0xFF000000) : (xo ? 0xFF000000 : 0);   // inverter vira preto
            }
            px[y * w + x] = v;
        }
    D3D11_TEXTURE2D_DESC td = {};
    td.Width = w; td.Height = h; td.MipLevels = 1; td.ArraySize = 1;
    td.Format = DXGI_FORMAT_B8G8R8A8_UNORM; td.SampleDesc.Count = 1;
    td.Usage = D3D11_USAGE_DEFAULT; td.BindFlags = D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA sd = { px, (UINT)(w * 4), 0 };
    g.texCursor.reset(); g.srvCursor.reset();
    if (SUCCEEDED(g.dev->CreateTexture2D(&td, &sd, &g.texCursor)))
        g.dev->CreateShaderResourceView(g.texCursor, nullptr, &g.srvCursor);
    g.curW = w; g.curH = h;
}

// pega o quadro novo da tela (se houver) ate 'espera' ms
static void capturar(Gravador& g, UINT espera) {
    if (!g.dup) {
        static DWORD ultima = 0;
        if (GetTickCount() - ultima < 250) { Sleep(espera); return; }
        ultima = GetTickCount();
        if (FAILED(criarDuplicacao(g))) { Sleep(espera); return; }
    }
    DXGI_OUTDUPL_FRAME_INFO fi;
    Com<IDXGIResource> rec;
    HRESULT hr = g.dup->AcquireNextFrame(espera, &fi, &rec);
    if (hr == DXGI_ERROR_WAIT_TIMEOUT) return;
    if (FAILED(hr)) {            // mudou a resolucao, tela do UAC, jogo em tela cheia... recria
        g.dup.reset();
        return;
    }
    if (fi.LastPresentTime.QuadPart != 0) {
        Com<ID3D11Texture2D> tex;
        rec->QueryInterface(__uuidof(ID3D11Texture2D), (void**)&tex);
        if (tex) { g.ctx->CopySubresourceRegion(g.texTela, 0, 0, 0, 0, tex, 0, nullptr); g.temQuadro = true; g.mipsSujos = true; }
    }
    if (fi.LastMouseUpdateTime.QuadPart != 0) {
        g.curVisivel = fi.PointerPosition.Visible;
        g.curX = fi.PointerPosition.Position.x; g.curY = fi.PointerPosition.Position.y;
    }
    if (fi.PointerShapeBufferSize > 0) {
        static uint8_t buf[256 * 256 * 4 * 2];
        UINT usado = 0; DXGI_OUTDUPL_POINTER_SHAPE_INFO si;
        if (fi.PointerShapeBufferSize <= sizeof(buf) &&
            SUCCEEDED(g.dup->GetFramePointerShape(sizeof(buf), buf, &usado, &si)))
            atualizarCursor(g, si, buf);
    }
    g.dup->ReleaseFrame();
}

static HRESULT criarShaders(Gravador& g) {
    HMODULE m = LoadLibraryExW(L"d3dcompiler_47.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    PFN_D3DCompile compilar = m ? (PFN_D3DCompile)GetProcAddress(m, "D3DCompile") : nullptr;
    if (!compilar) { erro(L"d3dcompiler_47.dll ausente"); return E_FAIL; }
    Com<ID3DBlob> bvs, bps, berr;
    HRESULT hr = compilar(HLSL, strlen(HLSL), "gravador", nullptr, nullptr, "VS", "vs_5_0", D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &bvs, &berr);
    if (SUCCEEDED(hr)) hr = compilar(HLSL, strlen(HLSL), "gravador", nullptr, nullptr, "PS", "ps_5_0", D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &bps, &berr);
    if (FAILED(hr)) {
        if (berr) { wchar_t w[256]; MultiByteToWideChar(CP_UTF8, 0, (char*)berr->GetBufferPointer(), -1, w, 255); w[255] = 0; erro(L"shader: %ls", w); }
        return hr;
    }
    g.dev->CreateVertexShader(bvs->GetBufferPointer(), bvs->GetBufferSize(), nullptr, &g.vs);
    g.dev->CreatePixelShader(bps->GetBufferPointer(), bps->GetBufferSize(), nullptr, &g.ps);
    D3D11_BUFFER_DESC bd = {}; bd.ByteWidth = (sizeof(Params) + 15) & ~15; bd.Usage = D3D11_USAGE_DEFAULT; bd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    hr = g.dev->CreateBuffer(&bd, nullptr, &g.cb);
    D3D11_SAMPLER_DESC sd = {};
    sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MaxLOD = D3D11_FLOAT32_MAX;
    if (SUCCEEDED(hr)) hr = g.dev->CreateSamplerState(&sd, &g.amostrador);
    return hr;
}

static HRESULT criarSaida(Gravador& g) {
    D3D11_TEXTURE2D_DESC td = {};
    td.Width = g.saidaW; td.Height = g.saidaH; td.MipLevels = 1; td.ArraySize = 1;
    td.Format = DXGI_FORMAT_B8G8R8A8_UNORM; td.SampleDesc.Count = 1; td.Usage = D3D11_USAGE_DEFAULT;
    td.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
    HRESULT hr = g.dev->CreateTexture2D(&td, nullptr, &g.texSaida);
    if (SUCCEEDED(hr)) hr = g.dev->CreateRenderTargetView(g.texSaida, nullptr, &g.rtvSaida);
    if (FAILED(hr)) return hr;

    // conversor RGB -> NV12 da propria placa (BT.709, faixa limitada 16-235)
    hr = g.dev->QueryInterface(__uuidof(ID3D11VideoDevice), (void**)&g.vdev);
    if (SUCCEEDED(hr)) hr = g.ctx->QueryInterface(__uuidof(ID3D11VideoContext), (void**)&g.vctx);
    if (FAILED(hr)) { erro(L"placa sem processador de video"); return hr; }
    D3D11_VIDEO_PROCESSOR_CONTENT_DESC cd = {};
    cd.InputFrameFormat = D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE;
    cd.InputWidth = g.saidaW; cd.InputHeight = g.saidaH; cd.OutputWidth = g.saidaW; cd.OutputHeight = g.saidaH;
    cd.InputFrameRate = { (UINT)g.cfg.fps, 1 }; cd.OutputFrameRate = { (UINT)g.cfg.fps, 1 };
    cd.Usage = D3D11_VIDEO_USAGE_OPTIMAL_QUALITY;
    hr = g.vdev->CreateVideoProcessorEnumerator(&cd, &g.vpEnum);
    if (SUCCEEDED(hr)) hr = g.vdev->CreateVideoProcessor(g.vpEnum, 0, &g.vp);
    if (FAILED(hr)) { erro(L"processador de video: 0x%08lX", hr); return hr; }
    D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC iv = {};
    iv.ViewDimension = D3D11_VPIV_DIMENSION_TEXTURE2D;
    hr = g.vdev->CreateVideoProcessorInputView(g.texSaida, g.vpEnum, &iv, &g.vpIn);
    if (FAILED(hr)) { erro(L"entrada do processador: 0x%08lX", hr); return hr; }
    g.vctx->VideoProcessorSetStreamAutoProcessingMode(g.vp, 0, FALSE);
    g.vctx->VideoProcessorSetStreamFrameFormat(g.vp, 0, D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE);
    Com<ID3D11VideoContext1> v1;
    if (SUCCEEDED(g.vctx->QueryInterface(__uuidof(ID3D11VideoContext1), (void**)&v1))) {
        v1->VideoProcessorSetStreamColorSpace1(g.vp, 0, DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709);
        v1->VideoProcessorSetOutputColorSpace1(g.vp, DXGI_COLOR_SPACE_YCBCR_STUDIO_G22_LEFT_P709);
    } else {
        D3D11_VIDEO_PROCESSOR_COLOR_SPACE cin = {}, cout = {};
        cin.RGB_Range = 0;                     // RGB 0-255
        cout.YCbCr_Matrix = 1;                 // BT.709
        cout.Nominal_Range = D3D11_VIDEO_PROCESSOR_NOMINAL_RANGE_16_235;
        g.vctx->VideoProcessorSetStreamColorSpace(g.vp, 0, &cin);
        g.vctx->VideoProcessorSetOutputColorSpace(g.vp, &cout);
    }
    RECT r = { 0, 0, g.saidaW, g.saidaH };
    g.vctx->VideoProcessorSetStreamSourceRect(g.vp, 0, TRUE, &r);
    g.vctx->VideoProcessorSetStreamDestRect(g.vp, 0, TRUE, &r);
    g.vctx->VideoProcessorSetOutputTargetRect(g.vp, TRUE, &r);
    return S_OK;
}

static void corDe(unsigned rgb, float* f) {
    f[0] = ((rgb >> 16) & 255) / 255.f; f[1] = ((rgb >> 8) & 255) / 255.f; f[2] = (rgb & 255) / 255.f;
}

// compoe tela + webcam na textura de saida
static void compor(Gravador& g) {
    GrConfig c;
    trava();
    c = g_cfg;
    if (g_camNovo && g_cam) {
        if (g_camW != g.camW || g_camH != g.camH || !g.texCam) {
            D3D11_TEXTURE2D_DESC td = {};
            td.Width = g_camW; td.Height = g_camH; td.MipLevels = 1; td.ArraySize = 1;
            td.Format = DXGI_FORMAT_R8G8B8A8_UNORM; td.SampleDesc.Count = 1;
            td.Usage = D3D11_USAGE_DEFAULT; td.BindFlags = D3D11_BIND_SHADER_RESOURCE;
            g.texCam.reset(); g.srvCam.reset();
            if (SUCCEEDED(g.dev->CreateTexture2D(&td, nullptr, &g.texCam)))
                g.dev->CreateShaderResourceView(g.texCam, nullptr, &g.srvCam);
            g.camW = g_camW; g.camH = g_camH;
        }
        if (g.texCam) g.ctx->UpdateSubresource(g.texCam, 0, nullptr, g_cam, g_camW * 4, 0);
        g_camNovo = false;
    }
    solta();

    int ax = c.areaX, ay = c.areaY, aw = c.areaW, ah = c.areaH;
    if (aw <= 0 || ah <= 0) { ax = 0; ay = 0; aw = g.telaW; ah = g.telaH; }
    if (ax < 0) ax = 0;
    if (ay < 0) ay = 0;
    if (ax + aw > g.telaW) aw = g.telaW - ax;
    if (ay + ah > g.telaH) ah = g.telaH - ay;
    int tw = c.telaW > 0 ? c.telaW : g.saidaW, th = c.telaH > 0 ? c.telaH : g.saidaH;
    float escala = (float)aw / (float)tw;
    if (fabsf(escala - 1.0f) < 0.001f && aw == tw && ah == th) escala = 1.0f;
    bool precisaMips = escala > 1.001f || c.fundo == 1;
    if (precisaMips && g.mipsSujos && g.srvTela) { g.ctx->GenerateMips(g.srvTela); g.mipsSujos = false; }

    Params p = {};
    p.telaRect[0] = (float)c.telaX; p.telaRect[1] = (float)c.telaY; p.telaRect[2] = (float)tw; p.telaRect[3] = (float)th;
    p.areaRect[0] = (float)ax; p.areaRect[1] = (float)ay; p.areaRect[2] = (float)aw; p.areaRect[3] = (float)ah;
    p.camRect[0] = (float)c.camX; p.camRect[1] = (float)c.camY; p.camRect[2] = (float)c.camW; p.camRect[3] = (float)c.camH;
    corDe(c.corFundo, p.corFundo);
    corDe(c.camCorBorda, p.corBorda); p.corBorda[3] = (float)c.camBorda;
    if (c.cursor && g.curVisivel && g.srvCursor) {
        p.cursorRect[0] = (float)g.curX; p.cursorRect[1] = (float)g.curY; p.cursorRect[2] = (float)g.curW; p.cursorRect[3] = (float)g.curH;
    }
    p.telaTam[0] = (float)g.telaW; p.telaTam[1] = (float)g.telaH;
    p.camTam[0] = (float)(g.camW ? g.camW : 1); p.camTam[1] = (float)(g.camH ? g.camH : 1);
    p.escala = escala;
    p.lodTela = escala > 1.0f ? log2f(escala) : 0.0f;
    p.lodFundo = 5.0f;
    p.camForma = (g.srvCam && c.camW > 0 && c.camH > 0) ? (float)c.camForma : 0.0f;
    p.fundoModo = (float)c.fundo;
    p.saidaTam[0] = (float)g.saidaW; p.saidaTam[1] = (float)g.saidaH;
    g.ctx->UpdateSubresource(g.cb, 0, nullptr, &p, 0, 0);

    D3D11_VIEWPORT vp = { 0, 0, (float)g.saidaW, (float)g.saidaH, 0, 1 };
    g.ctx->RSSetViewports(1, &vp);
    ID3D11RenderTargetView* rt = g.rtvSaida;
    g.ctx->OMSetRenderTargets(1, &rt, nullptr);
    g.ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    g.ctx->IASetInputLayout(nullptr);
    g.ctx->VSSetShader(g.vs, nullptr, 0);
    g.ctx->PSSetShader(g.ps, nullptr, 0);
    ID3D11Buffer* cb = g.cb; g.ctx->PSSetConstantBuffers(0, 1, &cb);
    ID3D11ShaderResourceView* srvs[3] = { g.srvTela, g.srvCam, g.srvCursor };
    g.ctx->PSSetShaderResources(0, 3, srvs);
    ID3D11SamplerState* s = g.amostrador; g.ctx->PSSetSamplers(0, 1, &s);
    g.ctx->Draw(3, 0);
    ID3D11ShaderResourceView* nulos[3] = {};
    g.ctx->PSSetShaderResources(0, 3, nulos);
    g.ctx->OMSetRenderTargets(0, nullptr, nullptr);
}

// ------------------------------------------------------------------ codificador
static void definirCor(IMFMediaType* t) {
    t->SetUINT32(MF_MT_YUV_MATRIX, MFVideoTransferMatrix_BT709);
    t->SetUINT32(MF_MT_VIDEO_PRIMARIES, MFVideoPrimaries_BT709);
    t->SetUINT32(MF_MT_TRANSFER_FUNCTION, MFVideoTransFunc_709);
    t->SetUINT32(MF_MT_VIDEO_NOMINAL_RANGE, MFNominalRange_16_235);
}

static HRESULT criarEscritor(Gravador& g, bool gpu, bool qualidade, bool fragmentado) {
    g.escritor.reset(); g.alocador.reset();
    HRESULT hr;
    Com<IMFAttributes> at;
    MFCreateAttributes(&at, 6);
    at->SetUINT32(MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS, TRUE);
    // MP4 fragmentado: legivel mesmo se o PC travar no meio
    at->SetGUID(MF_TRANSCODE_CONTAINERTYPE, fragmentado ? MFTranscodeContainerType_FMPEG4 : MFTranscodeContainerType_MPEG4);
    if (gpu) at->SetUnknown(MF_SINK_WRITER_D3D_MANAGER, g.dxgiMan);
    DeleteFileW(g.cfg.arquivo);
    hr = MFCreateSinkWriterFromURL(g.cfg.arquivo, nullptr, at, &g.escritor);
    if (FAILED(hr)) { erro(L"nao consegui criar o arquivo (0x%08lX)", hr); return hr; }

    const GUID& formato = g.cfg.codec == 1 ? MFVideoFormat_HEVC : MFVideoFormat_H264;
    Com<IMFMediaType> tout, tin;
    MFCreateMediaType(&tout);
    tout->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
    tout->SetGUID(MF_MT_SUBTYPE, formato);
    tout->SetUINT32(MF_MT_AVG_BITRATE, (UINT32)g.cfg.bitrateKbps * 1000);
    tout->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
    MFSetAttributeSize(tout, MF_MT_FRAME_SIZE, g.saidaW, g.saidaH);
    MFSetAttributeRatio(tout, MF_MT_FRAME_RATE, g.cfg.fps, 1);
    MFSetAttributeRatio(tout, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
    tout->SetUINT32(MF_MT_MPEG2_PROFILE, g.cfg.codec == 1 ? eAVEncH265VProfile_Main_420_8 : eAVEncH264VProfile_High);
    definirCor(tout);
    hr = g.escritor->AddStream(tout, &g.fluxoVideo);
    if (FAILED(hr)) { erro(L"codec de video recusado (0x%08lX)", hr); return hr; }

    MFCreateMediaType(&tin);
    tin->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
    tin->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_NV12);
    tin->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
    MFSetAttributeSize(tin, MF_MT_FRAME_SIZE, g.saidaW, g.saidaH);
    MFSetAttributeRatio(tin, MF_MT_FRAME_RATE, g.cfg.fps, 1);
    MFSetAttributeRatio(tin, MF_MT_PIXEL_ASPECT_RATIO, 1, 1);
    definirCor(tin);
    Com<IMFAttributes> enc;
    MFCreateAttributes(&enc, 6);
    if (qualidade) {
        enc->SetUINT32(CODECAPI_AVEncCommonRateControlMode, eAVEncCommonRateControlMode_Quality);
        enc->SetUINT32(CODECAPI_AVEncCommonQuality, (UINT32)g.cfg.qualidade);
    } else {
        enc->SetUINT32(CODECAPI_AVEncCommonRateControlMode, eAVEncCommonRateControlMode_PeakConstrainedVBR);
        enc->SetUINT32(CODECAPI_AVEncCommonMeanBitRate, (UINT32)g.cfg.bitrateKbps * 1000);
        enc->SetUINT32(CODECAPI_AVEncCommonMaxBitRate, (UINT32)g.cfg.bitrateKbps * 2000);
    }
    enc->SetUINT32(CODECAPI_AVEncCommonQualityVsSpeed, 100);
    enc->SetUINT32(CODECAPI_AVEncMPVGOPSize, (UINT32)(g.cfg.fps * (g.cfg.gopSegundos > 0 ? g.cfg.gopSegundos : 2)));
    hr = g.escritor->SetInputMediaType(g.fluxoVideo, tin, enc);
    if (FAILED(hr)) { erro(L"entrada de video recusada (gpu=%d qual=%d frag=%d): 0x%08lX", gpu, qualidade, fragmentado, hr); return hr; }

    if (g.cfg.audio) {
        Com<IMFMediaType> aout, ain;
        MFCreateMediaType(&aout);
        aout->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio);
        aout->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_AAC);
        aout->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 16);
        aout->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, 48000);
        aout->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, 2);
        aout->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, 24000);   // 192 kbps
        hr = g.escritor->AddStream(aout, &g.fluxoAudio);
        if (FAILED(hr)) { erro(L"codec de audio recusado (0x%08lX)", hr); return hr; }
        MFCreateMediaType(&ain);
        ain->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio);
        ain->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_PCM);
        ain->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 16);
        ain->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, 48000);
        ain->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, 2);
        ain->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT, 4);
        ain->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, 192000);
        hr = g.escritor->SetInputMediaType(g.fluxoAudio, ain, nullptr);
        if (FAILED(hr)) { erro(L"entrada de audio recusada (0x%08lX)", hr); return hr; }
    }

    // qual codificador o Windows escolheu?
    Com<IMFTransform> mft;
    trava();
    g_est.hardware = 0; g_est.codificador[0] = 0; g_est.modoQualidade = qualidade ? 1 : 0;
    solta();
    if (SUCCEEDED(g.escritor->GetServiceForStream(g.fluxoVideo, GUID_NULL, __uuidof(IMFTransform), (void**)&mft)) && mft) {
        Com<IMFAttributes> ma;
        if (SUCCEEDED(mft->GetAttributes(&ma)) && ma) {
            UINT32 n = 0; wchar_t nome[128] = L"";
            if (SUCCEEDED(ma->GetString(MFT_FRIENDLY_NAME_Attribute, nome, 127, &n))) { trava(); wcsncpy(g_est.codificador, nome, 127); solta(); }
            UINT32 tam = 0;
            if (SUCCEEDED(ma->GetStringLength(MFT_ENUM_HARDWARE_URL_Attribute, &tam))) { trava(); g_est.hardware = 1; solta(); }
        }
        Com<ICodecAPI> api;
        if (qualidade && SUCCEEDED(mft->QueryInterface(OB_IID_ICodecAPI, (void**)&api)) && api) {
            VARIANT v; VariantInit(&v);
            if (SUCCEEDED(api->GetValue(&CODECAPI_AVEncCommonRateControlMode, &v)) && v.vt == VT_UI4 &&
                v.ulVal != eAVEncCommonRateControlMode_Quality) { trava(); g_est.modoQualidade = 0; solta(); }
        }
    }
    if (!g_est.codificador[0]) { trava(); wcscpy(g_est.codificador, gpu ? L"(GPU)" : L"Microsoft (software)"); solta(); }

    if (gpu) {
        hr = MFCreateVideoSampleAllocatorEx(__uuidof(IMFVideoSampleAllocatorEx), (void**)&g.alocador);
        if (SUCCEEDED(hr)) hr = g.alocador->SetDirectXManager(g.dxgiMan);
        Com<IMFAttributes> aa; MFCreateAttributes(&aa, 3);
        UINT bind = D3D11_BIND_RENDER_TARGET;
        if (GetEnvironmentVariableW(L"OB_GR_BIND_ENC", nullptr, 0)) bind |= 0x200;   // D3D11_BIND_VIDEO_ENCODER
        if (GetEnvironmentVariableW(L"OB_GR_BIND_SRV", nullptr, 0)) bind |= D3D11_BIND_SHADER_RESOURCE;
        aa->SetUINT32(MF_SA_D3D11_BINDFLAGS, bind);
        aa->SetUINT32(MF_SA_D3D11_USAGE, D3D11_USAGE_DEFAULT);
        if (SUCCEEDED(hr)) hr = g.alocador->InitializeSampleAllocatorEx(4, 12, aa, tin);
        if (FAILED(hr)) { erro(L"alocador de quadros: 0x%08lX", hr); return hr; }
    }
    hr = g.escritor->BeginWriting();
    if (FAILED(hr)) erro(L"BeginWriting (gpu=%d qual=%d frag=%d): 0x%08lX", gpu, qualidade, fragmentado, hr);
    return hr;
}

static int g_etapa = 0;
static HRESULT enviarQuadro(Gravador& g, int64_t tempo, int64_t duracao) {
    Com<IMFSample> amostra;
    Com<ID3D11Texture2D> alvo;
    HRESULT hr;
    if (g.gpu) {
        g_etapa = 1;
        hr = g.alocador->AllocateSample(&amostra);
        if (FAILED(hr)) return hr;
        g_etapa = 2;
        Com<IMFMediaBuffer> buf; amostra->GetBufferByIndex(0, &buf);
        Com<IMFDXGIBuffer> dx; hr = buf->QueryInterface(__uuidof(IMFDXGIBuffer), (void**)&dx);
        if (FAILED(hr)) return hr;
        dx->GetResource(__uuidof(ID3D11Texture2D), (void**)&alvo);
        // o gravador do Windows recusa (E_INVALIDARG) buffer com "tamanho atual" zero
        Com<IMF2DBuffer> b2; DWORD tam = 0;
        if (SUCCEEDED(buf->QueryInterface(__uuidof(IMF2DBuffer), (void**)&b2)) && SUCCEEDED(b2->GetContiguousLength(&tam)))
            buf->SetCurrentLength(tam);
    } else {
        if (!g.texNV12) {
            D3D11_TEXTURE2D_DESC td = {};
            td.Width = g.saidaW; td.Height = g.saidaH; td.MipLevels = 1; td.ArraySize = 1; td.Format = DXGI_FORMAT_NV12;
            td.SampleDesc.Count = 1; td.Usage = D3D11_USAGE_DEFAULT; td.BindFlags = D3D11_BIND_RENDER_TARGET;
            hr = g.dev->CreateTexture2D(&td, nullptr, &g.texNV12);
            if (FAILED(hr)) return hr;
            td.Usage = D3D11_USAGE_STAGING; td.BindFlags = 0; td.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            hr = g.dev->CreateTexture2D(&td, nullptr, &g.texStaging);
            if (FAILED(hr)) return hr;
        }
        alvo.p = g.texNV12.p; alvo.p->AddRef();
    }
    D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC ov = {}; ov.ViewDimension = D3D11_VPOV_DIMENSION_TEXTURE2D;
    Com<ID3D11VideoProcessorOutputView> vpOut;
    g_etapa = 3;
    hr = g.vdev->CreateVideoProcessorOutputView(alvo, g.vpEnum, &ov, &vpOut);
    if (FAILED(hr)) return hr;
    g_etapa = 4;
    D3D11_VIDEO_PROCESSOR_STREAM st = {}; st.Enable = TRUE; st.pInputSurface = g.vpIn;
    hr = g.vctx->VideoProcessorBlt(g.vp, vpOut, 0, 1, &st);
    if (FAILED(hr)) return hr;

    if (!g.gpu) {        // codificador por software: copia o NV12 para a memoria
        g.ctx->CopyResource(g.texStaging, g.texNV12);
        D3D11_MAPPED_SUBRESOURCE map;
        hr = g.ctx->Map(g.texStaging, 0, D3D11_MAP_READ, 0, &map);
        if (FAILED(hr)) return hr;
        DWORD tam = g.saidaW * g.saidaH * 3 / 2;
        Com<IMFMediaBuffer> mb; MFCreateMemoryBuffer(tam, &mb);
        BYTE* dst = nullptr; mb->Lock(&dst, nullptr, nullptr);
        for (int y = 0; y < g.saidaH * 3 / 2; y++)
            memcpy(dst + y * g.saidaW, (BYTE*)map.pData + y * map.RowPitch, g.saidaW);
        mb->Unlock(); mb->SetCurrentLength(tam);
        g.ctx->Unmap(g.texStaging, 0);
        MFCreateSample(&amostra);
        amostra->AddBuffer(mb);
    }
    amostra->SetSampleTime(tempo);
    amostra->SetSampleDuration(duracao);
    g_etapa = 5;
    return g.escritor->WriteSample(g.fluxoVideo, amostra);
}

static void enviarAudio(Gravador& g) {
    for (;;) {
        trava();
        BlocoAudio* b = g_audioIni;
        if (b) { g_audioIni = b->prox; if (!g_audioIni) g_audioFim = nullptr; }
        solta();
        if (!b) return;
        DWORD tam = b->quadros * 4;
        Com<IMFMediaBuffer> mb;
        if (SUCCEEDED(MFCreateMemoryBuffer(tam, &mb))) {
            BYTE* dst = nullptr; mb->Lock(&dst, nullptr, nullptr);
            memcpy(dst, b->pcm, tam);
            mb->Unlock(); mb->SetCurrentLength(tam);
            Com<IMFSample> s; MFCreateSample(&s);
            s->AddBuffer(mb);
            s->SetSampleTime(b->tempo);
            s->SetSampleDuration((int64_t)b->quadros * 10000000LL / 48000);
            g.escritor->WriteSample(g.fluxoAudio, s);
        }
        free(b->pcm); free(b);
    }
}

static int64_t g_inicio = 0;        // relogio (100 ns) do inicio
static int64_t g_pausaTotal = 0;    // tempo somado das pausas
static int64_t g_pausaDesde = 0;

static int64_t tempoGravacao() {    // 100 ns desde o inicio, sem as pausas
    int64_t t = agora100ns() - g_inicio - g_pausaTotal;
    if (g_pausaDesde) t -= agora100ns() - g_pausaDesde;
    return t;
}

static DWORD WINAPI rodar(void*) {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    MFStartup(MF_VERSION, MFSTARTUP_FULL);
    Gravador* pg = new Gravador();
    Gravador& g = *pg;
    trava(); g.cfg = g_cfg; solta();
    g.saidaW = g.cfg.saidaW & ~1; g.saidaH = g.cfg.saidaH & ~1;
    HRESULT hr = S_OK;

    {   // monitor escolhido
        Monitor m[16];
        int n = listar(m, 16);
        int i = (g.cfg.monitor >= 0 && g.cfg.monitor < n) ? g.cfg.monitor : 0;
        if (n == 0) hr = E_FAIL;
        else { g.mon.adaptador.p = m[i].adaptador.p; g.mon.adaptador.p->AddRef(); g.mon.saida.p = m[i].saida.p; g.mon.saida.p->AddRef(); g.mon.desc = m[i].desc; }
        if (FAILED(hr)) erro(L"nenhum monitor encontrado");
    }
    if (SUCCEEDED(hr)) {
        D3D_FEATURE_LEVEL nivel[] = { D3D_FEATURE_LEVEL_11_1, D3D_FEATURE_LEVEL_11_0 };
        hr = D3D11CreateDevice(g.mon.adaptador, D3D_DRIVER_TYPE_UNKNOWN, nullptr,
                               D3D11_CREATE_DEVICE_BGRA_SUPPORT | D3D11_CREATE_DEVICE_VIDEO_SUPPORT,
                               nivel, 2, D3D11_SDK_VERSION, &g.dev, nullptr, &g.ctx);
        if (FAILED(hr)) erro(L"placa de video: 0x%08lX", hr);
    }
    if (SUCCEEDED(hr)) {
        Com<ID3D10Multithread> mt;
        if (SUCCEEDED(g.dev->QueryInterface(__uuidof(ID3D10Multithread), (void**)&mt))) mt->SetMultithreadProtected(TRUE);
        hr = criarDuplicacao(g);
        if (FAILED(hr)) erro(L"captura da tela: 0x%08lX", hr);
    }
    if (SUCCEEDED(hr)) hr = criarShaders(g);
    if (SUCCEEDED(hr)) hr = criarSaida(g);
    if (SUCCEEDED(hr)) {
        hr = MFCreateDXGIDeviceManager(&g.tokenMan, &g.dxgiMan);
        if (SUCCEEDED(hr)) hr = g.dxgiMan->ResetDevice(g.dev, g.tokenMan);
    }
    if (SUCCEEDED(hr)) {
        // tenta, nessa ordem: GPU + qualidade constante, GPU + VBR, software + qualidade, software + VBR
        HRESULT h2 = E_FAIL;
        bool opcoes[8][3] = { { true, true, true }, { true, true, false }, { true, false, true }, { true, false, false },
                              { false, true, true }, { false, true, false }, { false, false, true }, { false, false, false } };
        wchar_t tentativas[256] = L"";
        int teste = GetEnvironmentVariableW(L"OB_GR_SEM_GPU", nullptr, 0) ? 1 : 0;
        for (auto& o : opcoes) {
            if (teste && o[0]) continue;
            g.gpu = o[0];
            h2 = criarEscritor(g, o[0], o[1], o[2]);
            if (SUCCEEDED(h2)) { trava(); g_est.fragmentado = o[2] ? 1 : 0; g_est.erro[0] = 0; solta(); break; }
            trava(); if (!tentativas[0]) wcsncpy(tentativas, g_est.erro, 255); solta();
        }
        if (FAILED(h2)) { erro(L"%ls", tentativas); }
        hr = h2;
        if (FAILED(hr)) { wchar_t ult[256]; trava(); wcscpy(ult, g_est.erro); solta(); erro(L"codificador de video: %ls", ult); }
    }
    g_hr_inicio = hr;
    if (FAILED(hr)) {
        g.escritor.reset();
        SetEvent(g_pronto);
        delete pg;
        MFShutdown();
        CoUninitialize();
        return 1;
    }

    trava();
    g_est.gravando = 1; g_est.quadros = 0; g_est.perdidos = 0;
    solta();
    g_inicio = agora100ns(); g_pausaTotal = 0; g_pausaDesde = 0;
    SetEvent(g_pronto);

    const int64_t periodo = 10000000LL / g.cfg.fps;
    int64_t k = 0;
    capturar(g, 100);                                   // primeiro quadro da tela
    while (g_rodar) {
        if (g_pausar) {
            if (!g_pausaDesde) g_pausaDesde = agora100ns();
            capturar(g, 20);
            enviarAudio(g);
            continue;
        }
        if (g_pausaDesde) { g_pausaTotal += agora100ns() - g_pausaDesde; g_pausaDesde = 0; }
        int64_t alvo = k * periodo;
        int64_t falta = alvo - tempoGravacao();
        if (falta > 0) {
            capturar(g, (UINT)(falta / 10000));          // espera o momento do quadro olhando a tela
            continue;
        }
        compor(g);
        hr = enviarQuadro(g, alvo, periodo);
        if (FAILED(hr)) { erro(L"ao gravar quadro %lld: 0x%08lX (etapa %d)", (long long)k, hr, g_etapa); break; }
        enviarAudio(g);
        k++;
        int64_t atual = tempoGravacao() / periodo;       // atrasou (PC ocupado)? pula quadros
        if (atual > k + 1) { trava(); g_est.perdidos += atual - k; solta(); k = atual; }
        trava();
        g_est.quadros++;
        g_est.segundos = (double)tempoGravacao() / 1e7;
        solta();
    }
    enviarAudio(g);
    HRESULT hf = g.escritor->Finalize();
    if (FAILED(hf) && !g_est.erro[0]) erro(L"ao fechar o arquivo: 0x%08lX", hf);
    g.escritor.reset();
    trava(); g_est.gravando = 0; g_est.pausado = 0; solta();
    delete pg;
    MFShutdown();
    CoUninitialize();
    return 0;
}

// ------------------------------------------------------------------ interface C
extern "C" __declspec(dllexport) int GrIniciar(const GrConfig* c) {
    if (g_thread) return -1;
    if (!c || c->saidaW < 64 || c->saidaH < 64 || c->saidaW > 7680 || c->saidaH > 4320 || c->fps < 1 || c->fps > 120)
        return -2;
    trava();
    g_cfg = *c;
    g_cfg.arquivo[519] = 0;
    memset(&g_est, 0, sizeof(g_est));
    g_audioBase = -1; g_audioAmostras = 0;
    solta();
    g_rodar = 1; g_pausar = 0;
    g_pronto = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    g_thread = CreateThread(nullptr, 0, rodar, nullptr, 0, nullptr);
    WaitForSingleObject(g_pronto, 15000);
    CloseHandle(g_pronto); g_pronto = NULL;
    if (FAILED(g_hr_inicio)) {
        WaitForSingleObject(g_thread, 5000);
        CloseHandle(g_thread); g_thread = NULL;
        g_rodar = 0;
        return (int)g_hr_inicio;
    }
    return 0;
}

// muda o que pode mudar durante a gravacao (layout, webcam, fundo, cursor)
extern "C" __declspec(dllexport) void GrAtualizar(const GrConfig* c) {
    if (!c) return;
    trava();
    g_cfg.cursor = c->cursor;
    g_cfg.areaX = c->areaX; g_cfg.areaY = c->areaY; g_cfg.areaW = c->areaW; g_cfg.areaH = c->areaH;
    g_cfg.telaX = c->telaX; g_cfg.telaY = c->telaY; g_cfg.telaW = c->telaW; g_cfg.telaH = c->telaH;
    g_cfg.fundo = c->fundo; g_cfg.corFundo = c->corFundo;
    g_cfg.camForma = c->camForma; g_cfg.camX = c->camX; g_cfg.camY = c->camY; g_cfg.camW = c->camW; g_cfg.camH = c->camH;
    g_cfg.camBorda = c->camBorda; g_cfg.camCorBorda = c->camCorBorda;
    solta();
}

// imagem da webcam ja com o efeito, RGBA (alpha = recorte da IA)
extern "C" __declspec(dllexport) void GrQuadroWebcam(const uint8_t* rgba, int w, int h) {
    if (!rgba || w <= 0 || h <= 0 || w > 4096 || h > 4096) return;
    trava();
    if (w != g_camW || h != g_camH) { free(g_cam); g_cam = (uint8_t*)malloc((size_t)w * h * 4); g_camW = w; g_camH = h; }
    if (g_cam) { memcpy(g_cam, rgba, (size_t)w * h * 4); g_camNovo = true; }
    solta();
}

// audio PCM 16 bits estereo 48 kHz; os blocos sao carimbados pela contagem de amostras,
// corrigida pelo relogio se a placa de som "escorregar" mais de 40 ms
extern "C" __declspec(dllexport) void GrAudio(const int16_t* pcm, int quadros) {
    if (!g_thread || !g_rodar || !pcm || quadros <= 0 || quadros > 48000) return;
    if (g_pausar || !g_est.gravando) return;
    int64_t dur = (int64_t)quadros * 10000000LL / 48000;
    int64_t agora = tempoGravacao() - dur;
    if (agora < 0) agora = 0;
    trava();
    if (g_audioBase < 0) { g_audioBase = agora; g_audioAmostras = 0; }
    int64_t esperado = g_audioBase + g_audioAmostras * 10000000LL / 48000;
    if (llabs(esperado - agora) > 400000) { g_audioBase = agora; g_audioAmostras = 0; esperado = agora; }
    BlocoAudio* b = (BlocoAudio*)malloc(sizeof(BlocoAudio));
    b->pcm = (int16_t*)malloc((size_t)quadros * 4);
    memcpy(b->pcm, pcm, (size_t)quadros * 4);
    b->quadros = quadros; b->tempo = esperado; b->prox = nullptr;
    if (g_audioFim) g_audioFim->prox = b; else g_audioIni = b;
    g_audioFim = b;
    g_audioAmostras += quadros;
    solta();
}

extern "C" __declspec(dllexport) void GrPausar(int pausar) {
    g_pausar = pausar ? 1 : 0;
    trava(); g_est.pausado = g_pausar; g_audioBase = -1; solta();
}

extern "C" __declspec(dllexport) int GrParar() {
    if (!g_thread) return 0;
    g_rodar = 0;
    WaitForSingleObject(g_thread, 30000);
    CloseHandle(g_thread); g_thread = NULL;
    trava();
    while (g_audioIni) { BlocoAudio* b = g_audioIni; g_audioIni = b->prox; free(b->pcm); free(b); }
    g_audioFim = nullptr;
    solta();
    return 0;
}

extern "C" __declspec(dllexport) void GrEstado(GrEstadoInfo* e) {
    if (!e) return;
    trava();
    *e = g_est;
    solta();
    WIN32_FILE_ATTRIBUTE_DATA fa;
    if (GetFileAttributesExW(g_cfg.arquivo, GetFileExInfoStandard, &fa))
        e->bytes = ((int64_t)fa.nFileSizeHigh << 32) | fa.nFileSizeLow;
}


// ------------------------------------------------------------------ som do computador (WASAPI loopback)
// Captura o que esta tocando na saida padrao, ja convertido para 48 kHz estereo float.
// O Python le com GrSomLer e mistura com o microfone.
DEFINE_GUID(OB_CLSID_MMDeviceEnumerator, 0xbcde0395, 0xe52f, 0x467c, 0x8e, 0x3d, 0xc4, 0x57, 0x92, 0x91, 0x69, 0x2e);
DEFINE_GUID(OB_IID_IMMDeviceEnumerator, 0xa95664d2, 0x9614, 0x4f35, 0xa7, 0x46, 0xde, 0x8d, 0xb6, 0x36, 0x17, 0xe6);
DEFINE_GUID(OB_IID_IAudioClient, 0x1cb9ad4c, 0xdbfa, 0x4c32, 0xb1, 0x78, 0xc2, 0xf5, 0x68, 0xa7, 0x03, 0xb2);
DEFINE_GUID(OB_IID_IAudioCaptureClient, 0xc8adbd64, 0xe71e, 0x48a0, 0xa4, 0xde, 0x18, 0x5c, 0x39, 0x5c, 0xd3, 0x17);

static const int SOM_CAP = 48000 * 2;          // 2 s de folga (quadros estereo)
static float* g_som = nullptr;                 // anel intercalado L R
static int g_somIni = 0, g_somQtd = 0;
static HANDLE g_somThread = NULL;
static volatile LONG g_somRodar = 0;
static CRITICAL_SECTION g_somTrava;
static bool g_somTravaOk = false;
static wchar_t g_somErro[160] = L"";

static void somGuardar(const float* x, int quadros) {
    EnterCriticalSection(&g_somTrava);
    for (int i = 0; i < quadros; i++) {
        if (g_somQtd == SOM_CAP) { g_somIni = (g_somIni + 1) % SOM_CAP; g_somQtd--; }   // descarta o mais velho
        int pos = (g_somIni + g_somQtd) % SOM_CAP;
        g_som[pos * 2] = x ? x[i * 2] : 0.f;
        g_som[pos * 2 + 1] = x ? x[i * 2 + 1] : 0.f;
        g_somQtd++;
    }
    LeaveCriticalSection(&g_somTrava);
}

static DWORD WINAPI somRodar(void*) {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    Com<IMMDeviceEnumerator> en; Com<IMMDevice> disp; Com<IAudioClient> cli; Com<IAudioCaptureClient> cap;
    HRESULT hr = CoCreateInstance(OB_CLSID_MMDeviceEnumerator, nullptr, CLSCTX_ALL, OB_IID_IMMDeviceEnumerator, (void**)&en);
    if (SUCCEEDED(hr)) hr = en->GetDefaultAudioEndpoint(eRender, eConsole, &disp);
    if (SUCCEEDED(hr)) hr = disp->Activate(OB_IID_IAudioClient, CLSCTX_ALL, nullptr, (void**)&cli);
    WAVEFORMATEXTENSIBLE wf = {};
    wf.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE; wf.Format.nChannels = 2; wf.Format.nSamplesPerSec = 48000;
    wf.Format.wBitsPerSample = 32; wf.Format.nBlockAlign = 8; wf.Format.nAvgBytesPerSec = 48000 * 8;
    wf.Format.cbSize = 22; wf.Samples.wValidBitsPerSample = 32;
    wf.dwChannelMask = SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT; wf.SubFormat = KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;
    if (SUCCEEDED(hr))
        hr = cli->Initialize(AUDCLNT_SHAREMODE_SHARED,
                             AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                             2000000, 0, (WAVEFORMATEX*)&wf, nullptr);
    if (SUCCEEDED(hr)) hr = cli->GetService(OB_IID_IAudioCaptureClient, (void**)&cap);
    if (SUCCEEDED(hr)) hr = cli->Start();
    if (FAILED(hr)) { _snwprintf(g_somErro, 159, L"som do computador: 0x%08lX", hr); g_somRodar = 0; CoUninitialize(); return 1; }
    // sem nada tocando o Windows nao entrega pacotes: completa com silencio pelo relogio
    int64_t t0 = agora100ns(), entregues = 0;
    while (g_somRodar) {
        Sleep(10);
        UINT32 n = 0;
        while (SUCCEEDED(cap->GetNextPacketSize(&n)) && n > 0) {
            BYTE* dados; UINT32 q; DWORD fl;
            if (FAILED(cap->GetBuffer(&dados, &q, &fl, nullptr, nullptr))) break;
            somGuardar((fl & AUDCLNT_BUFFERFLAGS_SILENT) ? nullptr : (float*)dados, (int)q);
            entregues += q;
            cap->ReleaseBuffer(q);
        }
        int64_t devido = (agora100ns() - t0) * 48000 / 10000000;
        if (devido - entregues > 4800) {           // >100 ms sem pacotes = silencio
            int falta = (int)(devido - entregues - 960);
            somGuardar(nullptr, falta);
            entregues += falta;
        }
    }
    cli->Stop();
    CoUninitialize();
    return 0;
}

extern "C" __declspec(dllexport) int GrSomIniciar() {
    if (g_somThread) return 0;
    if (!g_somTravaOk) { InitializeCriticalSection(&g_somTrava); g_somTravaOk = true; }
    if (!g_som) g_som = (float*)malloc(sizeof(float) * SOM_CAP * 2);
    g_somIni = g_somQtd = 0; g_somErro[0] = 0;
    g_somRodar = 1;
    g_somThread = CreateThread(nullptr, 0, somRodar, nullptr, 0, nullptr);
    Sleep(150);
    return g_somRodar ? 0 : -1;
}

// copia ate 'max' quadros estereo (float -1..1) para buf; devolve quantos
extern "C" __declspec(dllexport) int GrSomLer(float* buf, int max) {
    if (!g_somTravaOk || !buf || max <= 0) return 0;
    EnterCriticalSection(&g_somTrava);
    int n = g_somQtd < max ? g_somQtd : max;
    for (int i = 0; i < n; i++) {
        int pos = (g_somIni + i) % SOM_CAP;
        buf[i * 2] = g_som[pos * 2]; buf[i * 2 + 1] = g_som[pos * 2 + 1];
    }
    g_somIni = (g_somIni + n) % SOM_CAP; g_somQtd -= n;
    LeaveCriticalSection(&g_somTrava);
    return n;
}

extern "C" __declspec(dllexport) int GrSomQtd() {
    if (!g_somTravaOk) return 0;
    EnterCriticalSection(&g_somTrava); int n = g_somQtd; LeaveCriticalSection(&g_somTrava);
    return n;
}

extern "C" __declspec(dllexport) void GrSomParar() {
    if (!g_somThread) return;
    g_somRodar = 0;
    WaitForSingleObject(g_somThread, 3000);
    CloseHandle(g_somThread); g_somThread = NULL;
}

extern "C" __declspec(dllexport) const wchar_t* GrSomErro() { return g_somErro; }
