cmake_minimum_required(VERSION 3.10)
project(ffmpeg-opstool C)

# ffmpeg source root is two directories up
get_filename_component(FFMPEG_SRC "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)

# Create the executable from the single source file
# ops_asmgen.c includes rasm.c, ops_impl.c, ops_entries.c via #include
add_executable(ops_asmgen ops_asmgen.c)

target_include_directories(ops_asmgen PRIVATE
    "${FFMPEG_SRC}"              # for libavutil/dynarray.h and other ffmpeg headers
)

# Install into host tools directory
install(TARGETS ops_asmgen DESTINATION manual-tools/ffmpeg-opstool)
