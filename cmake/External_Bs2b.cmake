# ---- Registration ----
dep_package(
    NAME        bs2b
    DEFAULT     3.1.0
    BUILD       meson
    FFMPEG_FLAG --enable-libbs2b
    REQUIRES    sndfile
)
dep_package_version(NAME bs2b VERSION 3.1.0
    URL      "https://downloads.sourceforge.net/project/bs2b/libbs2b/3.1.0/libbs2b-3.1.0.tar.gz"
)

# ---- Build function ----
function(build_bs2b)
    ExternalProject_Add(bs2b_target
        DEPENDS      ${BS2B_RESOLVED_DEPENDS}
        URL          ${BS2B_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/bs2b"
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --cross-file "${CMAKE_CURRENT_BINARY_DIR}/msvc-cross.ini"
                -Db_vscrt=mt
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/bs2b.lib"
            "${STAGE_DIR}/lib/pkgconfig/bs2b.pc"
    )
    ExternalProject_Add_Step(bs2b_target copy_meson_build
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_LIST_DIR}/../patches/bs2b/meson.build"
            <SOURCE_DIR>/meson.build
        DEPENDEES download update patch
        DEPENDERS configure
    )
    add_rename_step(bs2b_target libbs2b.a bs2b.lib)
endfunction()
