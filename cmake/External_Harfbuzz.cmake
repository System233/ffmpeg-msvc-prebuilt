# ---- Registration ----
dep_package(
    NAME        harfbuzz
    DEFAULT     10.1.0
    BUILD       cmake
    FFMPEG_FLAG --enable-libharfbuzz
    REQUIRES    freetype
)
dep_package_version(NAME harfbuzz VERSION 10.1.0
    URL      "https://github.com/harfbuzz/harfbuzz/archive/refs/tags/10.1.0.tar.gz"
    PATCHES  harfbuzz/msvc-pkgconfig-no-lm.patch
)

# ---- Build function ----
function(build_harfbuzz)
    ExternalProject_Add(harfbuzz_target
        DEPENDS      ${HARFBUZZ_RESOLVED_DEPENDS}
        URL          ${HARFBUZZ_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/harfbuzz"
        PATCH_COMMAND ${HARFBUZZ_RESOLVED_PATCH_CMDS}
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_PREFIX_PATH=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${MSVC_CRT_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
            -DHB_HAVE_FREETYPE=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/harfbuzz.lib"
            "${STAGE_DIR}/lib/pkgconfig/harfbuzz.pc"
    )
endfunction()
