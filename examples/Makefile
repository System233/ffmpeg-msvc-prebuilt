# GNU Makefile for ffmeta
# Uses pkg-config to obtain compiler and linker flags
#
# Usage:
#   make PKG_CONFIG_PATH=<prefix>/lib/pkgconfig
#   make install PREFIX=/usr/local DESTDIR=
#
# From this directory:
#   PKG_CONFIG_PATH=../../path/to/ffmpeg_prefix/lib/pkgconfig make

FFMPEG_LIBS = libavformat libavcodec libavutil

CFLAGS  ?= -Wall -g
CFLAGS  := $(shell pkg-config --cflags $(FFMPEG_LIBS)) $(CFLAGS)
LDLIBS  := $(shell pkg-config --libs $(FFMPEG_LIBS)) $(LDLIBS)

PREFIX  ?= /usr/local

ffmeta: main.c
	$(CC) $(CFLAGS) -o $@ main.c $(LDLIBS)

install: ffmeta
	install -d $(DESTDIR)$(PREFIX)/bin
	install ffmeta $(DESTDIR)$(PREFIX)/bin

clean:
	rm -f ffmeta

.PHONY: install clean
