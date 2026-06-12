# ---- Registration ----
dep_package(
    NAME        theora
    DEFAULT     1.2.0
    BUILD       autotools
    FFMPEG_FLAG --enable-libtheora
    REQUIRES    ogg
)
dep_package_version(NAME theora VERSION 1.2.0
    URL "https://downloads.xiph.org/releases/theora/libtheora-1.2.0.tar.gz"
)

# ---- Build function ----
function(build_theora)
    skip_if_staged_target(theora_target theora)
    message(STATUS "INFO build_theora")
    ExternalProject_Add(theora_target
        DEPENDS      ${THEORA_RESOLVED_DEPENDS}
        URL          ${THEORA_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/theora"
        CONFIGURE_COMMAND
            ./configure
                --prefix=${STAGE_DIR}
                --host=${HOST_TRIPLE}
                --enable-static
                --disable-shared
                --disable-dependency-tracking
                --disable-examples
                --disable-oggtest
                --disable-vorbistest
                --disable-asm
                ${COMPAT_ENV} 
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/theora.lib"
            "${STAGE_DIR}/lib/theoradec.lib"
            "${STAGE_DIR}/lib/theoraenc.lib"
            "${STAGE_DIR}/lib/pkgconfig/theora.pc"
            "${STAGE_DIR}/lib/pkgconfig/theoradec.pc"
            "${STAGE_DIR}/lib/pkgconfig/theoraenc.pc"
    )
    add_rename_step(theora_target libtheora.lib theora.lib)
    add_rename_step(theora_target libtheoradec.lib theoradec.lib)
    add_rename_step(theora_target libtheoraenc.lib theoraenc.lib)
    add_libtool_step(theora_target)
endfunction()
