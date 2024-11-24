#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

HELP_MSG="Usage: build.sh <x86,amd64,arm,arm64> [static,shared] [gpl,lgpl] ...FF_ARGS"
set -e
source ./env.sh

export BUILD_ARCH=${1:-$VSCMD_ARG_TGT_ARCH}
export BUILD_TYPE=${2:-shared}
export BUILD_LICENSE=${3:-gpl}

if [ -z $BUILD_ARCH ]; then
    echo "$HELP_MSG" >&2
    exit 1
fi

shift 3 || true
FF_ARGS=$@

for dep in libharfbuzz libfreetype sdl libjxl; do
    if grep -q "enable-${dep}" FFmpeg/configure; then
        export ENABLE_${dep^^}=1
        FF_ARGS="$FF_ARGS --enable-$dep"
    fi
done

echo BUILD_ARCH=$BUILD_ARCH
echo BUILD_TYPE=$BUILD_TYPE
echo BUILD_LICENSE=$BUILD_LICENSE
echo FF_ARGS=$FF_ARGS

git -C zlib apply ../zlib.patch
git -C FFmpeg apply ../ffmpeg.patch || true
git -C x265_git apply ../x265_git.patch

# --enable-libfribidi --enable-libass
# ./build-meson-dep.sh fribidi -Ddocs=false
# ./build-meson-dep.sh libass

if [ "$BUILD_LICENSE" == "gpl" ]; then

    if [[ "$BUILD_ARCH" =~ arm ]]; then
        X264_ARGS="--disable-asm"
    fi

    INSTALL_TARGET=install-lib-${BUILD_TYPE} ./build-make-dep.sh x264 --enable-${BUILD_TYPE} $X264_ARGS
    FF_ARGS="$FF_ARGS --enable-libx264"

    if [ "$BUILD_TYPE" == "static" ]; then
        X265_ARGS="-DSTATIC_LINK_CRT=on"
    fi

    if [[ "$BUILD_ARCH" = arm ]]; then
        X265_ARGS="$X265_ARGS -DCMAKE_SYSTEM_PROCESSOR=armv7l"
    elif [[ "$BUILD_ARCH" = arm64 ]]; then
        X265_ARGS="$X265_ARGS -DCMAKE_SYSTEM_PROCESSOR=arm64"
    fi

    git -C x265_git fetch --tags
    ./build-cmake-dep.sh x265_git/source -DENABLE_SHARED=on -DENABLE_CLI=off $X265_ARGS
    FF_ARGS="$FF_ARGS --enable-libx265"
fi

./build-make-dep.sh nv-codec-headers

CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded ./build-cmake-dep.sh zlib

if [ -n "$ENABLE_LIBFREETYPE" ]; then
    ./build-cmake-dep.sh freetype
fi

if [ -n "$ENABLE_LIBHARFBUZZ" ]; then
    ./build-cmake-dep.sh harfbuzz -DHB_HAVE_FREETYPE=ON
fi

if [ -n "$ENABLE_SDL" ]; then
    ./build-cmake-dep.sh SDL
fi

if [ -n "$ENABLE_LIBJXL" ]; then
    ./build-cmake-dep.sh openexr -DOPENEXR_INSTALL_TOOLS=OFF
    ./build-cmake-dep.sh libjxl -DBUILD_TESTING=OFF -DJPEGXL_ENABLE_BENCHMARK=OFF -DJPEGXL_ENABLE_JNI=OFF -DJPEGXL_BUNDLE_LIBPNG=OFF -DJPEGXL_ENABLE_TOOLS=OFF -DJPEGXL_ENABLE_EXAMPLES=OFF #-DJPEGXL_STATIC=ON
fi

./build-ffmpeg.sh FFmpeg $FF_ARGS
