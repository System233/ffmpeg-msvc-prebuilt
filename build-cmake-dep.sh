#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
echo -e "\n[Build $1]"
SRC_DIR=$(pwd)/$1
BUILD_DIR=build/$1
shift 1
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

case $BUILD_ARCH in
x86)
    ARCH=Win32
    ;;
amd64)
    ARCH=x64
    ;;
esac

if [ $BUILD_ARCH == "x86" ]; then
    ARCH=Win32
fi
if [ $BUILD_TYPE == "static" ]; then
    BUILD_SHARED_LIBS=OFF
else
    BUILD_SHARED_LIBS=ON
fi
cmake "$SRC_DIR" --install-prefix "$INSTALL_PREFIX" -A=$BUILD_ARCH -DBUILD_SHARED_LIBS=$BUILD_SHARED_LIBS $@
cmake --build . --config Release -j$(nproc)
cmake --install . --config Release
