# ---- Registration ----
dep_package(
    NAME    highway
    DEFAULT 1.2.0
    BUILD   cmake
)
dep_package_version(NAME highway VERSION 1.2.0
    URL "https://github.com/google/highway/archive/refs/tags/1.2.0.tar.gz"
)

# ---- Build function ----
function(build_highway)
    ExternalProject_Add(highway_target
        URL          ${HIGHWAY_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/highway"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DBUILD_TESTING=OFF
            -DHWY_ENABLE_TESTS=OFF
            -DHWY_ENABLE_EXAMPLES=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/hwy.lib"
    )
endfunction()
