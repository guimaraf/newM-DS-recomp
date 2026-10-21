cmake_minimum_required(VERSION 3.20)
project(NewSuperMarioBrosDSRecomp VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(NDSRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/ndsrecomp" CACHE PATH
    "Path to the ndsrecomp framework checkout")

if(NOT EXISTS "${NDSRECOMP_ROOT}/recompiler/CMakeLists.txt")
    message(FATAL_ERROR
        "ndsrecomp framework not found at ${NDSRECOMP_ROOT}. "
        "Create the junction or pass -DNDSRECOMP_ROOT=<path>.")
endif()

include("${NDSRECOMP_ROOT}/cmake/NdsCompilerCache.cmake")
include("${NDSRECOMP_ROOT}/cmake/NdsJobPools.cmake")
if(EXISTS "${NDSRECOMP_ROOT}/external/arm-recomp-core/cmake/ArmRecompCore.cmake")
    include("${NDSRECOMP_ROOT}/external/arm-recomp-core/cmake/ArmRecompCore.cmake")
    arm_recomp_core_include_dirs(NDS_ARM_RECOMP_INCLUDE_DIRS armv4t)
else()
    set(NDS_ARM_RECOMP_INCLUDE_DIRS)
endif()

# Build the ndsrecomp ARM recompiler
add_subdirectory(
    "${NDSRECOMP_ROOT}/recompiler"
    "${CMAKE_BINARY_DIR}/ndsrecomp-recompiler")

set(NSMB_ROM "${CMAKE_CURRENT_SOURCE_DIR}/../roms/New Super Mario Bros. (USA).nds" CACHE FILEPATH
    "Path to the retail NSMB DS (USA) ROM")
set(NSMB_CONFIG_DIR "${CMAKE_CURRENT_SOURCE_DIR}/config" CACHE PATH
    "Path to config directory with symbols.txt/delinks.txt")
set(NSMB_GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/generated")
set(NSMB_INPUT_DIR "${NSMB_GENERATED_DIR}/inputs")
set(NSMB_RECOMP_DIR "${NSMB_GENERATED_DIR}/recomp")
set(NSMB_BANK_STAMPS)

set(_nsmb_candidate_python
    "${CMAKE_CURRENT_SOURCE_DIR}/../supermario64dsrecomp/third_party/sm64ds-decomp/.venv/Scripts/python.exe")
if(EXISTS "${_nsmb_candidate_python}")
    set(NSMB_PYTHON "${_nsmb_candidate_python}" CACHE FILEPATH "Python interpreter with ndspy installed")
else()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    set(NSMB_PYTHON "${Python3_EXECUTABLE}" CACHE FILEPATH "Python interpreter with ndspy installed")
endif()

set(NSMB_PREP_OUTPUTS
    "${NSMB_INPUT_DIR}/arm9.bin"
    "${NSMB_INPUT_DIR}/arm9_runtime.bin"
    "${NSMB_INPUT_DIR}/arm7.bin"
    "${NSMB_INPUT_DIR}/arm9.toml"
    "${NSMB_INPUT_DIR}/arm9_runtime.toml"
    "${NSMB_INPUT_DIR}/arm7.toml"
    "${NSMB_INPUT_DIR}/arm7_wram.toml"
    "${NSMB_INPUT_DIR}/arm9_itcm.toml"
    "${NSMB_INPUT_DIR}/overlays/arm9_overlay_009.bin"
    "${NSMB_INPUT_DIR}/overlays/arm9_overlay_009.toml")
file(GLOB NSMB_SEED_INPUTS CONFIGURE_DEPENDS "${NSMB_CONFIG_DIR}/seeds/*.toml")

add_custom_command(
    OUTPUT ${NSMB_PREP_OUTPUTS}
    COMMAND "${NSMB_PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_nsmb.py"
            --rom "${NSMB_ROM}"
            --config-dir "${NSMB_CONFIG_DIR}"
            --out "${NSMB_INPUT_DIR}"
    DEPENDS
        "${NSMB_ROM}"
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/prepare_nsmb.py"
        "${NSMB_CONFIG_DIR}/symbols.txt"
        "${NSMB_CONFIG_DIR}/delinks.txt"
        ${NSMB_SEED_INPUTS}
    COMMENT "Preparing NSMB DS code images and TOML manifests")
add_custom_target(nsmb_prepare DEPENDS ${NSMB_PREP_OUTPUTS})

file(GLOB NSMB_ARM9_SOURCES CONFIGURE_DEPENDS
    "${NSMB_RECOMP_DIR}/*arm9*_[0-9][0-9].c"
    "${NSMB_RECOMP_DIR}/*arm9*_dispatch.c")
file(GLOB NSMB_ARM7_SOURCES CONFIGURE_DEPENDS
    "${NSMB_RECOMP_DIR}/*arm7*_[0-9][0-9].c"
    "${NSMB_RECOMP_DIR}/*arm7*_dispatch.c")
# Include new banks on the first build, before the glob can see them.
set(NSMB_EXTRA_BANK_SOURCES
    "${NSMB_RECOMP_DIR}/nsmb_arm9_runtime_00.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_runtime_01.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_runtime_02.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_runtime_03.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_runtime_dispatch.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_ov009_00.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_ov009_01.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm9_ov009_dispatch.c")
list(APPEND NSMB_ARM9_SOURCES ${NSMB_EXTRA_BANK_SOURCES})
list(REMOVE_DUPLICATES NSMB_ARM9_SOURCES)
set(NSMB_BANK_SOURCES ${NSMB_ARM9_SOURCES} ${NSMB_ARM7_SOURCES})

set(NSMB_BANKS_STAMP "${NSMB_RECOMP_DIR}/nsmb_banks.stamp")
option(NSMB_COALESCE_FALLTHROUGHS
    "Coalesce validated ARM9 ITCM/runtime fallthroughs" ON)
set(NSMB_PRECEDING_DISPATCH_DIR "${NDSRECOMP_ROOT}/generated" CACHE PATH
    "Framework dispatch directory used by the runner (NDS_GENERATED_DIR if overridden)")
file(GLOB NSMB_PRECEDING_DISPATCH_INPUTS CONFIGURE_DEPENDS
    "${NSMB_PRECEDING_DISPATCH_DIR}/*_dispatch.c")
if(NSMB_COALESCE_FALLTHROUGHS)
    set(NSMB_COALESCE_ARG --coalesce-fallthroughs)
else()
    set(NSMB_COALESCE_ARG --no-coalesce-fallthroughs)
endif()
# Track option changes for Makefile generators too, whose timestamp rules do
# not necessarily re-run an output just because its command line changed.
set(NSMB_EMISSION_SETTINGS "${CMAKE_CURRENT_BINARY_DIR}/nsmb_emission_settings.txt")
file(GENERATE OUTPUT "${NSMB_EMISSION_SETTINGS}"
    CONTENT "${NSMB_COALESCE_ARG}\n${NSMB_PRECEDING_DISPATCH_DIR}\n${NSMB_PRECEDING_DISPATCH_INPUTS}\n")
add_custom_command(
    OUTPUT "${NSMB_BANKS_STAMP}"
    BYPRODUCTS ${NSMB_EXTRA_BANK_SOURCES}
    COMMAND ${CMAKE_COMMAND} -E make_directory "${NSMB_RECOMP_DIR}"
    COMMAND "${NSMB_PYTHON}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/emit_all_banks.py"
            --recompiler $<TARGET_FILE:nds_recompile>
            --preceding-dispatch-dir "${NSMB_PRECEDING_DISPATCH_DIR}"
            ${NSMB_COALESCE_ARG}
    COMMAND ${CMAKE_COMMAND} -E touch "${NSMB_BANKS_STAMP}"
    DEPENDS nds_recompile ${NSMB_PREP_OUTPUTS} "${CMAKE_CURRENT_SOURCE_DIR}/tools/emit_all_banks.py"
            "${NSMB_EMISSION_SETTINGS}" ${NSMB_PRECEDING_DISPATCH_INPUTS}
    COMMENT "Statically recompiling NSMB ARM9, ARM7, runtime WRAM/ITCM, and overlays")
list(APPEND NSMB_BANK_STAMPS "${NSMB_BANKS_STAMP}")

add_custom_target(nsmb_generate_banks DEPENDS ${NSMB_BANK_STAMPS})

add_library(nsmb_recompiled_banks STATIC ${NSMB_BANK_SOURCES})
add_dependencies(nsmb_recompiled_banks nsmb_generate_banks)
ndsrecomp_limit_generated_compiles(nsmb_recompiled_banks)
ndsrecomp_limit_link(nsmb_recompiled_banks)

set_source_files_properties(${NSMB_ARM9_SOURCES} PROPERTIES COMPILE_DEFINITIONS "NDS_STATIC_CPU=0")
set_source_files_properties(${NSMB_ARM7_SOURCES} PROPERTIES COMPILE_DEFINITIONS "NDS_STATIC_CPU=1")

target_include_directories(nsmb_recompiled_banks PRIVATE
    "${NSMB_RECOMP_DIR}"
    "${NDSRECOMP_ROOT}/recompiler/armv4t"
    ${NDS_ARM_RECOMP_INCLUDE_DIRS})

if(NOT MSVC)
    target_compile_options(nsmb_recompiled_banks PRIVATE -w -O2 -g0)
endif()

# Native recomp-ui launcher
option(NSMB_BUILD_LAUNCHER "Build the NSMB recomp-ui launcher" ON)
if(NSMB_BUILD_LAUNCHER AND (WIN32 OR MINGW OR MSYS))
    set(NSMB_RECOMP_UI_ROOT
        "${CMAKE_CURRENT_SOURCE_DIR}/third_party/recomp-ui"
        CACHE PATH "Path to recomp-ui")
    find_package(SDL3 CONFIG REQUIRED)
    add_executable(nsmb_launcher src/launcher_main.cpp)
    set_target_properties(nsmb_launcher PROPERTIES
        OUTPUT_NAME "New Super Mario Bros DS Decomp")
    target_link_libraries(nsmb_launcher PRIVATE SDL3::SDL3)
    set(RECOMP_UI_ROOT "${NSMB_RECOMP_UI_ROOT}")
    set(SNESRECOMP_SDL_BACKEND "SDL3" CACHE STRING "SDL backend" FORCE)
    set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "" FORCE)
    include("${NSMB_RECOMP_UI_ROOT}/recomp_ui.cmake")
    recomp_target_launcher_ui(nsmb_launcher
        CONSOLE nds
        BOXART "${CMAKE_CURRENT_SOURCE_DIR}/assets/boxart_nsmb_us.tga")
endif()
