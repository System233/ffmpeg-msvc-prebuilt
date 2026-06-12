# ---- Registration ----
dep_package(
    NAME        gme
    DEFAULT     0.6.5
    BUILD       cmake
    FFMPEG_FLAG --enable-libgme
    LICENSE     lgpl
)
dep_package_version(NAME gme VERSION 0.6.5
    URL      "https://github.com/libgme/game-music-emu/releases/download/0.6.5/libgme-0.6.5-src.tar.gz"
)

# ---- Build function ----
function(build_gme)
    skip_if_staged_target(gme_target
        LIBS libgme
    )
    ExternalProject_Add(gme_target
        URL          ${GME_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/gme"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DGME_BUILD_SHARED=OFF
            -DGME_BUILD_STATIC=ON
            -DGME_BUILD_TESTING=OFF
            -DGME_BUILD_EXAMPLES=OFF
            -DGME_BUILD_FRAMEWORK=OFF
            -DGME_ENABLE_UBSAN=OFF
            -DENABLE_UBSAN=OFF
            -DBUILD_TESTING=OFF
            -DGME_ZLIB=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/gme.lib"
            "${STAGE_DIR}/lib/pkgconfig/libgme.pc"
    )
endfunction()
