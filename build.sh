#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
source ./env.sh

./build-cmake-dep.sh freetype
./build-cmake-dep.sh harfbuzz
./build-meson-dep.sh fribidi
./build-meson-dep.sh libass

./build-make-dep.sh nv-codec-headers
./build-cmake-dep.sh zlib
./build-cmake-dep.sh SDL
./build-cmake-dep.sh libjxl -DBUILD_TESTING=OFF -DJPEGXL_ENABLE_BENCHMARK=OFF -DJPEGXL_ENABLE_JNI=OFF -DJPEGXL_BUNDLE_LIBPNG=OFF -DJPEGXL_ENABLE_TOOLS=OFF -DJPEGXL_ENABLE_JPEGLI=OFF -DJPEGXL_ENABLE_EXAMPLES=OFF -DJPEGXL_STATIC=ON

./build-ffmpeg.sh FFmpeg --enable-libfreetype --enable-libass --enable-sdl --enable-libjxl
