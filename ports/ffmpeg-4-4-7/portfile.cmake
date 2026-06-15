set(FFMPEG_VERSION "4.4.7")
set(FFMPEG_SHA512 ccd79de9a570d6168ff2ee28061c3637a39963512a3e44b438a4a14a92865d5e91ed7d2f98a360826ac389e96d0ff3eb9f27b88164e6846d35efa0a817c0ff7b)
set(FFMPEG_PORT_REVISION 1)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg")
set(FFMPEG_BUILDER_DIR "${CURRENT_INSTALLED_DIR}/share/ffmpeg-builder")
set(FFMPEG_PATCHES_DIR "${CMAKE_CURRENT_LIST_DIR}/../../patches/4.x")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect --enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--debug --disable-optimizations")
set(FFMPEG_PATCHES
    0001-create-lib-libraries.patch
    0003-fix-windowsinclude.patch
    0004-fix-debug-build.patch
    0006-fix-StaticFeatures.patch
    0007-fix-lib-naming.patch
    0009-Fix-fdk-detection.patch
    0010-Fix-x264-detection.patch
    0011-Fix-x265-detection.patch
    0012-Fix-ssl-110-detection-4.4.7.patch
    0013-define-WINVER.patch
    0014-avfilter-dependency-fix.patch
    0015-Fix-xml2-detection.patch
    0017-Patch-for-ticket-9019-CUDA-Compile-Broken-Using-MSVC.patch
    0018-libaom-Dont-use-aom_codec_av1_dx_algo.patch
    0019-libx264-Do-not-explicitly-set-X264_API_IMPORTS.patch
    0020-fix-aarch64-libswscale-4.4.7.patch
    0022-fix-m1-hardware-decode-nal-bits.patch
    0023-fix-qsv-init.patch
    0050-lensfun-0.3.4-compat-4.4.7.patch
    0052-svtav1-3.x-compat-4.4.7.patch
    0001-fix-iconv-link.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${FFMPEG_BUILDER_DIR}/ffmpeg-portfile.cmake")
