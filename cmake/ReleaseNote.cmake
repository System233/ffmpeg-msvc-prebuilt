# ReleaseNote.cmake — Generate RELEASE_NOTE.txt

set(_release_note_file "${CMAKE_CURRENT_BINARY_DIR}/RELEASE_NOTE.txt")

set(_content "")
string(APPEND _content "FFmpeg MSVC Build - Release Note\n")
string(APPEND _content "================================\n")
string(APPEND _content "Date:        [Built on demand]\n")
string(APPEND _content "FFmpeg:      ${FFMPEG_VERSION} (${FFMPEG_RESOLVED_URL_TYPE})\n")
string(APPEND _content "Link type:   ${LINK_TYPE}\n")
string(APPEND _content "Target:      ${TARGET_ARCH} (${ARCH_NAME})\n")
string(APPEND _content "License:     ${LICENSE}\n")
string(APPEND _content "\nDependencies:\n")

foreach(_dep IN LISTS RESOLVED_DEPS)
    string(APPEND _content "  ${_dep}       ${${_dep}_RESOLVED_URL}\n")
endforeach()

string(APPEND _content "\nBuild command:\n")
string(APPEND _content "  cmake -S . -B build -DFFMPEG_VERSION=${FFMPEG_VERSION}")
string(APPEND _content " -DLINK_TYPE=${LINK_TYPE} -DLICENSE=${LICENSE}")
if(DEP_VERSION_OVERRIDE)
    string(APPEND _content " -DDEP_VERSION_OVERRIDE=\"${DEP_VERSION_OVERRIDE}\"")
endif()
string(APPEND _content "\n")

file(WRITE "${_release_note_file}" "${_content}")

add_custom_target(release_note
    COMMAND ${CMAKE_COMMAND} -E echo "Release note written to: ${_release_note_file}"
    COMMAND ${CMAKE_COMMAND} -E cat "${_release_note_file}"
    COMMENT "Generating release note"
)
