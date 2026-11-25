"""
Catalogo de mensagens do OpenBokeh: cada problema conhecido vira um aviso
claro (titulo + explicacao + o que fazer + botao de acao), em vez de um erro
tecnico. O motor so informa o codigo; a interface decide como mostrar.

nivel: "info" (azul, some sozinho), "aviso" (amarelo), "erro" (vermelho)
acao:  codigo de uma acao que a interface sabe executar
"""

import winreg
from i18n import _

MENSAGENS = {
    "webcam_ocupada": dict(
        nivel="aviso", titulo=_("A webcam está sendo usada por outro programa"),
        texto=_("A {camera} foi aberta diretamente por outro app (por exemplo Meet, Zoom, Teams ou OBS)."),
        dica=_("Nesse programa, troque a câmera para “OpenBokeh Camera”. O OpenBokeh tenta de novo sozinho."),
        acao=("tentar", _("Tentar agora"))),
    "webcam_ausente": dict(
        nivel="aviso", titulo=_("Nenhuma webcam encontrada"),
        texto=_("Não encontramos nenhuma webcam conectada ao computador."),
        dica=_("Conecte a webcam (ou confira o cabo USB). Assim que ela aparecer, o OpenBokeh liga sozinho."),
        acao=("tentar", _("Procurar de novo"))),
    "webcam_bloqueada": dict(
        nivel="erro", titulo=_("O Windows está bloqueando o acesso à câmera"),
        texto=_("A privacidade do Windows não permite que aplicativos da área de trabalho usem a câmera."),
        dica=_("Em Configurações › Privacidade › Câmera, ative “Permitir que aplicativos da área de trabalho "
             "acessem a câmera”."),
        acao=("privacidade", _("Abrir configurações"))),
    "webcam_desconectada": dict(
        nivel="aviso", titulo=_("A webcam parou de enviar imagem"),
        texto=_("A {camera} deixou de responder — talvez tenha sido desconectada ou outro app a tomou."),
        dica=_("Confira o cabo USB. O OpenBokeh reconecta sozinho assim que ela voltar."),
        acao=("tentar", _("Reconectar"))),
    "gpu_indisponivel": dict(
        nivel="info", titulo=_("IA rodando no processador (modo mais lento)"),
        texto=_("A placa de vídeo não pôde ser usada pela IA, então o OpenBokeh está usando o processador."),
        dica=_("O OpenBokeh já se ajustou para o processador (qualidade mais leve). Se o PC tiver vídeo da Intel ou "
             "AMD, atualizar o driver de vídeo pode liberar a aceleração."),
        acao=None),
    "camera_virtual_ausente": dict(
        nivel="erro", titulo=_("A câmera virtual não está instalada"),
        texto=_("A “OpenBokeh Camera” não foi encontrada neste computador, então outros apps não verão o efeito."),
        dica=_("Reinstale o OpenBokeh com o instalador oficial (ele registra a câmera virtual)."),
        acao=None),
    "ia_falhou": dict(
        nivel="erro", titulo=_("A IA encontrou um problema"),
        texto=_("O recorte da imagem falhou ({detalhe})."),
        dica=_("O OpenBokeh tenta se recuperar sozinho. Se continuar, troque a “Qualidade da IA” na aba Recorte."),
        acao=None),
    "fundo_imagem": dict(
        nivel="aviso", titulo=_("Não foi possível abrir a imagem de fundo"),
        texto=_("O arquivo “{arquivo}” não existe mais ou não é uma imagem válida."),
        dica=_("Escolha outra imagem (JPG, PNG ou WEBP). Enquanto isso, o fundo usa a cor sólida."),
        acao=("escolher_imagem", _("Escolher imagem"))),
    "fundo_video": dict(
        nivel="aviso", titulo=_("Não foi possível abrir o vídeo de fundo"),
        texto=_("O arquivo “{arquivo}” não existe mais ou está num formato não suportado."),
        dica=_("Escolha outro vídeo em MP4, MOV ou WMV. Enquanto isso, o fundo usa a cor sólida."),
        acao=("escolher_video", _("Escolher vídeo"))),
    "webcam_lenta": dict(
        nivel="info", titulo=_("A webcam está enviando só {fps} quadros por segundo"),
        texto=_("Com pouca luz, a {camera} aumenta o tempo de exposição e manda menos quadros — "
              "a imagem fica lenta mesmo sem o OpenBokeh."),
        dica=_("Acenda uma luz voltada para o rosto, ou nos ajustes da webcam desligue “compensação de pouca luz” "
             "(ou “prioridade de exposição”)."),
        acao=("ajustes_webcam", _("Ajustes da webcam"))),
    "qualidade_reduzida": dict(
        nivel="info", titulo=_("Qualidade da IA ajustada para “{qualidade}”"),
        texto=_("O computador não estava conseguindo manter a imagem fluida, então o OpenBokeh reduziu a qualidade."),
        dica=_("Você pode mudar isso em Configurações › Desempenho."),
        acao=None),
    "atalho_ocupado": dict(
        nivel="info", titulo=_("Atalho {atalho} indisponível"),
        texto=_("Outro programa já usa esse atalho de teclado."),
        dica=_("Escolha outro em Configurações › Atalhos."),
        acao=None),
    "inesperado": dict(
        nivel="erro", titulo=_("Algo deu errado"),
        texto=_("Aconteceu um erro inesperado, mas o OpenBokeh continua funcionando."),
        dica=_("Se repetir, use Ajuda › Copiar diagnóstico e envie junto com o arquivo de registro."),
        acao=("registro", _("Abrir registro"))),
}


def montar(codigo, **dados):
    """Devolve (nivel, titulo, texto, dica, acao) com os dados preenchidos."""
    m = MENSAGENS.get(codigo, MENSAGENS["inesperado"])

    def fmt(t):
        try:
            return t.format(**dados)
        except (KeyError, IndexError):
            return t
    return m["nivel"], fmt(m["titulo"]), fmt(m["texto"]), fmt(m["dica"]), m["acao"]


def camera_bloqueada_pelo_windows():
    """Privacidade do Windows: 'Permitir que aplicativos da area de trabalho
    acessem a camera' desligado (para o usuario ou para o computador)."""
    chave = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    for raiz, sub in ((winreg.HKEY_CURRENT_USER, chave), (winreg.HKEY_LOCAL_MACHINE, chave),
                      (winreg.HKEY_CURRENT_USER, chave + r"\NonPackaged")):
        try:
            with winreg.OpenKey(raiz, sub) as k:
                valor, _tipo = winreg.QueryValueEx(k, "Value")
                if str(valor).lower() == "deny":
                    return True
        except OSError:
            continue
    return False
