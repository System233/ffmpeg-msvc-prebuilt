#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
SRC_DIR=$(pwd)/$1
BUILD_DIR=build/$1
shift 1
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake "$SRC_DIR" --install-prefix "$INSTALL_PREFIX" $@
cmake --build . --config Release -j$(nproc)
cmake --install . --config Release
