#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

# build [x86,amd64,arm,arm64] ...FF_ARGS
set -e
source ./env.sh

export ARCH=$1
shift 1
FF_ARGS=$@
# --enable-libfribidi --enable-libass
# ./build-meson-dep.sh fribidi -Ddocs=false
# ./build-meson-dep.sh libass

./build-make-dep.sh nv-codec-headers

./build-cmake-dep.sh zlib
./build-cmake-dep.sh openexr -DOPENEXR_INSTALL_TOOLS=OFF
./build-cmake-dep.sh harfbuzz
./build-cmake-dep.sh freetype

./build-cmake-dep.sh SDL
./build-cmake-dep.sh libjxl -DBUILD_TESTING=OFF -DJPEGXL_ENABLE_BENCHMARK=OFF -DJPEGXL_ENABLE_JNI=OFF -DJPEGXL_BUNDLE_LIBPNG=OFF -DJPEGXL_ENABLE_TOOLS=OFF -DJPEGXL_ENABLE_EXAMPLES=OFF #-DJPEGXL_STATIC=ON

./build-ffmpeg.sh FFmpeg --enable-libfreetype --enable-libharfbuzz --enable-sdl --enable-libjxl $FF_ARGS
