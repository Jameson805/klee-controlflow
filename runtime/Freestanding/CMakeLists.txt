#===------------------------------------------------------------------------===#
#
#                     The KLEE Symbolic Virtual Machine
#
# This file is distributed under the University of Illinois Open Source
# License. See LICENSE.TXT for details.
#
#===------------------------------------------------------------------------===#

set(LIB_PREFIX "RuntimeFreestanding")
set(SRC_FILES
        explicit_bzero.c
        fortify-fs.c
        memcmp.c
        memcpy.c
        memmove.c
        memset.c
        )

# Build it
include("${CMAKE_SOURCE_DIR}/cmake/compile_bitcode_library.cmake")
prefix_with_path("${SRC_FILES}" "${CMAKE_CURRENT_SOURCE_DIR}/" prefixed_files)
add_bitcode_library_targets("${LIB_PREFIX}" "${prefixed_files}" "" "")

prefix_with_path("explicit_bzero.c" "${CMAKE_CURRENT_SOURCE_DIR}/" explicit_bzero_file)
add_bitcode_library_targets("RuntimeExplicitBzero" "${explicit_bzero_file}" "" "")
