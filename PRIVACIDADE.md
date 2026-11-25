# Política de privacidade do OpenBokeh

*Última atualização: 24 de novembro de 2026*

**Resumo: o OpenBokeh não coleta, não guarda e não envia nenhum dado seu. Tudo acontece
no seu computador.**

## O que o OpenBokeh faz com a sua imagem
- A imagem da webcam é processada **somente no seu computador**, na memória, quadro a quadro.
- O resultado vai apenas para a câmera virtual "OpenBokeh Camera", que só os programas que
  **você** escolher (Meet, Zoom, OBS…) conseguem ler.
- Nenhum quadro de vídeo é gravado em disco nem enviado para a internet.

## Microfone sem ruído (opcional, desligado por padrão)
- Quando ligado, o som do microfone é limpo **só no seu computador**, em blocos de 10 ms na memória,
  e vai direto para o cabo de áudio virtual (VB-CABLE). Nada é gravado nem enviado.
- O botão "Gravar e ouvir" guarda 4 segundos na memória só para tocar o teste, e descarta em seguida.

## Gravação de tela (só quando você manda gravar)
- Os vídeos são salvos **só no seu computador**, na pasta que você escolher (padrão: Vídeos\OpenBokeh).
- Nada é enviado. O app não grava nada sozinho: a gravação começa e termina pelo botão, menu ou atalho.
- Na página "Gravar tela", o medidor de nível usa o microfone só para mostrar se ele está captando: nada é
  gravado. O microfone é solto quando você sai da página ou minimiza o app.

## Conexão com a internet
- A versão instalada **não se conecta à internet**: os modelos de IA já vêm no instalador.
- Não há contas, anúncios, telemetria, estatísticas de uso ou verificação de atualizações.
- O único acesso à web é o botão "Abrir site do VB-CABLE", que abre o seu navegador quando você clica.

## O que fica salvo no seu computador
- Suas configurações (efeito, ajustes, perfis, caminhos das imagens/vídeos de fundo que você
  escolheu) ficam em `%APPDATA%\OpenBokeh\config.json`.
- Um registro técnico (`openbokeh.log`) na mesma pasta, com mensagens de erro, para ajudar a
  resolver problemas. Ele não contém imagens; a cada abertura do app o registro anterior vira
  `openbokeh-anterior.log` (só o da vez anterior é guardado).
- O instalador anota os passos da instalação em `%ProgramData%\OpenBokeh\instalacao.log`
  (só nomes de arquivos e códigos de resultado). Ele é apagado ao desinstalar.
- Ao desinstalar, você pode escolher apagar essa pasta.

## Outros programas
Os programas de videochamada que recebem a imagem da "OpenBokeh Camera" têm suas próprias
políticas de privacidade, que não dependem do OpenBokeh.

## Código aberto
O OpenBokeh é software livre (GPL-3.0). Qualquer pessoa pode conferir no código-fonte que
estas afirmações são verdadeiras.
