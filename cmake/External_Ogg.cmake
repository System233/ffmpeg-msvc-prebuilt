# ---- Registration ----
dep_package(
    NAME        ogg
    DEFAULT     1.3.6
    BUILD       cmake
)
dep_package_version(NAME ogg VERSION 1.3.6
    URL "https://github.com/xiph/ogg/releases/download/v1.3.6/libogg-1.3.6.tar.gz"
)

# ---- Build function ----
function(build_ogg)
    skip_if_staged_target(ogg_target
        LIBS ogg
    )
    ExternalProject_Add(ogg_target
        URL          ${OGG_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/ogg"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/ogg.lib"
            "${STAGE_DIR}/lib/pkgconfig/ogg.pc"
    )
endfunction()
