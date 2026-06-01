cmake_minimum_required(VERSION 3.21)

# ---- Job parallelism ----
include(ProcessorCount)
ProcessorCount(N)
if(N EQUAL 0)
    set(N 4)
endif()

# ---- Cache variables needed by toolchain (MUST be before project()) ----
set(STAGE_DIR "${CMAKE_CURRENT_BINARY_DIR}/stage")
set(STAGE_DIR "${STAGE_DIR}" CACHE PATH "Unified install prefix for all dependencies")

set(LINK_TYPE "shared" CACHE STRING "Link type: static, shared")
set_property(CACHE LINK_TYPE PROPERTY STRINGS "static" "shared")

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded" CACHE STRING "MSVC runtime library")
set_property(CACHE CMAKE_MSVC_RUNTIME_LIBRARY PROPERTY STRINGS
    "MultiThreaded" "MultiThreadedDLL" "MultiThreadedDebug" "MultiThreadedDebugDLL")
if(CMAKE_MSVC_RUNTIME_LIBRARY MATCHES "DLL")
    set(MSVC_CRT_FLAG "/MD")
else()
    set(MSVC_CRT_FLAG "/MT")
endif()
if(CMAKE_MSVC_RUNTIME_LIBRARY MATCHES "Debug")
    set(MSVC_CRT_FLAG "${MSVC_CRT_FLAG}d")
endif()

# ---- Unified toolchain (CMake + ENV for both CMake and autotools deps) ----
set(CMAKE_TOOLCHAIN_FILE
    "${CMAKE_CURRENT_LIST_DIR}/cmake/ToolchainMSVC.cmake"
    CACHE FILEPATH "Unified MSVC build environment"
)

project(FFmpegMSVCBuild
    VERSION 2.0.0
    DESCRIPTION "FFmpeg MSVC build using CMake ExternalProject"
    LANGUAGES NONE
)

if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

# ---- MSYS2 Detection ----
include("${CMAKE_CURRENT_LIST_DIR}/cmake/BootstrapMSYS2.cmake")

# ---- Architecture Mapping ----
if(NOT DEFINED CACHE{TARGET_ARCH} AND DEFINED ENV{VSCMD_ARG_TGT_ARCH})
    if($ENV{VSCMD_ARG_TGT_ARCH} STREQUAL "x64")
        set(TARGET_ARCH "amd64")
    elseif($ENV{VSCMD_ARG_TGT_ARCH} STREQUAL "x86")
        set(TARGET_ARCH "x86")
    elseif($ENV{VSCMD_ARG_TGT_ARCH} MATCHES "^arm")
        set(TARGET_ARCH "$ENV{VSCMD_ARG_TGT_ARCH}")
    endif()
endif()
set(TARGET_ARCH "${TARGET_ARCH}" CACHE STRING "Target arch: x86, amd64, arm, arm64")
set_property(CACHE TARGET_ARCH PROPERTY STRINGS "x86" "amd64" "arm" "arm64")

if(TARGET_ARCH STREQUAL "x86")
    set(ARCH_NAME   "x86"                  CACHE INTERNAL "")
    set(HOST_TRIPLE "i686-w64-mingw32"     CACHE STRING "GNU host triple")
elseif(TARGET_ARCH STREQUAL "amd64")
    set(ARCH_NAME   "x86_64"               CACHE INTERNAL "")
    set(HOST_TRIPLE "x86_64-w64-mingw32"   CACHE STRING "GNU host triple")
elseif(TARGET_ARCH STREQUAL "arm")
    set(ARCH_NAME   "arm"                  CACHE INTERNAL "")
    set(HOST_TRIPLE "armv7-w64-mingw32"    CACHE STRING "GNU host triple")
elseif(TARGET_ARCH STREQUAL "arm64")
    set(ARCH_NAME   "aarch64"              CACHE INTERNAL "")
    set(HOST_TRIPLE "aarch64-w64-mingw32"  CACHE STRING "GNU host triple")
else()
    message(FATAL_ERROR "Unknown TARGET_ARCH: ${TARGET_ARCH}")
endif()

# ---- Meson cross-file CPU mapping ----
if(TARGET_ARCH STREQUAL "x86")
    set(MESON_CPU_FAMILY "x86")
    set(MESON_CPU "i686")
elseif(TARGET_ARCH STREQUAL "amd64")
    set(MESON_CPU_FAMILY "x86_64")
    set(MESON_CPU "x86_64")
elseif(TARGET_ARCH STREQUAL "arm")
    set(MESON_CPU_FAMILY "arm")
    set(MESON_CPU "armv7")
elseif(TARGET_ARCH STREQUAL "arm64")
    set(MESON_CPU_FAMILY "aarch64")
    set(MESON_CPU "aarch64")
endif()

configure_file(
    "${CMAKE_CURRENT_LIST_DIR}/cmake/MesonCrossFiles/msvc-cross.ini.in"
    "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
    @ONLY
)
configure_file(
    "${CMAKE_CURRENT_LIST_DIR}/cmake/MesonCrossFiles/gcc-native.ini.in"
    "${CMAKE_CURRENT_BINARY_DIR}/gcc-native.ini"
    @ONLY
)

# ---- User-facing build options ----
set(FFMPEG_VERSION       "7.1"   CACHE STRING "FFmpeg version")
set(DEP_VERSION_OVERRIDE ""      CACHE STRING "Override dep versions: name=ver;name=ver")
set(LICENSE              "gpl"   CACHE STRING "License: gpl, lgpl")
set_property(CACHE LICENSE PROPERTY STRINGS "gpl" "lgpl")

# ---- Tool detection ----
find_package(Git REQUIRED)

message(STATUS "=== FFmpeg MSVC ExternalProject Build ===")
message(STATUS "  TARGET_ARCH       = ${TARGET_ARCH} (${ARCH_NAME})")
message(STATUS "  LINK_TYPE         = ${LINK_TYPE}")
message(STATUS "  CRT               = ${CMAKE_MSVC_RUNTIME_LIBRARY} (${MSVC_CRT_FLAG})")
message(STATUS "  HOST_TRIPLE       = ${HOST_TRIPLE}")
message(STATUS "  STAGE_DIR         = ${STAGE_DIR}")
message(STATUS "  MSYS2_ROOT        = ${MSYS2_ROOT}")
message(STATUS "  MSYS2_SHELL       = ${MSYS2_SHELL}")
message(STATUS "  FFMPEG_VERSION    = ${FFMPEG_VERSION}")
message(STATUS "  LICENSE           = ${LICENSE}")
message(STATUS "Git:               ${GIT_EXECUTABLE}")

# ---- ExternalProject ----
include(ExternalProject)

# =======================================================
# Phase 1: Register all packages and versions
# =======================================================
message(STATUS "--- Phase 1: Registering packages ---")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/DepPackage.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/PkgConfigHelper.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Zlib.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_X264.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Fribidi.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Libass.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Freetype.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Harfbuzz.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Openexr.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Highway.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Brotli.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Lcms2.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Libjxl.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_X265.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Libvpx.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Dav1d.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Opus.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Soxr.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_SDL2.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Libwebp.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_NvcodecHeaders.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Srt.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Libxml2.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Svtav1.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Aom.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Lame.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Pthreads.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Vmaf.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Openjpeg.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Snappy.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Vvenc.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Liblc3.cmake")
# include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Codec2.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Gsm.cmake")
# include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Speex.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Twolame.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Sndfile.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Bs2b.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_Gme.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/External_FFmpeg.cmake")

# =======================================================
# Phase 2: Load version families
# =======================================================
message(STATUS "--- Phase 2: Loading version families ---")
file(GLOB _family_files "${CMAKE_CURRENT_LIST_DIR}/families/*.cmake")
foreach(_f IN LISTS _family_files)
    include("${_f}")
endforeach()

# =======================================================
# Phase 3: Resolve versions, dependencies, patches
# =======================================================
message(STATUS "--- Phase 3: Resolving dependencies ---")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/DepResolver.cmake")
dep_resolve_all()

# =======================================================
# Phase 4: Build
# =======================================================
message(STATUS "--- Phase 4: Building ---")
include("${CMAKE_CURRENT_LIST_DIR}/cmake/BuildAssembly.cmake")

# =======================================================
# Phase 5: Release Note
# =======================================================
include("${CMAKE_CURRENT_LIST_DIR}/cmake/ReleaseNote.cmake")

# ---- Top-level Convenience Target ----
add_custom_target(all_deps ALL
    DEPENDS ffmpeg_target
    COMMENT "All dependencies and FFmpeg built"
)
