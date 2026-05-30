# ---- Registration ----
dep_package(
    NAME    lcms2
    DEFAULT 2.16
    BUILD   cmake
)
dep_package_version(NAME lcms2 VERSION 2.16
    URL "https://github.com/mm2/Little-CMS/archive/refs/tags/lcms2.16.tar.gz"
)

# ---- Build function ----
function(build_lcms2)
    set(_patch_cmake "${CMAKE_CURRENT_LIST_DIR}/../patches/lcms2/CMakeLists.txt")
    ExternalProject_Add(lcms2_target
        URL          ${LCMS2_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/lcms2"
        PATCH_COMMAND
            ${CMAKE_COMMAND} -E copy "${_patch_cmake}" <SOURCE_DIR>/CMakeLists.txt
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_PREFIX_PATH=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/lcms2.lib"
            "${STAGE_DIR}/lib/pkgconfig/lcms2.pc"
    )
endfunction()
