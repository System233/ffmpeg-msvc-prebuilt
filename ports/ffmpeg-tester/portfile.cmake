set(VCPKG_POLICY_EMPTY_PACKAGE enabled)

vcpkg_cmake_configure(
    SOURCE_PATH "${CMAKE_CURRENT_LIST_DIR}"
)
vcpkg_cmake_build()

file(COPY "${CMAKE_CURRENT_LIST_DIR}/copyright"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")
