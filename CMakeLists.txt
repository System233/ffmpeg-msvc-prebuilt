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

if(LINK_TYPE STREQUAL "static")
    set(MSVC_CRT_FLAG "-MT" CACHE STRING "MSVC CRT link flag")
    set(MSVC_CRT_LIBRARY "MultiThreaded" CACHE INTERNAL "")
else()
    set(MSVC_CRT_FLAG "-MD" CACHE STRING "MSVC CRT link flag")
    set(MSVC_CRT_LIBRARY "MultiThreadedDLL" CACHE INTERNAL "")
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
set(TARGET_ARCH "amd64" CACHE STRING "Target arch: x86, amd64, arm, arm64")
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

# ---- User-facing build options ----
set(FFMPEG_VERSION       "7.1"   CACHE STRING "FFmpeg version")
set(DEP_VERSION_OVERRIDE ""      CACHE STRING "Override dep versions: name=ver;name=ver")
set(LICENSE              "gpl"   CACHE STRING "License: gpl, lgpl")
set_property(CACHE LICENSE PROPERTY STRINGS "gpl" "lgpl")

# ---- Tool detection ----
find_package(Git REQUIRED)

message(STATUS "=== FFmpeg MSVC ExternalProject Build ===")
message(STATUS "  TARGET_ARCH       = ${TARGET_ARCH} (${ARCH_NAME})")
message(STATUS "  LINK_TYPE         = ${LINK_TYPE} (CFLAGS=${MSVC_CRT_FLAG})")
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
