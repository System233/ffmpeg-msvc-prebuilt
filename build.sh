#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

source ./env.sh
./build-cmake-dep.sh libjxl -DBUILD_TESTING=OFF -DJPEGXL_ENABLE_BENCHMARK=OFF -DJPEGXL_ENABLE_JNI=OFF -DJPEGXL_BUNDLE_LIBPNG=OFF -DJPEGXL_ENABLE_TOOLS=OFF -DJPEGXL_ENABLE_JPEGLI=OFF -DJPEGXL_ENABLE_EXAMPLES=OFF -DJPEGXL_STATIC=ON
./build-cmake-dep.sh SDL
./build-cmake-dep.sh freetype
./build-cmake-dep.sh harfbuzz
./build-meson-dep.sh fribidi
./build-meson-dep.sh libass

./build-zlib.sh "https://www.zlib.net/zlib-1.3.1.tar.gz" 9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23
./build-ffmpeg.sh FFmpeg --enable-libfreetype --enable-libjxl
