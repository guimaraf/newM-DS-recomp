# New Super Mario Bros. DS - Static Recompilation (Experimental)

Experimental static recompilation project for New Super Mario Bros. DS (Nintendo DS), based on the `ndsrecomp` architecture.

## Target Metadata

* **Primary ROM:** `roms/New Super Mario Bros. (USA).nds`
* **Game Code:** `A2DE` (Revision 0)
* **ROM SHA-1:** `a22713711b5cd58dfbafc9688dadea66c59888ce`
* **ARM9:** Base `0x02000000`, Entry `0x02000800`, Uncompressed size 581,776 bytes
* **ARM7:** Base `0x02380000`, Entry `0x02380000`, Size 165,536 bytes
* **Overlays:** 131 overlays cataloged in `generated/inputs/overlays.json`
* **Save Type:** EEPROM 8 KB (64 Kbit)

## Project Structure

* `assets/`: Box art and graphical assets for the launcher.
* `config/`: Metadata extracted from the decompiled project (NSMB-Decomp A2DE).
  * `symbols.txt`: Boundaries and calling conventions for 1,367+ functions.
  * `delinks.txt`: Code and data sections (.text, .rodata, .init).
  * `relocs.txt`: Pointer and call relocation table.
* `generated/inputs/`: Uncompressed binaries and TOML manifests for the compiler.
* `ndsrecomp/`: Junction to the `ndsrecomp` framework.
* `src/launcher_main.cpp`: recomp-ui graphical frontend with display options and a 60 FPS limit.
* `tools/prepare_nsmb.py`: Python pipeline for ROM extraction and configuration file generation.

## Build Requirements

* **Toolchain:** MSYS2 MinGW64 (`C:\msys64\mingw64\bin\gcc.exe`, `g++.exe`, `ninja.exe`, `cmake.exe`).
* **Dependencies:** SDL3, OpenGL 4.3, Python with `ndspy`.
