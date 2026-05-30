# ---- Registration ----
dep_package(
    NAME        sdl2
    DEFAULT     2.30.11
    BUILD       cmake
    FFMPEG_FLAG --enable-sdl2
)
dep_package_version(NAME sdl2 VERSION 2.30.11
    URL "https://github.com/libsdl-org/SDL/archive/refs/tags/release-2.30.11.tar.gz"
)

# ---- Build function ----
function(build_sdl2)
    ExternalProject_Add(sdl2_target
        URL          ${SDL2_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/sdl2"
        CMAKE_ARGS
            -DCMAKE_TOOLCHAIN_FILE:FILEPATH=${CMAKE_TOOLCHAIN_FILE}
            -DCMAKE_INSTALL_PREFIX=${STAGE_DIR}
            -DCMAKE_BUILD_TYPE=Release
            -DCMAKE_POLICY_DEFAULT_CMP0091=NEW
            -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DCMAKE_MSVC_RUNTIME_LIBRARY=${CMAKE_MSVC_RUNTIME_LIBRARY}
            -DBUILD_SHARED_LIBS=OFF
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/SDL2.lib"
            "${STAGE_DIR}/lib/pkgconfig/sdl2.pc"
    )
endfunction()
