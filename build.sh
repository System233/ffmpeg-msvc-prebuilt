#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

HELP_MSG="Usage: build.sh <x86,amd64,arm,arm64> [static,shared] [gpl,lgpl] ...FF_ARGS"
set -e
source ./env.sh

if [ -z $BUILD_ARCH ]; then
    echo "$HELP_MSG" >&2
    exit 1
fi

shift 3 || true
FF_ARGS=$@

for dep in libharfbuzz libfreetype sdl libjxl libvpx; do
    if grep -q "enable-${dep}" FFmpeg/configure; then
        export ENABLE_${dep^^}=1
        FF_ARGS="$FF_ARGS --enable-$dep"
    fi
done

echo BUILD_ARCH=$BUILD_ARCH
echo BUILD_TYPE=$BUILD_TYPE
echo BUILD_LICENSE=$BUILD_LICENSE
echo FF_ARGS=$FF_ARGS

apply-patch() {
    GIT_CMD="git -C $1 apply ../patches/$2 --ignore-whitespace"
    if ! $GIT_CMD -R --check; then
        $GIT_CMD --ignore-whitespace
    else
        echo Skip $2 for $1
    fi
}

apply-patch zlib zlib.patch
apply-patch FFmpeg ffmpeg.patch
apply-patch harfbuzz harfbuzz.patch

# --enable-libfribidi --enable-libass
# ./build-meson-dep.sh fribidi -Ddocs=false
# ./build-meson-dep.sh libass

# if [ "$BUILD_LICENSE" == "gpl" ]; then

#     apply-patch x265_git x265_git-${BUILD_TYPE}.patch

#     if [ "$BUILD_TYPE" == "static" ]; then
#         X265_ARGS="-DSTATIC_LINK_CRT=ON"
#         ENABLE_SHARED=OFF
#     else
#         X265_ARGS="-DSTATIC_LINK_CRT=OFF"
#         ENABLE_SHARED=ON
#     fi

#     if [ "$BUILD_ARCH" == arm ]; then
#         apply-patch x265_git x265_git-arm.patch
#     fi

#     git -C x265_git fetch --tags
#     ./build-cmake-dep.sh x265_git/source -DCMAKE_SYSTEM_NAME=Windows -DENABLE_SHARED=$ENABLE_SHARED -DENABLE_CLI=OFF $X265_ARGS
#     FF_ARGS="$FF_ARGS --enable-libx265"

#     if [ "$BUILD_TYPE" == "shared" ]; then
#         apply-patch x264 x264-${BUILD_TYPE}.patch
#     fi
#     if [[ "$BUILD_ARCH" =~ arm ]]; then
#         X264_ARGS="--disable-asm"
#     fi

#     INSTALL_TARGET=install-lib-${BUILD_TYPE} ./build-make-dep.sh x264 --enable-${BUILD_TYPE} $X264_ARGS
#     FF_ARGS="$FF_ARGS --enable-libx264"

# fi

# ./build-make-dep.sh nv-codec-headers

# CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded ./build-cmake-dep.sh zlib

# if [ -n "$ENABLE_LIBFREETYPE" ]; then
#     ./build-cmake-dep.sh freetype
# fi

# if [ -n "$ENABLE_LIBHARFBUZZ" ]; then
#     ./build-cmake-dep.sh harfbuzz -DHB_HAVE_FREETYPE=ON
# fi

# if [ -n "$ENABLE_SDL" ]; then
#     ./build-cmake-dep.sh SDL
# fi

# if [ -n "$ENABLE_LIBJXL" ]; then

#     if [ "$BUILD_TYPE" == "shared" ]; then
#         JPEGXL_STATIC=OFF
#     else
#         JPEGXL_STATIC=ON
#     fi

#     apply-patch libjxl libjxl.patch
#     ./build-cmake-dep.sh openexr -DOPENEXR_INSTALL_TOOLS=OFF -DOPENEXR_BUILD_TOOLS=OFF -DBUILD_TESTING=OFF -DOPENEXR_IS_SUBPROJECT=ON
#     ./build-cmake-dep.sh libjxl -DBUILD_TESTING=OFF -DJPEGXL_ENABLE_BENCHMARK=OFF -DJPEGXL_ENABLE_JNI=OFF -DJPEGXL_BUNDLE_LIBPNG=OFF -DJPEGXL_ENABLE_TOOLS=OFF -DJPEGXL_ENABLE_EXAMPLES=OFF -DJPEGXL_STATIC=$JPEGXL_STATIC
# fi

# libvpx AR=lib ARFLAGS= CC=cl CXX=cl LD=link STRIP=false ./configure --as=yasm --disable-optimizations   --disable-dependency-tracking --disable-runtime-cpu-detect  --disable-thumb --disable-neon
# AR=lib ARFLAGS= CC=cl CXX=cl LD=link STRIP=false ./configure --target=armv7-win32-vs17 --as=yasm --disable-optimizations   --disable-dependency-tracking --disable-runtime-cpu-detect  --disable-thumb --disable-neon --enable-external-build --enable-static-msvcrt

if [ -n "$ENABLE_LIBVPX" ]; then
    case $BUILD_ARCH in
    amd64) libvpx_target=x86_64-win64-vs17 ;;
    x86) libvpx_target=x86-win32-vs17 ;;
    arm) libvpx_target=armv7-win32-vs17 ;;
    arm64) libvpx_target=arm64-win64-vs17 ;;
    esac

    if [ "$BUILD_TYPE" == "static" ]; then
        LIBVPX_ARGS="--enable-static-msvcrt"
    fi
    apply-patch libvpx libvpx.patch
    AR=lib ARFLAGS= CC=cl CXX=cl LD=link STRIP=false ./build-make-dep.sh libvpx --target=$libvpx_target --as=yasm --disable-optimizations --disable-dependency-tracking --disable-runtime-cpu-detect --disable-thumb --disable-neon --enable-external-build $LIBVPX_ARGS
    FF_ARGS=--enable-libvpx
fi
./build-ffmpeg.sh FFmpeg $FF_ARGS
