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
    BUILD_ARCH=Win32
    ;;
amd64)
    BUILD_ARCH=x64
    ;;
esac

if [ $BUILD_TYPE == "static" ]; then
    BUILD_SHARED_LIBS=ON
    CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded
else
    BUILD_SHARED_LIBS=ON
    CMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL
fi
cmake "$SRC_DIR" --install-prefix "$INSTALL_PREFIX" -A=$BUILD_ARCH -D_WIN32=1 -DBUILD_SHARED_LIBS=$BUILD_SHARED_LIBS -DCMAKE_MSVC_RUNTIME_LIBRARY=$CMAKE_MSVC_RUNTIME_LIBRARY $@
cmake --build . --config Release -j$(nproc)
cmake --install . --config Release
