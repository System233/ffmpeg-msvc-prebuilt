set(FFMPEG_VERSION "7.1.2")
set(FFMPEG_SHA512 8411c45f71d2d61184b11e2a786137044a80d9b979a7e2e8513efc5e716b3360bff4533a13875dd4bca492b97b97f0384f7fb4f3d796802e81981b0857d18a2b)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/7.1")
set(FFMPEG_BASE_OPTIONS "--enable-debug")
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
    0043-fix-miss-head.patch
    0044-fix-vulkan-debug-callback-abi.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
