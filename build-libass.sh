#!/bin/bash
# Copyright (c) 2024 System233
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e -x
echo SET test
SRC_DIR=$(pwd)

export TOOLCHAIN_SRCDIR="$(pwd)/toolchain"
export AR=win-ar
export RANLIB=win-ranlib
export PATH=$TOOLCHAIN_SRCDIR:$PATH

echo -e "\n[Build fribidi]"
cd $SRC_DIR/fribidi
NOCONFIGURE=1 ./autogen.sh
CFLAGS="$CFLAGS -DHAVE_STRINGIZE" ./configure "--host=${BUILD_ARCH}-windows" --prefix=$INSTALL_PREFIX --disable-shared --enable-static --disable-dependency-tracking 
make -C lib install -j1 CFLAGS="$CFLAGS -DHAVE_STRINGIZE"
make install-data-am


echo -e "\n[Build libass]"
cd $SRC_DIR/libass
NOCONFIGURE=1 ./autogen.sh
CFLAGS="$CFLAGS" ./configure "--host=${BUILD_ARCH}-windows" --prefix=$INSTALL_PREFIX --disable-shared --enable-static --disable-asm --disable-dependency-tracking
make install -j$(nproc)
make install-data-am

