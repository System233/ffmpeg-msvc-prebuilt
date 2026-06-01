# ---- Registration ----
dep_package(
    NAME        gsm
    DEFAULT     1.0.24
    BUILD       meson
    FFMPEG_FLAG --enable-libgsm
)
dep_package_version(NAME gsm VERSION 1.0.24
    URL      "https://www.quut.com/gsm/gsm-1.0.24.tar.gz"
)

# ---- Build function ----
function(build_gsm)
    ExternalProject_Add(gsm_target
        URL          ${GSM_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/gsm"
        CONFIGURE_COMMAND
            meson setup <BINARY_DIR> <SOURCE_DIR>
                --prefix=${STAGE_DIR}
                --buildtype=release
                --default-library=static
                --vsenv
                -Db_vscrt=mt
        BUILD_COMMAND
            meson compile -C <BINARY_DIR>
        INSTALL_COMMAND
            meson install -C <BINARY_DIR>
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/gsm.lib"
            "${STAGE_DIR}/lib/pkgconfig/gsm.pc"
    )
    ExternalProject_Add_Step(gsm_target copy_meson_build
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_LIST_DIR}/../patches/gsm/meson.build"
            <SOURCE_DIR>/meson.build
        DEPENDEES download update patch
        DEPENDERS configure
    )
    add_rename_step(gsm_target libgsm.a gsm.lib)
endfunction()
