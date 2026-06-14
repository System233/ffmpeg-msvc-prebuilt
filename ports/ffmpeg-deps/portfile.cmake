message(STATUS "[ffmpeg-deps] All dependencies resolved by vcpkg dependency graph")

file(COPY "${CMAKE_CURRENT_LIST_DIR}/copyright"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")

file(INSTALL "${CMAKE_CURRENT_LIST_DIR}/copyright"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"
     RENAME copyright)
