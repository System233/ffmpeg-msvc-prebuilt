set(FFMPEG_VERSION "8.0.1")
set(FFMPEG_SHA512 f31769a7ed52865165e7db4a03e9378b3376012b7aaf0bbc022aa76c3e999e71c3927e6eb8639d8681e04e33362dd73eafa9e7c62a3c71599ff78da09f5cee0a)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/8.0")
set(FFMPEG_BASE_OPTIONS "")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations --enable-debug")
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
    0042-fix-arm64-linux.patch
    0044-fix-vulkan-debug-callback-abi.patch
    0045-use-prebuilt-bin2c.patch
    0046-fix-msvc-detection.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
