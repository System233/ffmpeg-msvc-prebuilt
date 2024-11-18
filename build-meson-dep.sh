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
MSYS_NO_PATHCONV=1 cmd /c build-meson-dep.cmd $@