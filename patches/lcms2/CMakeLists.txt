cmake_minimum_required(VERSION 3.10)
project(lcms2 C)

# Sources from src/ directory
file(GLOB LCMS2_SOURCES src/cms*.c)

# Headers
set(LCMS2_PUBLIC_HEADERS
    include/lcms2.h
    include/lcms2_plugin.h
)

# Create library
add_library(lcms2 STATIC ${LCMS2_SOURCES})

# Include directories
target_include_directories(lcms2 PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# Disable compiler warnings for this external library
if(MSVC)
    target_compile_options(lcms2 PRIVATE /W0)
endif()

# Install
include(GNUInstallDirs)
install(TARGETS lcms2
    EXPORT lcms2-targets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(FILES ${LCMS2_PUBLIC_HEADERS} DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

# Generate and install pkg-config file
set(prefix "${CMAKE_INSTALL_PREFIX}")
set(exec_prefix "\${prefix}")
set(libdir "\${exec_prefix}/${CMAKE_INSTALL_LIBDIR}")
set(includedir "\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}")
set(VERSION "2.16")
set(PACKAGE "lcms2")
set(LIB_PLUGINS "")
set(LIB_MATH "")
set(LIB_THREAD "")

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/lcms2.pc.in"
    "${CMAKE_CURRENT_BINARY_DIR}/lcms2.pc"
    @ONLY
)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/lcms2.pc"
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
