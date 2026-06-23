cmake_minimum_required(VERSION 3.21)
project(ffmpeg-tester C)

find_package(FFmpeg MODULE REQUIRED)

set(src_dir "${CMAKE_CURRENT_BINARY_DIR}/src")
file(MAKE_DIRECTORY "${src_dir}")

# Macro: per-lib test (generates demand / full / legacy targets)
macro(add_ffmpeg_test name header func demand_target)
    set(TEST_NAME "check-${name}")
    set(INCLUDE_HEADER "${header}")
    set(API_FUNC "${func}")
    configure_file(check_lib.c.in "${src_dir}/check_${name}.c" @ONLY)

    add_executable(check-${name} "${src_dir}/check_${name}.c")
    target_link_libraries(check-${name} PRIVATE ${demand_target})

    add_executable(check-full-${name} "${src_dir}/check_${name}.c")
    target_link_libraries(check-full-${name} PRIVATE FFmpeg::FFmpeg)

    add_executable(check-legacy-${name} "${src_dir}/check_${name}.c")
    target_include_directories(check-legacy-${name} PRIVATE ${FFMPEG_INCLUDE_DIRS})
    target_link_libraries(check-legacy-${name} PRIVATE ${FFMPEG_LIBRARIES})
endmacro()

# Macro: transitive dep test (generates transitive / full-transitive / legacy-transitive)
macro(add_ffmpeg_transitive_test name header func demand_target)
    set(TEST_NAME "check-transitive-${name}")
    set(INCLUDE_HEADER "${header}")
    set(API_FUNC "${func}")
    configure_file(check_transitive.c.in "${src_dir}/check_transitive_${name}.c" @ONLY)

    add_executable(check-transitive-${name} "${src_dir}/check_transitive_${name}.c")
    target_link_libraries(check-transitive-${name} PRIVATE ${demand_target})

    add_executable(check-full-transitive-${name} "${src_dir}/check_transitive_${name}.c")
    target_link_libraries(check-full-transitive-${name} PRIVATE FFmpeg::FFmpeg)

    add_executable(check-legacy-transitive-${name} "${src_dir}/check_transitive_${name}.c")
    target_include_directories(check-legacy-transitive-${name} PRIVATE ${FFMPEG_INCLUDE_DIRS})
    target_link_libraries(check-legacy-transitive-${name} PRIVATE ${FFMPEG_LIBRARIES})
endmacro()

# == Per-library compilation + link tests ==
add_ffmpeg_test(avutil     libavutil/avutil.h     avutil_version     FFmpeg::avutil)
add_ffmpeg_test(avcodec    libavcodec/avcodec.h   avcodec_version    FFmpeg::avcodec)
add_ffmpeg_test(avformat   libavformat/avformat.h avformat_version   FFmpeg::avformat)
add_ffmpeg_test(avdevice   libavdevice/avdevice.h avdevice_version   FFmpeg::avdevice)
add_ffmpeg_test(avfilter   libavfilter/avfilter.h avfilter_version   FFmpeg::avfilter)
add_ffmpeg_test(swresample libswresample/swresample.h swresample_version FFmpeg::swresample)
add_ffmpeg_test(swscale    libswscale/swscale.h   swscale_version    FFmpeg::swscale)
if(TARGET FFmpeg::postproc)
    add_ffmpeg_test(postproc libpostproc/postprocess.h postproc_version FFmpeg::postproc)
endif()

# == Transitive dependency tests (only verify avutil propagation) ==
add_ffmpeg_transitive_test(avcodec    libavcodec/avcodec.h   avcodec_version    FFmpeg::avcodec)
add_ffmpeg_transitive_test(avformat   libavformat/avformat.h avformat_version   FFmpeg::avformat)
add_ffmpeg_transitive_test(avdevice   libavdevice/avdevice.h avdevice_version   FFmpeg::avdevice)
add_ffmpeg_transitive_test(avfilter   libavfilter/avfilter.h avfilter_version   FFmpeg::avfilter)
add_ffmpeg_transitive_test(swresample libswresample/swresample.h swresample_version FFmpeg::swresample)
add_ffmpeg_transitive_test(swscale    libswscale/swscale.h   swscale_version    FFmpeg::swscale)
