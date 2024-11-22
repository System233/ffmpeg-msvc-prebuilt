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

# --enable-libfribidi --enable-libass
# ./build-meson-dep.sh fribidi -Ddocs=false
# ./build-meson-dep.sh libass

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
