file(GLOB_RECURSE _pdbs "${SRC_DIR}/*.pdb")

foreach(_pdb ${_pdbs})
    get_filename_component(_name "${_pdb}" NAME)
    file(COPY "${_pdb}" DESTINATION "${DST_DIR}")
    message(STATUS "Installed PDB: ${_name}")
endforeach()
