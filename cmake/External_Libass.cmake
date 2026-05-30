ExternalProject_Add(libass_target
    DEPENDS        fribidi_target
    URL            https://github.com/libass/libass/archive/refs/tags/0.17.3.tar.gz
    DOWNLOAD_DIR   "${CMAKE_CURRENT_BINARY_DIR}/downloads"
    SOURCE_DIR     "${CMAKE_CURRENT_BINARY_DIR}/src/libass"

    CONFIGURE_COMMAND
        ${SHELL_ENV} ./autogen.sh &&
        ${SHELL_ENV} AR=ar AR_FLAGS=cr ./configure
            --prefix=${STAGE_DIR}
            --host=${HOST_TRIPLE}
            --disable-shared
            --enable-static
            --disable-asm
            --disable-dependency-tracking

    BUILD_COMMAND
        $(MAKE)

    INSTALL_COMMAND
        $(MAKE) install prefix=${STAGE_DIR}

    BUILD_IN_SOURCE 1
    BUILD_BYPRODUCTS
        "${STAGE_DIR}/lib/pkgconfig/libass.pc"
)
