# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

set -e
SRC_DIR=$(pwd)
export GNULIB_SRCDIR=$SRC_DIR/gnulib
export PATH=$PATH:$GNULIB_SRCDIR

./build-make-dep.sh gmplib --host=amd64-windows --prefix=$INSTALL_PREFIX --disable-shared --enable-static --disable-assembly gmp_cv_asm_w32=.word
# mv $INSTALL_PREFIX/lib/libgmp.a $INSTALL_PREFIX/lib/gmp.lib



cd $SRC_DIR/gnutls/devel/nettle

gnulib-tool --import unistd
automake -a -c
autoconf

./configure --host=amd64-windows --prefix=$INSTALL_PREFIX --disable-shared --enable-static --enable-public-key LDFLAGS="-L$INSTALL_PREFIX/lib" CFLAGS="-I$INSTALL_PREFIX/include"

make -j$(nproc) install

cd $SRC_DIR/gnutls/devel/libtasn1
./bootstrap
./configure --host=amd64-windows --prefix=$INSTALL_PREFIX --disable-shared --enable-static  --disable-valgrind-tests  --disable-doc   --disable-dependency-tracking CFLAGS=-DASN1_STATIC
make -C lib install
# mv $INSTALL_PREFIX/lib/libtasn1.a $INSTALL_PREFIX/lib/tasn1.lib


cd $SRC_DIR/libev
gnulib-tool --import sys_time
autoconf
./configure --host=amd64-windows --prefix=$INSTALL_PREFIX --disable-shared --enable-static
# ln -sf /bin/libtool libtool
make install -j$(nproc)



cd $SRC_DIR/gnutls
# find . -name "*.gperf"|xargs -P$(nproc) -I{} sed -i "s/\r//g" '{}'
gnulib-tool --add-import dirent opendir closedir readdir --local-dir=gl
aclocal -I m4
autoconf
./configure --host=amd64-windows --prefix=/usr/local --disable-shared --enable-static --with-included-unistring --with-libev-prefix=/usr/local CFLAGS=-I/usr/local/include LDFLAGS=-L/usr/local/lib --without-p11-kit --disable-hardware-acceleration --disable-cxx -disable-tests    --disable-tools  --disable-doc   
# ln -sf /bin/libtool libtool
make install -j$(nproc)
