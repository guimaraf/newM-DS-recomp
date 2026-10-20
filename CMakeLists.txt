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
    "${NSMB_INPUT_DIR}/arm7.bin"
    "${NSMB_INPUT_DIR}/arm9.toml"
    "${NSMB_INPUT_DIR}/arm7.toml")

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
    COMMENT "Preparing NSMB DS code images and TOML manifests")
add_custom_target(nsmb_prepare DEPENDS ${NSMB_PREP_OUTPUTS})

set(NSMB_ARM9_SOURCES)
foreach(shard RANGE 0 15)
    if(shard LESS 10)
        set(shard_name "0${shard}")
    else()
        set(shard_name "${shard}")
    endif()
    list(APPEND NSMB_ARM9_SOURCES
        "${NSMB_RECOMP_DIR}/nsmb_arm9_${shard_name}.c")
endforeach()
list(APPEND NSMB_ARM9_SOURCES
    "${NSMB_RECOMP_DIR}/nsmb_arm9_dispatch.c")

set(NSMB_ARM7_SOURCES
    "${NSMB_RECOMP_DIR}/nsmb_arm7_00.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm7_01.c"
    "${NSMB_RECOMP_DIR}/nsmb_arm7_dispatch.c")

set(NSMB_BANK_SOURCES ${NSMB_ARM9_SOURCES} ${NSMB_ARM7_SOURCES})

set(NSMB_ARM9_STAMP "${NSMB_RECOMP_DIR}/nsmb_arm9.stamp")
add_custom_command(
    OUTPUT "${NSMB_ARM9_STAMP}"
    BYPRODUCTS ${NSMB_ARM9_SOURCES}
        "${NSMB_RECOMP_DIR}/nsmb_arm9.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${NSMB_RECOMP_DIR}"
    COMMAND $<TARGET_FILE:nds_recompile>
            --config "${NSMB_INPUT_DIR}/arm9.toml"
            --bin "${NSMB_INPUT_DIR}/arm9.bin"
            --out "${NSMB_RECOMP_DIR}"
            --bank nsmb_arm9
            --shards 16
            --stable-address-shards
            --max-function-bytes 16384
    COMMAND ${CMAKE_COMMAND} -E touch "${NSMB_ARM9_STAMP}"
    DEPENDS nds_recompile ${NSMB_PREP_OUTPUTS}
    COMMENT "Statically recompiling NSMB ARM9 main module")
list(APPEND NSMB_BANK_STAMPS "${NSMB_ARM9_STAMP}")

set(NSMB_ARM7_STAMP "${NSMB_RECOMP_DIR}/nsmb_arm7.stamp")
add_custom_command(
    OUTPUT "${NSMB_ARM7_STAMP}"
    BYPRODUCTS ${NSMB_ARM7_SOURCES}
        "${NSMB_RECOMP_DIR}/nsmb_arm7.h"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${NSMB_RECOMP_DIR}"
    COMMAND $<TARGET_FILE:nds_recompile>
            --config "${NSMB_INPUT_DIR}/arm7.toml"
            --bin "${NSMB_INPUT_DIR}/arm7.bin"
            --out "${NSMB_RECOMP_DIR}"
            --bank nsmb_arm7
            --shards 2
            --max-function-bytes 512
    COMMAND ${CMAKE_COMMAND} -E touch "${NSMB_ARM7_STAMP}"
    DEPENDS nds_recompile ${NSMB_PREP_OUTPUTS}
    COMMENT "Statically recompiling NSMB ARM7 module")
list(APPEND NSMB_BANK_STAMPS "${NSMB_ARM7_STAMP}")

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
    target_compile_options(nsmb_recompiled_banks PRIVATE -w -O0 -g0)
endif()

# Native recomp-ui launcher
option(NSMB_BUILD_LAUNCHER "Build the NSMB recomp-ui launcher" ON)
if(NSMB_BUILD_LAUNCHER AND (WIN32 OR MINGW OR MSYS))
    set(NSMB_RECOMP_UI_ROOT
        "${CMAKE_CURRENT_SOURCE_DIR}/third_party/recomp-ui"
        CACHE PATH "Path to recomp-ui")
    find_package(SDL3 CONFIG REQUIRED)
    add_executable(nsmb_launcher src/launcher_main.cpp)
    target_link_libraries(nsmb_launcher PRIVATE SDL3::SDL3)
    set(RECOMP_UI_ROOT "${NSMB_RECOMP_UI_ROOT}")
    set(SNESRECOMP_SDL_BACKEND "SDL3" CACHE STRING "SDL backend" FORCE)
    set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "" FORCE)
    include("${NSMB_RECOMP_UI_ROOT}/recomp_ui.cmake")
    recomp_target_launcher_ui(nsmb_launcher
        CONSOLE nds
        BOXART "${CMAKE_CURRENT_SOURCE_DIR}/assets/boxart_nsmb_us.tga")
endif()
