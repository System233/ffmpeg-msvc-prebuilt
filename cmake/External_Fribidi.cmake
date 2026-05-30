ExternalProject_Add(fribidi_target
    URL            https://github.com/fribidi/fribidi/releases/download/v1.0.16/fribidi-1.0.16.tar.xz
    DOWNLOAD_DIR   "${CMAKE_CURRENT_BINARY_DIR}/downloads"
    SOURCE_DIR     "${CMAKE_CURRENT_BINARY_DIR}/src/fribidi"

    CONFIGURE_COMMAND 
        ${SHELL_ENV} AR=ar "AR_FLAGS=cr" "CFLAGS=-DHAVE_STRINGIZE" ./autogen.sh
            --prefix=${STAGE_DIR}
            --host=${HOST_TRIPLE}
            --disable-shared
            --enable-static
            --disable-dependency-tracking

    BUILD_COMMAND
        $(MAKE)

    INSTALL_COMMAND
        $(MAKE)  install  prefix=${STAGE_DIR}

    BUILD_IN_SOURCE 1
    BUILD_BYPRODUCTS
        "${STAGE_DIR}/lib/pkgconfig/fribidi.pc"
)
