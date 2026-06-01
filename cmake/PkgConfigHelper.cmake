# ---- add_pkgconfig_file(target pc_file lib_name version description [REQUIRES dep1;dep2]) ----
macro(add_pkgconfig_file _target _pc_file _lib_name _version _description)
    cmake_parse_arguments(_pc "" "INCLUDE_DIR" "REQUIRES" ${ARGN})

    set(_req "")
    if(_pc_REQUIRES)
        string(REPLACE ";" " " _req_str "${_pc_REQUIRES}")
        set(_req "Requires: ${_req_str}\n")
    endif()

    set(_inc "\${includedir}")
    if(_pc_INCLUDE_DIR)
        set(_inc "\${includedir}/${_pc_INCLUDE_DIR}")
    endif()

    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/${_pc_file}"
        "prefix=${STAGE_DIR}\n"
        "exec_prefix=\${prefix}\n"
        "libdir=\${exec_prefix}/lib\n"
        "includedir=\${prefix}/include\n"
        "\n"
        "Name: ${_lib_name}\n"
        "Description: ${_description}\n"
        "Version: ${_version}\n"
        "${_req}"
        "Conflicts:\n"
        "Libs: -L\${libdir} -l${_lib_name}\n"
        "Cflags: -I${_inc}\n"
    )
    ExternalProject_Add_Step(${_target} ${_lib_name}_pc
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_BINARY_DIR}/${_pc_file}"
            "${STAGE_DIR}/lib/pkgconfig/${_pc_file}"
        DEPENDEES install
    )
endmacro()

# ---- add_rename_step(target from to) ----
macro(add_rename_step _target _from _to)
    ExternalProject_Add_Step(${_target} rename
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${STAGE_DIR}/lib/${_from}"
            "${STAGE_DIR}/lib/${_to}"
        DEPENDEES install
    )
endmacro()


macro(patch_pkg_config _prefix)
    file(GLOB _pcs "${_prefix}/lib/pkgconfig/*.pc")
    file(GLOB _share "${_prefix}/share/pkgconfig/*.pc")
    if(_share)
        list(APPEND _pcs ${_share})
    endif()
    foreach(_pc IN LISTS _pcs)
        file(READ "${_pc}" _content)
        string(REPLACE "${STAGE_DIR}" "\${pcfiledir}/../.." _content "${_content}")
        file(WRITE "${_pc}" "${_content}")
    endforeach()
endmacro()