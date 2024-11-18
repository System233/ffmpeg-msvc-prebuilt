#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

# build.sh [x86,amd64,arm,arm64] [static|shared] [gpl|lgpl] ...FF_ARGS
set -e
source ./env.sh

export BUILD_ARCH=${1:-$VSCMD_ARG_TGT_ARCH}
export BUILD_TYPE=${2:-shared}
export BUILD_LICENSE=${3:-gpl}
shift 3
FF_ARGS=$@

echo BUILD_ARCH=$BUILD_ARCH
echo BUILD_TYPE=$BUILD_TYPE
echo BUILD_LICENSE=$BUILD_LICENSE
echo FF_ARGS=$FF_ARGS

git -C zlib apply ../zlib.patch
git -C FFmpeg apply ../ffmpeg.patch

# --enable-libfribidi --enable-libass
# ./build-meson-dep.sh fribidi -Ddocs=false
# ./build-meson-dep.sh libass

./build-make-dep.sh nv-codec-headers

CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded ./build-cmake-dep.sh zlib
./build-cmake-dep.sh freetype
./build-cmake-dep.sh harfbuzz -DHB_HAVE_FREETYPE=ON

./build-cmake-dep.sh SDL

# ./build-cmake-dep.sh openexr -DOPENEXR_INSTALL_TOOLS=OFF
# ./build-cmake-dep.sh libjxl -DBUILD_TESTING=OFF -DJPEGXL_ENABLE_BENCHMARK=OFF -DJPEGXL_ENABLE_JNI=OFF -DJPEGXL_BUNDLE_LIBPNG=OFF -DJPEGXL_ENABLE_TOOLS=OFF -DJPEGXL_ENABLE_EXAMPLES=OFF #-DJPEGXL_STATIC=ON

./build-ffmpeg.sh FFmpeg --enable-libfreetype --enable-libharfbuzz --enable-sdl $FF_ARGS #--enable-libjxl $FF_ARGS
