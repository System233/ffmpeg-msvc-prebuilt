set(FFMPEG_VERSION "7.1.1")
set(FFMPEG_SHA512 6b9a5ee501be41d6abc7579a106263b31f787321cbc45dedee97abf992bf8236cdb2394571dd256a74154f4a20018d429ae7e7f0409611ddc4d6f529d924d175)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/7.1")
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
    0043-fix-miss-head.patch
    0044-fix-vulkan-debug-callback-abi.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
