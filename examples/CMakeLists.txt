cmake_minimum_required(VERSION 3.20)
project(ffmeta C)

# --- Find FFmpeg -------------------------------------------------
# Usage:
#   1. Direct zip (FFMPEG_ROOT must be absolute):
#        cmake -B build -DFFMPEG_ROOT=C:/path/to/ffmpeg_prefix
#   2. Via vcpkg:
#        cmake -B build -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake
#   3. Place FindFFMPEG.cmake in cmake/ subdirectory:
#        mkdir cmake && cp <prefix>/share/ffmpeg/FindFFMPEG.cmake cmake/
#        cmake -B build

if(FFMPEG_ROOT)
    if(NOT IS_ABSOLUTE "${FFMPEG_ROOT}")
        message(FATAL_ERROR "FFMPEG_ROOT must be an absolute path: ${FFMPEG_ROOT}")
    endif()
    list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
endif()
find_package(FFMPEG MODULE REQUIRED)

add_executable(ffmeta main.c)

# --- Method A: umbrella target FFMPEG::ffmpeg (recommended) ----
target_link_libraries(ffmeta PRIVATE FFMPEG::ffmpeg)

# --- Method B: per-module targets --------------------------------
# target_link_libraries(ffmeta PRIVATE
#     FFMPEG::avformat
#     FFMPEG::avcodec
#     FFMPEG::avutil)

# --- Method C: legacy variables ----------------------------------
# target_include_directories(ffmeta PRIVATE ${FFMPEG_INCLUDE_DIRS})
# target_link_libraries(ffmeta PRIVATE ${FFMPEG_LIBRARIES})

install(TARGETS ffmeta RUNTIME DESTINATION bin)
