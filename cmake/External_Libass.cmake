# ---- Registration ----
dep_package(
    NAME        libass
    DEFAULT     0.17.3
    BUILD       meson
    FFMPEG_FLAG --enable-libass
    REQUIRES    fribidi;freetype;harfbuzz
)
dep_package_version(NAME libass VERSION 0.17.3
    URL      "https://github.com/libass/libass/archive/refs/tags/0.17.3.tar.gz"
)

# ---- Build function ----
function(build_libass)
    ExternalProject_Add(libass_target
        DEPENDS      ${LIBASS_RESOLVED_DEPENDS}
        URL          ${LIBASS_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/libass"
        CONFIGURE_COMMAND
            ${SHELL_ENV} meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Db_vscrt=mt
                -Dasm=disabled
                -Dtest=false
                -Dprofile=false
                -Dfontconfig=disabled
                -Dlibunibreak=disabled
                -Drequire-system-font-provider=false
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/libass.lib"
            "${STAGE_DIR}/lib/pkgconfig/libass.pc"
    )
    add_rename_step(libass_target libass.a ass.lib)
endfunction()
