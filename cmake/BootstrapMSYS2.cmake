# BootstrapMSYS2.cmake — locate MSYS2 and set up environment variables

set(MSYS2_ROOT "D:/msys64" CACHE PATH "MSYS2 installation root directory")

# Find MSYS2 bash
find_program(MSYS2_BASH
    NAMES bash
    HINTS
        "${MSYS2_ROOT}/usr/bin"
        "C:/msys64/usr/bin"
        "D:/msys64/usr/bin"
    NO_DEFAULT_PATH
)

if(NOT MSYS2_BASH)
    message(FATAL_ERROR "MSYS2 bash not found. Install MSYS2 to D:/msys64 or set MSYS2_ROOT")
endif()

get_filename_component(MSYS2_USR "${MSYS2_BASH}" DIRECTORY)
set(MSYS2_SHELL "${MSYS2_USR}/bash.exe" CACHE FILEPATH "Path to MSYS2 bash executable")

# Set environment for ExternalProject subprocesses
set(ENV{MSYSTEM}        "MSYS")
set(ENV{MSYS2_PATH_TYPE} "inherit")

message(STATUS "MSYS2 found: ${MSYS2_ROOT}")
message(STATUS "MSYS2 bash:  ${MSYS2_SHELL}")
