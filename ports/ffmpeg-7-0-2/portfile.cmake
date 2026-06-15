set(FFMPEG_VERSION "7.0.2")
set(FFMPEG_SHA512 3ba02e8b979c80bf61d55f414bdac2c756578bb36498ed7486151755c6ccf8bd8ff2b8c7afa3c5d1acd862ce48314886a86a105613c05e36601984c334f8f6bf)
set(FFMPEG_PORT_REVISION 1)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg")
set(FFMPEG_BUILDER_DIR "${CURRENT_INSTALLED_DIR}/share/ffmpeg-builder")
set(FFMPEG_PATCHES_DIR "${CMAKE_CURRENT_LIST_DIR}/../../patches/7.x")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect --enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations")
set(FFMPEG_PATCHES
    0001-create-lib-libraries-6.1.patch
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-dependencies-7.0.patch
    0005-fix-nasm-7.0.patch
    0007-fix-lib-naming-7.0.patch
    0012-Fix-ssl-110-detection.patch
    0013-define-WINVER.patch
    0020-fix-aarch64-libswscale-6.1.patch
    0024-fix-osx-host-c11.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium.patch
    0041-add-const-for-opengl-definition.patch
    0043-fix-miss-head-7.0.patch
    0050-lensfun-0.3.4-compat-7.x.patch
    0051-lensfun-configure-fix-7.x.patch
    0052-svtav1-3.x-compat-7.x.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${FFMPEG_BUILDER_DIR}/ffmpeg-portfile.cmake")
