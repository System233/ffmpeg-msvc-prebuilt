# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

export INSTALL_PREFIX=${INSTALL_PREFIX:-/usr/local}
export PKG_CONFIG_PATH=$INSTALL_PREFIX/lib/pkgconfig:$INSTALL_PREFIX/share/pkgconfig
export CC=cl
export CXX=cl
