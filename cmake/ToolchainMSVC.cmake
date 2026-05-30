# Unified MSVC toolchain + build environment
#
# Usage:
#   set(CMAKE_TOOLCHAIN_FILE "cmake/ToolchainMSVC.cmake" CACHE FILEPATH "")
#   project(...)   # ← loads this file
#
# After loading:
#   CMake deps:   CMAKE_C_COMPILER=cl, CMAKE_RC_COMPILER=rc, etc.
#   Autotools deps: ENV{CC}=cl, ENV{CFLAGS}=/MD, etc. (inherited by ExternalProject)

set(CMAKE_SYSTEM_NAME       Windows)
set(CMAKE_SYSTEM_PROCESSOR  AMD64)


# ---- CMake compiler tools (MSVC) ----
set(CMAKE_C_COMPILER    cl   CACHE STRING "" FORCE)
set(CMAKE_CXX_COMPILER  cl   CACHE STRING "" FORCE)
set(CMAKE_RC_COMPILER   rc   CACHE STRING "" FORCE)
set(CMAKE_AR            lib  CACHE STRING "" FORCE)
set(CMAKE_LINKER        link CACHE STRING "" FORCE)
set(CMAKE_MT            mt   CACHE STRING "" FORCE)

execute_process(
    COMMAND cygpath -u "${STAGE_DIR}"
    OUTPUT_VARIABLE STAGE_DIR_UNIX
    OUTPUT_STRIP_TRAILING_WHITESPACE
)

# ---- Environment variables (inherited by autotools ExternalProject deps) ----

 
set(ENV{CC}              ${CMAKE_C_COMPILER})
set(ENV{CXX}             ${CMAKE_CXX_COMPILER})
set(ENV{RC}              ${CMAKE_RC_COMPILER})
set(ENV{LINKER}          ${CMAKE_LINKER})
set(ENV{MT}              ${CMAKE_MT})
set(ENV{AR}              ${CMAKE_AR})
set(ENV{CFLAGS}         "${MSVC_CRT_FLAG}")
set(ENV{PKG_CONFIG_PATH} "${STAGE_DIR_UNIX}/lib/pkgconfig:${STAGE_DIR_UNIX}/share/pkgconfig")
set(ENV{MSYSTEM}         MSYS)
set(ENV{MSYS2_PATH_TYPE} inherit)
set(ENV{MSYS2_ARG_CONV_EXCL} "*")
set(ENV{VSLANG} 1033)
set(ENV{LC_ALL} C)

set(SHELL_ENV
    "CC=${CMAKE_C_COMPILER}"
    "CXX=${CMAKE_CXX_COMPILER}"
    "RC=${CMAKE_RC_COMPILER}"
    "LINKER=${CMAKE_LINKER}"
    "MT=${CMAKE_MT}"
    "AR=${CMAKE_AR}"
    "CFLAGS=${MSVC_CRT_FLAG}"
    "PKG_CONFIG_PATH=${STAGE_DIR_UNIX}/lib/pkgconfig:${STAGE_DIR_UNIX}/share/pkgconfig"
    "MSYSTEM=MSYS"
    "MSYS2_PATH_TYPE=inherit"
    "VSLANG=1033"
    "LC_ALL=C"
)
