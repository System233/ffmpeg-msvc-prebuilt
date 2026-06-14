set(FFMPEG_VERSION "7.0")
set(FFMPEG_SHA512 ac147e52557b71cab0a38c0fee5f710a70d7e99107d1cb881e733c489a6b16f99d2c15e00e359ab48353bd710ead13399ee31840e6c5844a11d042eda71a0aa0)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/7.0")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect --enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations")
set(FFMPEG_PATCHES
    0001-create-lib-libraries.patch
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-dependencies.patch
    0005-fix-nasm.patch
    0007-fix-lib-naming.patch
    0013-define-WINVER.patch
    0020-fix-aarch64-libswscale.patch
    0024-fix-osx-host-c11.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium.patch
    0041-add-const-for-opengl-definition.patch
    0042-fix-arm64-linux.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
