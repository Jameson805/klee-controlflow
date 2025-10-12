#!/usr/bin/env python3

import argparse
from elftools.elf.elffile import ELFFile

def get_addr_info(executable_path, address):
    """
    Finds the source file, line, and column for a given instruction address
    in an ELF executable compiled with DWARF debug information.

    Args:
        executable_path (str): The path to the executable file.
        address (int): The instruction address to look up.

    Returns:
        A tuple (filename, line, column) if the address is found,
        otherwise None.
    """
    best_match = None

    with open(executable_path, 'rb') as f:
        elffile = ELFFile(f)

        if not elffile.has_dwarf_info():
            print(f"Warning: No DWARF info found in '{executable_path}'.")
            print("Please compile the executable with the '-g' flag (e.g., 'gcc -g my_program.c -o my_program').")
            return None

        dwarfinfo = elffile.get_dwarf_info()

        # Iterate over all Compilation Units (CUs) in the DWARF information.
        # Each CU typically corresponds to one source file.
        for cu in dwarfinfo.iter_CUs():
            # Get the line program, which maps addresses to source code lines.
            line_program = dwarfinfo.line_program_for_CU(cu)

            # Get the full filenames for this CU. The line program entries
            # only contain an index into this list.
            cu_filenames = [entry.name.decode('utf-8') for entry in line_program['file_entry']]

            for entry in line_program.get_entries():
                if entry.state is None:
                    continue

                if entry.state.address == address:
                    # The file index in DWARF is 1-based, so we subtract 1.
                    return cu_filenames[entry.state.file - 1], entry.state.line, entry.state.column

    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Find the source file, line, and column for a given instruction address."
    )
    parser.add_argument(
        'executable_path',
        help="The path to the ELF executable file."
    )
    parser.add_argument(
        'address',
        help="The instruction address in hexadecimal format (e.g., 0x40114b)."
    )

    args = parser.parse_args()

    try:
        # Convert the hex string from the command line to an integer.
        address_int = int(args.address, 16)
    except ValueError:
        print(f"Error: Invalid address format. Please use a hexadecimal string like '0x123abc'.")
        exit(1)

    # Call the main function with the provided arguments.
    info = get_addr_info(args.executable_path, address_int)

    if info:
        filename, line, column = info
        # Print the result in a standard format.
        print(f"{filename}:{line}:{column}")
    else:
        print(f"Could not find debug info for address {args.address} in '{args.executable_path}'.")
        # Exit with a non-zero status to indicate that the lookup failed.
        exit(1)
