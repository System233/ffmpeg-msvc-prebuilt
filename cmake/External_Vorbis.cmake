# ---- Registration ----
dep_package(
    NAME        vorbis
    DEFAULT     1.3.7
    BUILD       cmake
    FFMPEG_FLAG --enable-libvorbis
    REQUIRES    ogg
)
dep_package_version(NAME vorbis VERSION 1.3.7
    URL "https://github.com/xiph/vorbis/releases/download/v1.3.7/libvorbis-1.3.7.tar.gz"
)

# ---- Build function ----
function(build_vorbis)
    skip_if_staged_target(vorbis_target
        LIBS vorbis
    )
    ExternalProject_Add(vorbis_target
        DEPENDS      ${VORBIS_RESOLVED_DEPENDS}
        URL          ${VORBIS_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/vorbis"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DINSTALL_PKG_CONFIG_MODULE=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/vorbis.lib"
            "${STAGE_DIR}/lib/pkgconfig/vorbis.pc"
    )
endfunction()
