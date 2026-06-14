set(VCPKG_POLICY_EMPTY_PACKAGE enabled)

file(INSTALL 
    "${CMAKE_CURRENT_LIST_DIR}/build.sh.in" 
    "${CMAKE_CURRENT_LIST_DIR}/FindFFMPEG.cmake.in" 
    "${CMAKE_CURRENT_LIST_DIR}/ffmpeg-portfile.cmake" 
    "${CMAKE_CURRENT_LIST_DIR}/vcpkg-cmake-wrapper.cmake" 
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")