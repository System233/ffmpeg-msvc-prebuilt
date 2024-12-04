#!/bin/bash
# Copyright (c) 2024 System233
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
SRC_DIR=$(pwd)
export GNULIB_SRCDIR="$SRC_DIR/gnutls/gnulib"
export PATH=$PATH:$GNULIB_SRCDIR

echo -e "\n[Build fribidi]"
cd $SRC_DIR/fribidi
./autogen.sh
./configure --host=amd64-windows --prefix=$INSTALL_PREFIX --disable-shared --enable-static --disable-dependency-tracking CFLAGS="-DHAVE_STRINGIZE"
make -C lib install -j$(nproc)
make install-data-am


echo -e "\n[Build libass]"
cd $SRC_DIR/libass
./autogen.sh
./configure --host=amd64-windows --prefix=$INSTALL_PREFIX --disable-shared --enable-static  --disable-asm --disable-dependency-tracking
make install -j$(nproc)
make install-data-am

