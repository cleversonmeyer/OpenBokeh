# Segurança / Security

## Como relatar uma falha / How to report a vulnerability
**Português:** encontrou uma falha de segurança? Não abra uma issue pública. Use a opção
**"Report a vulnerability"** na aba *Security* deste repositório (relato privado do GitHub). Descreva o que
acontece, como reproduzir e a versão do OpenBokeh (menu Ajuda › Sobre). A resposta vem assim que possível, e a
correção sai numa nova versão, com crédito a você se quiser.

**English:** found a security issue? Please do not open a public issue. Use **"Report a vulnerability"** in this
repository's *Security* tab (GitHub private reporting). Include what happens, how to reproduce it and the OpenBokeh
version (Help › About).

## O que o OpenBokeh faz para ser seguro / What OpenBokeh does to stay safe
- **Rede:** não se conecta à internet. Não há conta, telemetria ou atualização automática.
  **Network:** no network access, accounts, telemetry or auto-update.
- **DLLs do sistema:** são carregadas só do System32, o que evita *DLL planting*.
  **System DLLs** are loaded from System32 only.
- **Memória compartilhada das câmeras virtuais:** tem os tamanhos validados, e a do Windows 11 tem permissões
  restritas.
  **Virtual-camera shared memory** sizes are validated, with restricted permissions for the Windows 11 camera.
- **Configurações:** as lidas ou importadas são validadas, e o que estiver fora do esperado volta ao padrão.
  **Settings**, loaded or imported, are validated; unexpected values fall back to defaults.
- **Gravação:** só começa por ação da pessoa (botão, menu ou atalho) e mostra um indicador enquanto grava.
  **Recording** only starts by user action and is always indicated while running.

## Versões com suporte / Supported versions
Só a versão mais recente recebe correções. / Only the latest release receives fixes.
