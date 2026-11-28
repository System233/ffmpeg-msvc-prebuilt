cmake_minimum_required(VERSION 3.21)
project(ffmeta C)

# New SDK: cmake -B build -DCMAKE_PREFIX_PATH=<extracted_prefix>
# Older SDK: cmake -B build -DFFMPEG_ROOT=<extracted_prefix>
# Both discovery modes expose the same imported targets and legacy variables.
# cmake --build build --config Debug
# cmake --install build --prefix dist --config Debug

if(POLICY CMP0144)
    cmake_policy(SET CMP0144 NEW)
endif()

set(FFMPEG_ROOT "" CACHE PATH "Path to FFmpeg installation root directory")
set(FFMPEG_LINK_MODE "full" CACHE STRING "Linking method: full (FFmpeg::FFmpeg umbrella target), demand (FFmpeg::avformat etc.), legacy (\${FFMPEG_LIBRARIES})")
set_property(CACHE FFMPEG_LINK_MODE PROPERTY STRINGS full demand legacy)

if(FFMPEG_ROOT)
    # Keep the explicit legacy invocation compatible with previously released SDKs.
    if(NOT IS_ABSOLUTE "${FFMPEG_ROOT}")
        message(FATAL_ERROR "FFMPEG_ROOT must be an absolute path: ${FFMPEG_ROOT}")
    endif()
    list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")
    find_package(FFmpeg 5.0 MODULE REQUIRED)
else()
    find_package(FFmpeg 5.0 CONFIG REQUIRED)
endif()

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




if(WIN32 AND NOT FFMPEG_LINK_MODE STREQUAL "legacy")
# --- Copy FFmpeg DLLs to build output directory for direct execution ---
add_custom_command(TARGET ffmeta POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_RUNTIME_DLLS:ffmeta>" "$<TARGET_FILE_DIR:ffmeta>"
    COMMAND_EXPAND_LISTS
)
endif()


install(TARGETS ffmeta RUNTIME DESTINATION bin)
install(FILES $<TARGET_RUNTIME_DLLS:ffmeta> DESTINATION bin)


