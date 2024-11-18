#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
echo -e "\n[Build $1]"
SRC_DIR=$(pwd)/$1
shift 1
cd $SRC_DIR

if [ $BUILD_TYPE == "static" ]; then
    TYPE_ARGS="--enable-static"
else
    TYPE_ARGS="--enable-shared"
fi
if [[ $BUILD_ARCH =~ arm ]]; then
    CROSS_ARGS="--enable-cross-compile --disable-asm"
fi

if [ $BUILD_LICENSE == "gpl" ]; then
    LICENSE_ARGS="--enable-gpl --enable-version3"
fi
CFLAGS="$CFLAGS -I${SRC_DIR}/compat/stdbit"
EX_BUILD_ARGS="$TYPE_ARGS $CROSS_ARGS $LICENSE_ARGS"

git apply ../ffmpeg.patch
./configure --prefix=. --toolchain=msvc --arch=$BUILD_ARCH $EX_BUILD_ARGS $@
iconv -f gbk config.h >config.h.tmp && mv config.h.tmp config.h
make -j$(nproc)
make install prefix=$INSTALL_PREFIX
