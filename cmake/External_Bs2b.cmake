# ---- Registration ----
dep_package(
    NAME        bs2b
    DEFAULT     3.1.0
    BUILD       autotools
    FFMPEG_FLAG --enable-libbs2b
    REQUIRES    sndfile
)
dep_package_version(NAME bs2b VERSION 3.1.0
    URL      "https://downloads.sourceforge.net/project/bs2b/libbs2b/3.1.0/libbs2b-3.1.0.tar.gz"
)

# ---- Build function ----
function(build_bs2b)
    ExternalProject_Add(bs2b_target
        DEPENDS      ${BS2B_RESOLVED_DEPENDS}
        URL          ${BS2B_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/bs2b"
        PATCH_COMMAND ${BS2B_RESOLVED_PATCH_CMDS}
        CONFIGURE_COMMAND
            ${SHELL_COMPAT_ENV} ./configure
                --prefix=${STAGE_DIR}
                --host=${HOST_TRIPLE}
                --build=${HOST_TRIPLE}
                --enable-static
                --disable-shared
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR> 
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libbs2b.lib"
            "${STAGE_DIR}/lib/pkgconfig/libbs2b.pc"
    )
    add_rename_step(bs2b_target libbs2b.lib bs2b.lib)
    add_pkgconfig_file(bs2b_target libbs2b.pc bs2b 3.1.0 "Bauer stereophonic-to-binaural DSP library" INCLUDE_DIR bs2b)
endfunction()
