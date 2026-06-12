# ---- Registration ----
dep_package(
    NAME        speex
    DEFAULT     1.2.1
    BUILD       autotools
    FFMPEG_FLAG --enable-libspeex
)
dep_package_version(NAME speex VERSION 1.2.1
    URL      "https://downloads.xiph.org/releases/speex/speex-1.2.1.tar.gz"
)

# ---- Build function ----
function(build_speex)
    skip_if_staged_target(speex_target LIBS speex)
    ExternalProject_Add(speex_target
        URL          ${SPEEX_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/speex"
        PATCH_COMMAND ${SPEEX_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_ENV} ./configure
                --prefix=${STAGE_DIR}
                --host=${HOST_TRIPLE}
                --enable-static
                --disable-shared
                --disable-dependency-tracking
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libspeex.lib"
            "${STAGE_DIR}/lib/pkgconfig/speex.pc"
    )
endfunction()
