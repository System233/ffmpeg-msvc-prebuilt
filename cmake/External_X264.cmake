ExternalProject_Add(x264_target
    URL            https://code.videolan.org/videolan/x264/-/archive/master/x264-master.tar.gz
    DOWNLOAD_DIR   "${CMAKE_CURRENT_BINARY_DIR}/downloads"
    SOURCE_DIR     "${CMAKE_CURRENT_BINARY_DIR}/src/x264"
    CONFIGURE_COMMAND
        ${SHELL_ENV} ./configure
            --prefix=${STAGE_DIR}
            --enable-static
            --disable-cli

    BUILD_COMMAND
        $(MAKE)

    INSTALL_COMMAND
        $(MAKE) install prefix=${STAGE_DIR}

    BUILD_IN_SOURCE 1
    BUILD_BYPRODUCTS
        "${STAGE_DIR}/lib/x264.lib"
        "${STAGE_DIR}/lib/pkgconfig/x264.pc"
)
