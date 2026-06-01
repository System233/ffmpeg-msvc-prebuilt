# ---- Registration ----
dep_package(
    NAME        libass
    DEFAULT     0.17.3
    BUILD       autotools
    FFMPEG_FLAG --enable-libass
    REQUIRES    fribidi;freetype
)
dep_package_version(NAME libass VERSION 0.17.3
    URL      "https://github.com/libass/libass/archive/refs/tags/0.17.3.tar.gz"
)

# ---- Build function ----
function(build_libass)
    ExternalProject_Add(libass_target
        DEPENDS      ${LIBASS_RESOLVED_DEPENDS}
        URL          ${LIBASS_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/libass"
        CONFIGURE_COMMAND
            ${SHELL_ENV} ./autogen.sh &&
            ${SHELL_ENV} ./configure
                --prefix=${STAGE_DIR}
                --host=${HOST_TRIPLE}
                --disable-shared
                --enable-static
                --disable-asm
                --disable-dependency-tracking
                AR=ar AR_FLAGS=cr
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/pkgconfig/libass.pc"
    )
endfunction()
