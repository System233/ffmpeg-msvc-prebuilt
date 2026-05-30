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
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/freetype.lib"
            "${STAGE_DIR}/lib/pkgconfig/freetype2.pc"
    )
endfunction()
