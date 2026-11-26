# Histórico de versões / Changelog

## 1.0.1 — 25/11/2026
- **Microfones lidos direto da API de áudio do Windows (WASAPI)**: a lista é sempre a atual. Um microfone
  plugado ou tirado aparece ou some sozinho (o app confere a cada 2 s), sem precisar reabrir.
- Correção: o botão ↻ da lista de microfones podia travar e fechar o app (falha no MMDevAPI.dll do Windows), e
  tirar um microfone podia esvaziar a lista. A causa era religar a biblioteca de áudio (PortAudio) para
  enxergar microfones novos, o que não é mais necessário.
- **Volume por microfone** (-12 a +24 dB, guardado para cada microfone) e **volume automático**, que nivela
  a voz: sobe microfone baixo (ex.: lapela) e segura microfone alto. Com **limitador**, para não distorcer.
- O medidor mostra o nível já com o volume e fica vermelho se o microfone chegar estourado.
- **Sem "tremida" no começo**: o redutor de ruído (RNNoise) aprende o ambiente nos primeiros 0,3 s com o som
  em silêncio e entra suave.

## 1.0.0 — 25/11/2026
**Primeira versão pública. / First public release.**

### Câmera para chamadas
- Fundo desfocado, imagem, vídeo, cor ou sem efeito, com a IA Robust Video Matting na placa de vídeo
  (AMD, NVIDIA e Intel via DirectML) ou no processador.
- Câmera virtual "OpenBokeh Camera": a clássica, em 64 e 32 bits, e a do Windows 11.
- Correção de luz, redução de ruído, retoque de pele, enquadramento automático, câmera redonda, "Volto já" e perfis.
- Microfone sem ruído (RNNoise) para as chamadas, usando o VB-CABLE.

### Gravação de tela (nova)
- Grava a tela inteira, uma região ou uma janela (que é acompanhada).
- Formato 16:9 (1080p/1440p) ou o nativo do monitor, com encaixe com faixas, preencher ou 1:1.
- Webcam por cima: círculo, retângulo ou só você.
- Microfone escolhido na página, com redução de ruído e medidor, e o som do computador.
- Texto nítido em 1:1 com cor BT.709 e codificação H.264/HEVC na placa de vídeo. Medido: SSIM 0,999 no texto, de
  1,2 a 2,6 GB/h.
- Contagem 3-2-1, mini barra (pausar/parar) que não aparece no vídeo, atalhos Ctrl+Alt+R/P/S, gravações recentes e
  checagem de disco.

### Interface, segurança e qualidade
- Tela principal com duas áreas: "Câmera" e "Gravar tela".
- Configurações completas, bandeja, iniciar com o Windows, português e inglês.
- DLLs do Windows carregadas só do System32; configurações validadas.
- O app trata o "acesso controlado a pastas" do Windows e caminhos com acento.
- Testes automáticos em `testes/`. O registro da sessão anterior fica guardado.

## 0.9.0
- Interface em inglês: segue o idioma do Windows, e dá para trocar em Configurações › Geral.
- Correção: o instalador não criava a câmera do Windows 11 (o comando do `rundll32` estava com
  as aspas no lugar errado). Agora ele confere se a câmera apareceu e anota os passos em
  `%ProgramData%\OpenBokeh\instalacao.log`.
- Correção: o desinstalador era empacotado como pasta, e a instalação falhava com
  "Permission denied". Agora a construção confere o conteúdo do instalador.

## 0.8.0
- Câmera no padrão do Windows 11 (Media Foundation), vista pelo app Câmera, pelos apps da Store
  e pelo novo Teams.

## 0.7.0
- Instalador menor: de 144 para 105 MB, e de 422 para cerca de 250 MB instalado.
- CPU mais rápida: qualidade "Leve", entrada reduzida e limite de threads da IA.
- Aviso quando a webcam entrega poucos quadros (pouca luz).

## 0.6.0
- Câmera virtual também em 32 bits, para apps antigos.

## 0.5.0
- Janela de Configurações: saída em 720p/1080p, limite de FPS, qualidade automática, atalhos
  configuráveis, ajustes do driver da webcam e reparo da câmera.

## 0.4.0
- Avisos amigáveis (webcam ocupada, ausente, desconectada ou bloqueada), reconexão automática,
  barra de menus e ajuda.

## 0.3.0
- Ícone na bandeja, iniciar com o Windows e modo espera automático.

## 0.2.x
- Correção de luz, enquadramento automático, fundo em vídeo, tela "Volto já" e perfis.
- Janela Sobre (privacidade, créditos e licença GPL-3.0).

## 0.1.x
- Primeira versão: desfoque com IA na GPU (DirectML), câmera virtual própria e instalador.
