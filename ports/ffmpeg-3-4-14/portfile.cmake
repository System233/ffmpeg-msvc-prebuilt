set(FFMPEG_VERSION "3.4.14")
set(FFMPEG_SHA512 e249fa1eb9e8c3bef813da6da190c55a6b23279a5f268416e33e598e5ca06ed7b1606b91a68cf3914f22d16d88ff880423f3dbcd74d1528edaa15af30d259224)
set(FFMPEG_PORT_REVISION 1)
set(FFMPEG_SHARED_DIR "${CMAKE_CURRENT_LIST_DIR}/../../scripts/ffmpeg")
set(FFMPEG_BUILDER_DIR "${CURRENT_HOST_INSTALLED_DIR}/share/ffmpeg-builder")
set(FFMPEG_PATCHES_DIR "${CMAKE_CURRENT_LIST_DIR}/../../patches/3.x")
set(FFMPEG_BASE_OPTIONS "--enable-pic --disable-doc --enable-runtime-cpudetect --disable-autodetect --enable-debug")
set(FFMPEG_OPTIONS_DEBUG "--disable-optimizations")
set(FFMPEG_PATCHES
    configure_opencv-3.4.14.patch
    create-lib-libraries.patch
    detect-openssl-3.4.14.patch
    windres-configure-fix-3.4.14.patch
    0006-fix-libmp3lame-static.patch
    0007-fix-msvc-lib-naming.patch
    0008-fix-sdl2-version.patch
    0009-fix-openjpeg-lib-name.patch
    0010-fix-opencl.patch
    0011-fix-opengl-quoting.patch
    0012-fix-opengl-unistd.patch
    0013-fix-x264-imports.patch
)
set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")
include("${FFMPEG_BUILDER_DIR}/ffmpeg-portfile.cmake")
