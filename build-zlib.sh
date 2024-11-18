#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e

ZLIB_SRC=$1
ZLIB_TARGZ=$1.tar.gz
ZLIB_URL="https://www.zlib.net/$ZLIB_TARGZ"
ZLIB_HASH=$2
BUILD_DIR=build/zlib

mkdir -p $BUILD_DIR
cd $BUILD_DIR
wget "$ZLIB_URL" -O $ZLIB_TARGZ &&
    echo "$ZLIB_HASH  $ZLIB_TARGZ" | sha256sum --check
tar -xzf $ZLIB_TARGZ
cmake $ZLIB_SRC --install-prefix "$INSTALL_PREFIX"
cmake --build . --config Release
cmake --install . --config Release
