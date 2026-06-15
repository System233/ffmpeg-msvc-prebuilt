set(FFMPEG_VERSION "6.1.1")
set(FFMPEG_SHA512 a84209fe36a2a0262ebc34b727e7600b12d4739991a95599d7b4df533791b12e2e43586ccc6ff26aab2f935a3049866204e322ec0c5e49e378fc175ded34e183)
set(FFMPEG_PORT_REVISION 1)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg")
set(FFMPEG_BUILDER_DIR "${CURRENT_INSTALLED_DIR}/share/ffmpeg-builder")
set(FFMPEG_PATCHES_DIR "${CMAKE_CURRENT_LIST_DIR}/../../patches/6.x")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect --enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations")
set(FFMPEG_PATCHES
    0001-create-lib-libraries-6.1.patch
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-dependencies-6.1.patch
    0005-fix-nasm-6.0.patch
    0007-fix-lib-naming-6.1.patch
    0012-Fix-ssl-110-detection.patch
    0013-define-WINVER.patch
    0020-fix-aarch64-libswscale-6.1.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium-6.1.patch
    0041-add-const-for-opengl-definition.patch
    0042-fix-arm64-linux.patch
    0050-lensfun-0.3.4-compat-6.x.patch
    0052-svtav1-3.x-compat-6.x.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${FFMPEG_BUILDER_DIR}/ffmpeg-portfile.cmake")
