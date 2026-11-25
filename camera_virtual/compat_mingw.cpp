// O streams.cpp chama __security_init_cookie (rotina do runtime do MSVC).
// No MinGW o cookie de seguranca ja e inicializado pelo proprio runtime.
extern "C" void __security_init_cookie(void) {}
