# ---- Registration ----
dep_package(
    NAME        mbedtls
    DEFAULT     3.6.4
    BUILD       cmake
)
dep_package_version(NAME mbedtls VERSION 3.6.4
    URL "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.4/mbedtls-3.6.4.tar.bz2"
)

# ---- Build function ----
function(build_mbedtls)
    skip_if_staged_target(mbedtls_target LIBS mbedtls)
    ExternalProject_Add(mbedtls_target
        URL          ${MBEDTLS_RESOLVED_URL}
        DOWNLOAD_DIR "${CMAKE_CURRENT_BINARY_DIR}/downloads"
        SOURCE_DIR   "${CMAKE_CURRENT_BINARY_DIR}/src/mbedtls"
        CMAKE_ARGS
            ${DEPS_CMAKE_ARGS}
            -DENABLE_PROGRAMS=OFF
            -DENABLE_TESTING=OFF
            -DUSE_STATIC_MBEDTLS_LIBRARY=ON
        BUILD_BYPRODUCTS
            "${STAGE_DIR}/lib/mbedtls.lib"
            "${STAGE_DIR}/lib/mbedx509.lib"
            "${STAGE_DIR}/lib/mbedcrypto.lib"
            "${STAGE_DIR}/lib/pkgconfig/mbedtls.pc"
    )
    add_pkgconfig_file(mbedtls_target mbedtls.pc mbedtls 3.6.4 "Mbed TLS library")
    add_pkgconfig_file(mbedtls_target mbedx509.pc mbedx509 3.6.4 "Mbed X.509 library")
    add_pkgconfig_file(mbedtls_target mbedcrypto.pc mbedcrypto 3.6.4 "Mbed crypto library")
endfunction()
