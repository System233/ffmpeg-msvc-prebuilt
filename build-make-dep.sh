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
if [ -e ./configure ]; then
    ./configure $@
fi
make -j$(nproc)
make ${INSTALL_TARGET:-install} PREFIX=$INSTALL_PREFIX
