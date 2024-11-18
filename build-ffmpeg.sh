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
./configure --prefix=. --toolchain=msvc
iconv -f gbk config.h >config.h.tmp && mv config.h.tmp config.h
make -j$(nproc)
make install prefix=$INSTALL_PREFIX $@
