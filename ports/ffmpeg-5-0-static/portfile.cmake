set(FFMPEG_VERSION "5.0")
set(FFMPEG_SHA512 TODO)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/5.0")
set(FFMPEG_BASE_OPTIONS "--enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--debug --disable-optimizations")
set(FFMPEG_PATCHES
    0001-create-lib-libraries.patch
    0003-fix-windowsinclude.patch
    0004-fix-debug-build.patch
    0006-fix-StaticFeatures.patch
    0007-fix-lib-naming.patch
    0009-Fix-fdk-detection.patch
    0011-Fix-x265-detection.patch
    0012-Fix-ssl-110-detection.patch
    0013-define-WINVER.patch
    0015-Fix-xml2-detection.patch
    0019-libx264-Do-not-explicitly-set-X264_API_IMPORTS.patch
    0020-fix-aarch64-libswscale.patch
    0022-fix-iconv.patch
    0023-fix-qsv-init.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
