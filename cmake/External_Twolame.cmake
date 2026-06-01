# ---- Registration ----
dep_package(
    NAME        twolame
    DEFAULT     0.4.0
    BUILD       autotools
    FFMPEG_FLAG --enable-libtwolame
    LICENSE     lgpl
)
dep_package_version(NAME twolame VERSION 0.4.0
    URL      "https://sourceforge.net/projects/twolame/files/twolame/0.4.0/twolame-0.4.0.tar.gz"
    PATCHES  twolame/msvc-static-lib.patch
)

# ---- Build function ----
function(build_twolame)
    ExternalProject_Add(twolame_target
        URL          ${TWOLAME_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/twolame"
        PATCH_COMMAND ${TWOLAME_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_COMPAT_ENV} 
            ./configure
                --prefix=${STAGE_DIR}
                --host=${HOST_TRIPLE}
                --enable-shared=no
                --enable-static
                --disable-dependency-tracking
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/twolame.lib"
            "${STAGE_DIR}/lib/pkgconfig/twolame.pc"
    )
endfunction()
