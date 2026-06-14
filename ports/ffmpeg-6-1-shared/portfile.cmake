set(FFMPEG_VERSION "6.1")
set(FFMPEG_SHA512 abb9207364553248278f8e23e3d565da51ecb0ae9b20edda41624b314541bc3f53a8d6aac7fa5455168d2323d5d70d5a8acbe059f33423fbc2563e1a6cd0348b)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/6.1")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect --enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations")
set(FFMPEG_PATCHES
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-dependencies.patch
    0005-fix-nasm.patch
    0007-fix-lib-naming.patch
    0013-define-WINVER.patch
    0024-fix-osx-host-c11.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium.patch
    0042-fix-arm64-linux.patch
    0043-fix-miss-head.patch
    0044-fix-vulkan-debug-callback-abi.patch
    0045-use-prebuilt-bin2c.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
