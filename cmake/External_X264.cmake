# ---- Registration ----
dep_package(
    NAME        x264
    DEFAULT     master
    BUILD       autotools
    FFMPEG_FLAG --enable-libx264
    LICENSE     gpl
)
dep_package_version(NAME x264 VERSION master
    URL      "https://github.com/mirror/x264/archive/refs/heads/master.tar.gz"
)
dep_package_version(NAME x264 VERSION stable
    URL      "https://github.com/mirror/x264/archive/refs/heads/stable.tar.gz"
)

# ---- Build function ----
# ---- Architecture-specific flags ----
if(TARGET_ARCH MATCHES "^arm")
    set(X264_ARCH_FLAGS "--disable-asm")
else()
    set(X264_ARCH_FLAGS "")
endif()

function(build_x264)
    ExternalProject_Add(x264_target
        URL          ${X264_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/x264"
        CONFIGURE_COMMAND
            ${SHELL_ENV} ./configure
                --prefix=${STAGE_DIR}
                --enable-static
                --disable-cli
                ${X264_ARCH_FLAGS}
        BUILD_COMMAND
            $(MAKE) -C <SOURCE_DIR>
        INSTALL_COMMAND
            $(MAKE) -C <SOURCE_DIR> install
        BUILD_IN_SOURCE 1
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/x264.lib"
            "${STAGE_DIR}/lib/pkgconfig/x264.pc"
    )
endfunction()
