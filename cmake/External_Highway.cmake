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
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
            -DBUILD_TESTING=OFF
            -DHWY_ENABLE_TESTS=OFF
            -DHWY_ENABLE_EXAMPLES=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/hwy.lib"
    )
endfunction()
