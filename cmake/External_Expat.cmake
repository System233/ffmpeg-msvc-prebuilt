# ---- Registration ----
dep_package(
    NAME        expat
    DEFAULT     2.8.1
    BUILD       cmake
)
dep_package_version(NAME expat VERSION 2.8.1
    URL "https://github.com/libexpat/libexpat/releases/download/R_2_8_1/expat-2.8.1.tar.gz"
)

# ---- Build function ----
function(build_expat)
    skip_if_staged_target(expat_target
        LIBS expat
    )
    ExternalProject_Add(expat_target
        URL          ${EXPAT_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/expat"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DEXPAT_BUILD_TOOLS=OFF
            -DEXPAT_BUILD_TESTS=OFF
            -DEXPAT_BUILD_EXAMPLES=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libexpat.lib"
            "${STAGE_DIR}/lib/pkgconfig/expat.pc"
    )
endfunction()
