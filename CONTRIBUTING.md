# Como contribuir / Contributing

Obrigado por querer ajudar! / Thanks for helping!

## Relatar um problema / Reporting a bug
Abra uma [issue](https://github.com/cleversonmeyer/OpenBokeh/issues) com / Open an issue with:
- o que aconteceu e o que você esperava / what happened and what you expected;
- versão do OpenBokeh, do Windows e a placa de vídeo / OpenBokeh, Windows and GPU versions;
- o diagnóstico (Ajuda › Copiar diagnóstico) e o `openbokeh.log` de `%APPDATA%\OpenBokeh` / the diagnostics
  and `openbokeh.log`.

## Enviar código / Sending code
1. Faça um fork e uma branch / fork and create a branch.
2. Rode o app pelo código (`instalar.bat`, `iniciar.bat`) e os testes / run the app and the tests:
   `venv\Scripts\python -m unittest discover -s testes -v`
3. Regras do projeto / project rules:
   - O código e os comentários são em português (as palavras e nomes do projeto também).
     Code and comments are in Portuguese.
   - **Todo texto da interface usa `_()`** e precisa da tradução em `traducoes_en.py` (o teste confere).
     **Every UI string uses `_()`** and needs an entry in `traducoes_en.py` (a test checks this).
   - Textos com variável: `_("... {nome} ...").format(nome=...)`, nunca f-string dentro de `_()`.
   - Nada pode enviar dados para a internet sem a pessoa pedir. / Nothing may send data online without the user asking.
   - DLLs nativas: compile com o Zig 0.13 (`*/compilar.sh`). / Native DLLs: build with Zig 0.13.
4. Abra o Pull Request explicando o que muda e como você testou. / Open a PR describing the change and how you tested it.

Ao contribuir, você concorda em licenciar sua contribuição sob a GPL-3.0-or-later.
By contributing you agree to license your contribution under GPL-3.0-or-later.
