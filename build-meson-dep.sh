#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
echo -e "\n[Build $1]"
SRC_DIR=$(pwd)/$1
BUILD_DIR=build/$1
CROSS_FILE="$(pwd)/meson/win_$ARCH.ini"
shift 1
mkdir -p "$BUILD_DIR"
if [ -e "$CROSS_FILE" ]; then
    EXT_ARGS="--cross-file $CROSS_FILE"
fi
SRC_DIR="$SRC_DIR" BUILD_DIR="$BUILD_DIR" ./build-meson-dep.cmd $EXT_ARGS $@
