# ---- Registration ----
dep_package(
    NAME        openexr
    DEFAULT     3.3.2
    BUILD       cmake
)
dep_package_version(NAME openexr VERSION 3.3.2
    URL "https://github.com/AcademySoftwareFoundation/openexr/archive/refs/tags/v3.3.2.tar.gz"
)

# ---- Build function ----
function(build_openexr)
    ExternalProject_Add(openexr_target
        URL          ${OPENEXR_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/openexr"
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
            -DOPENEXR_INSTALL_TOOLS=OFF
            -DOPENEXR_BUILD_TOOLS=OFF
            -DBUILD_TESTING=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/OpenEXR.lib"
            "${STAGE_DIR}/lib/pkgconfig/OpenEXR.pc"
    )
endfunction()
