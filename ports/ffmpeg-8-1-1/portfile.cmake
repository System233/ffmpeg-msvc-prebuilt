set(FFMPEG_VERSION "8.1.1")
set(FFMPEG_SHA512 e858e92e5eb08d562302cde371af55917df6e1fe53994e18462a3c929a40ede1828c2bd53c2a7d65a2cfd791782ead3cd94efb2def904f49cb5dd8ab5cd4256f)
set(FFMPEG_PORT_REVISION 1)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg")
set(FFMPEG_BUILDER_DIR "${CURRENT_HOST_INSTALLED_DIR}/share/ffmpeg-builder")
set(FFMPEG_PATCHES_DIR "${CMAKE_CURRENT_LIST_DIR}/../../patches/8.x")
set(FFMPEG_NEED_BIN2C ON)
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations --enable-debug")
set(FFMPEG_PATCHES
    0002-fix-msvc-link-8.1.patch
    0003-fix-windowsinclude.patch
    0004-dependencies-8.1.patch
    0005-fix-nasm-8.1.patch
    0007-fix-lib-naming-8.1.patch
    0013-define-WINVER-8.1.patch
    0024-fix-osx-host-c11-8.1.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium.patch
    0045-use-prebuilt-bin2c-8.1.patch
    0046-fix-msvc-detection-8.1.patch
    0047-fix-msvc-utf8.patch
    0048-backport-23039.patch
    0050-lensfun-0.3.4-compat-8.x.patch
    0051-lensfun-configure-fix-8.x.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${FFMPEG_BUILDER_DIR}/ffmpeg-portfile.cmake")
