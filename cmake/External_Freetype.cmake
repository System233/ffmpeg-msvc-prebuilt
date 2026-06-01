# ---- Registration ----
dep_package(
    NAME        freetype
    DEFAULT     VER-2-13-3
    BUILD       cmake
    FFMPEG_FLAG --enable-libfreetype
)
dep_package_version(NAME freetype VERSION VER-2-13-3
    URL "https://github.com/freetype/freetype/archive/refs/tags/VER-2-13-3.tar.gz"
)

# ---- Build function ----
function(build_freetype)
    ExternalProject_Add(freetype_target
        URL          ${FREETYPE_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/freetype"
        CMAKE_ARGS 
            ${DEPS_CMAKE_ARGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/freetype.lib"
            "${STAGE_DIR}/lib/pkgconfig/freetype2.pc"
    )
endfunction()
