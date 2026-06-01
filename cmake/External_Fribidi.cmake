# ---- Registration ----
dep_package(
    NAME        fribidi
    DEFAULT     1.0.16
    BUILD       autotools
    FFMPEG_FLAG --enable-libfribidi
)
dep_package_version(NAME fribidi VERSION 1.0.16
    URL      "https://github.com/fribidi/fribidi/releases/download/v1.0.16/fribidi-1.0.16.tar.xz"
)

# ---- Build function ----
function(build_fribidi)
    ExternalProject_Add(fribidi_target
        URL          ${FRIBIDI_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/fribidi"
        PATCH_COMMAND ${FRIBIDI_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_ENV} ./autogen.sh
                --prefix=${STAGE_DIR}
                --host=${HOST_TRIPLE}
                --disable-shared
                --enable-static
                --disable-dependency-tracking
                AR=ar 
                "AR_FLAGS=cr" 
                "CFLAGS=-DHAVE_STRINGIZE" 

        BUILD_COMMAND
            $(MAKE)

        INSTALL_COMMAND
            $(MAKE)  install  prefix=${STAGE_DIR}

        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/pkgconfig/fribidi.pc"
    )
endfunction()
