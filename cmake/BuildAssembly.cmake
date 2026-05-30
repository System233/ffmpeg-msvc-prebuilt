# BuildAssembly.cmake — Call build functions for all resolved dependencies

# Build each enabled dependency
foreach(_dep IN LISTS RESOLVED_DEPS)
    message(STATUS "Building dependency: ${_dep}")
    cmake_language(CALL build_${_dep})
endforeach()

# Build FFmpeg
message(STATUS "Building FFmpeg ${FFMPEG_VERSION}")
build_ffmpeg()
