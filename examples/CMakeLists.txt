cmake_minimum_required(VERSION 3.21)
project(ffmeta C)

# ---------------------------------------------------------------------------
# How this works:
#
# 1. The user passes FFMPEG_ROOT pointing to the extracted FFmpeg archive.
# 2. We add ${FFMPEG_ROOT}/share/ffmpeg to CMAKE_MODULE_PATH so CMake can
#    locate FindFFmpeg.cmake inside the archive.
# 3. find_package(FFmpeg MODULE) loads FindFFmpeg.cmake, which:
#    - Searches for FFmpeg headers and libraries under FFMPEG_ROOT
#    - Caches the results for fast reconfiguration
#    - Creates imported targets (FFmpeg::FFmpeg, FFmpeg::avformat, etc.)
#      plus FFMPEG:: aliases for backward compatibility
#    - Provides legacy variables (FFMPEG_LIBRARIES, FFMPEG_INCLUDE_DIRS, …)
# 4. target_link_libraries consumes the targets; CMake handles include dirs,
#    import libraries, and per-config Debug/Release switching.
# 5. On Windows shared builds, IMPORTED_LOCATION points to the actual DLL;
#    $<TARGET_RUNTIME_DLLS:tgt> resolves paths for POST_BUILD copy and
#    install(FILES ...).
# ---------------------------------------------------------------------------
# Usage:
#   cmake -B build -DFFMPEG_ROOT=<absolute_path_to_ffmpeg_prefix>
#   cmake --build build --config Debug
#   cmake --install build --prefix dist --config Debug

if(POLICY CMP0144)
    cmake_policy(SET CMP0144 NEW)
endif()

set(FFMPEG_ROOT "" CACHE PATH "Path to FFmpeg installation root directory")
set(FFMPEG_LINK_MODE "full" CACHE STRING "Linking method: full (FFmpeg::FFmpeg umbrella target), demand (FFmpeg::avformat etc.), legacy (\${FFMPEG_LIBRARIES})")
set_property(CACHE FFMPEG_LINK_MODE PROPERTY STRINGS full demand legacy)

if(NOT IS_ABSOLUTE "${FFMPEG_ROOT}")
    message(FATAL_ERROR "FFMPEG_ROOT must be an absolute path: ${FFMPEG_ROOT}")
endif()

# Make FindFFmpeg.cmake discoverable — this is the key step
list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")

find_package(FFmpeg 5.0 MODULE REQUIRED)

add_executable(ffmeta main.c)

if(FFMPEG_LINK_MODE STREQUAL "full")
    # --- Method A: umbrella target FFmpeg::FFmpeg (recommended) ----
    target_link_libraries(ffmeta PRIVATE FFmpeg::FFmpeg)
elseif(FFMPEG_LINK_MODE STREQUAL "demand")
    # --- Method B: per-module targets --------------------------------
    target_link_libraries(ffmeta PRIVATE
        FFmpeg::avformat
        FFmpeg::avcodec
        FFmpeg::avutil)
elseif(FFMPEG_LINK_MODE STREQUAL "legacy")
    # --- Method C: legacy variables ----------------------------------
    target_include_directories(ffmeta PRIVATE ${FFMPEG_INCLUDE_DIRS})
    target_link_libraries(ffmeta PRIVATE ${FFMPEG_LIBRARIES})
else()
    message(FATAL_ERROR "Invalid FFMPEG_LINK_MODE '${FFMPEG_LINK_MODE}' — expected: full | demand | legacy")
endif()




if(NOT FFMPEG_LINK_MODE STREQUAL "legacy" AND "$<TARGET_RUNTIME_DLLS:ffmeta>")
# --- Copy FFmpeg DLLs to build output directory for direct execution ---
add_custom_command(TARGET ffmeta POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_RUNTIME_DLLS:ffmeta>" "$<TARGET_FILE_DIR:ffmeta>"
    COMMAND_EXPAND_LISTS
)
endif()


install(TARGETS ffmeta RUNTIME DESTINATION bin)
install(FILES $<TARGET_RUNTIME_DLLS:ffmeta> DESTINATION bin)


