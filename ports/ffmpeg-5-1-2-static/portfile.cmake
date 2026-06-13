set(FFMPEG_VERSION "5.1.2")
set(FFMPEG_SHA512 1b90c38b13149f2de7618ad419adc277afd5e65bbf52b849a7245aec0f92f73189c8547599dba8408b8828a767c1120f132727b57cd6231cd8b81de2471a4b8b)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/5.1")
set(FFMPEG_BASE_OPTIONS "--enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--debug --disable-optimizations")
set(FFMPEG_PATCHES
    0001-create-lib-libraries.patch
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-fix-debug-build.patch
    0005-fix-nasm.patch
    0006-fix-StaticFeatures.patch
    0007-fix-lib-naming.patch
    0009-Fix-fdk-detection.patch
    0011-Fix-x265-detection.patch
    0012-Fix-ssl-110-detection.patch
    0013-define-WINVER.patch
    0015-Fix-xml2-detection.patch
    0020-fix-aarch64-libswscale.patch
    0022-fix-iconv.patch
    0024-fix-gcc13-binutils.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
