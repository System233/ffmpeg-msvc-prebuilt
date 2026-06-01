# ---- Registration ----
dep_package(
    NAME        sndfile
    DEFAULT     1.2.2
    BUILD       cmake
    LICENSE     lgpl
)
dep_package_version(NAME sndfile VERSION 1.2.2
    URL "https://github.com/libsndfile/libsndfile/archive/refs/tags/1.2.2.tar.gz"
)

# ---- Build function ----
function(build_sndfile)
    ExternalProject_Add(sndfile_target
        URL          ${SNDFILE_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/sndfile"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DENABLE_EXTERNAL_LIBS=OFF
            -DENABLE_PACKAGE_CONFIG=ON
            -DBUILD_TESTING=OFF
            -DBUILD_PROGRAMS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/sndfile.lib"
            "${STAGE_DIR}/lib/pkgconfig/sndfile.pc"
    )
endfunction()
