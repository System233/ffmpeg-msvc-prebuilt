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

case $ARCH in
x86)
    ARCH=Win32
    ;;
amd64)
    ARCH=x64
    ;;
esac

if [ $ARCH == "x86" ]; then
    ARCH=Win32
fi
cmake "$SRC_DIR" --install-prefix "$INSTALL_PREFIX" -A=$ARCH $@
cmake --build . --config Release -j$(nproc)
cmake --install . --config Release
