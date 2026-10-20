# New Super Mario Bros. DS - Static Recompilation (Experimental)

Projeto experimental de recompilação estática de New Super Mario Bros. DS (Nintendo DS) baseado na arquitetura `ndsrecomp`.

## Metadados do Alvo
* **ROM Primária:** `roms/New Super Mario Bros. (USA).nds`
* **Game Code:** `A2DE` (Revisão 0)
* **ROM SHA-1:** `a22713711b5cd58dfbafc9688dadea66c59888ce`
* **ARM9:** Base `0x02000000`, Entry `0x02000800`, Tamanho descompactado 581.776 bytes
* **ARM7:** Base `0x02380000`, Entry `0x02380000`, Tamanho 165.536 bytes
* **Overlays:** 131 overlays catalogados em `generated/inputs/overlays.json`
* **Save Type:** EEPROM 8 KB (64 Kbit)

## Estrutura do Projeto
* `assets/`: Boxart e recursos gráficos do launcher.
* `config/`: Metadados extraídos do projeto decompilado (NSMB-Decomp A2DE).
  * `symbols.txt`: Limites e convenções de chamadas de 1.367+ funções.
  * `delinks.txt`: Seções de código e dados (.text, .rodata, .init).
  * `relocs.txt`: Tabela de realocações de ponteiros e chamadas.
* `generated/inputs/`: Binários descompactados e manifests TOML para o compilador.
* `ndsrecomp/`: Junction para o framework `ndsrecomp`.
* `src/launcher_main.cpp`: Frontend gráfico recomp-ui com opções de tela e trava em 60 FPS.
* `tools/prepare_nsmb.py`: Pipeline Python para extração da ROM e geração dos arquivos de configuração.

## Requisitos de Build
* **Toolchain:** MSYS2 MinGW64 (`C:\msys64\mingw64\bin\gcc.exe`, `g++.exe`, `ninja.exe`, `cmake.exe`).
* **Dependências:** SDL3, OpenGL 4.3, Python com `ndspy`.
