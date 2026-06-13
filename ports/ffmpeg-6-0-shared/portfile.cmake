set(FFMPEG_VERSION "6.0")
set(FFMPEG_SHA512 da1b836c8f51cf69f95db750d5da5191a71d534fa7b0f019d6d6454f8dd6db5598789576b4fe5ad983dcd0197b9a7e8f9d43f10707b6d40ac31425da23da35b2)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg/6.0")
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
    0023-fix-qsv-init.patch
    0024-fix-gcc13-binutils.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")
