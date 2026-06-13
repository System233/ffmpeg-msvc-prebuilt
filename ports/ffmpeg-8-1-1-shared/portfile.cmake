set(FFMPEG_VERSION "8.1.1")
set(FFMPEG_SHA512 e858e92e5eb08d562302cde371af55917df6e1fe53994e18462a3c929a40ede1828c2bd53c2a7d65a2cfd791782ead3cd94efb2def904f49cb5dd8ab5cd4256f)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/8.1")
set(FFMPEG_BASE_OPTIONS "")
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
