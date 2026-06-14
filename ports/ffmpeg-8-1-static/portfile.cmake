set(FFMPEG_VERSION "8.1")
set(FFMPEG_SHA512 1dee3967057619dd7f2f78c63de85bb97af16c974bd9225c2336d42c7c8765c04f77490aac36af2daf953bc52c7faa37750a09265e133708f6a1709028573834)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/8.1")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations --enable-debug")
set(FFMPEG_PATCHES
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-dependencies.patch
    0005-fix-nasm.patch
    0007-fix-lib-naming.patch
    0013-define-WINVER.patch
    0024-fix-osx-host-c11.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium.patch
    0045-use-prebuilt-bin2c.patch
    0046-fix-msvc-detection.patch
    0047-fix-msvc-utf8.patch
    0048-backport-23039.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
