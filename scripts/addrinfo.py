#!/usr/bin/env python3

import argparse
from elftools.elf.elffile import ELFFile
import os
from typing import Optional, Tuple, Dict, Any
import bisect

# Per-executable cache: exe -> preprocessed DWARF lookup data
_ADDR_CACHE: Dict[str, Dict[str, Any]] = {}


def get_addr_info(exe: str, address: int) -> Optional[Tuple[str, int, int]]:
    """
    Resolve address to (file, line, col) similar to addr2dbg.py but with caching:
    - Build a mapping addr -> (path, line, col) once per exe.
    - On each query, binary-search nearest previous address like addr2line.
    """

    # Build cache on first use
    if exe not in _ADDR_CACHE:
        with open(exe, "rb") as stream:
            elffile = ELFFile(stream)
            if not elffile.has_dwarf_info():
                _ADDR_CACHE[exe] = {"has_dwarf": False}
                return None
            dwarfinfo = elffile.get_dwarf_info()

            # Helper: build full path from CU top DIE (DW_AT_name + DW_AT_comp_dir)
            def cu_full_path(cu) -> Optional[str]:
                top = cu.get_top_DIE()
                name_attr = top.attributes.get("DW_AT_name")
                if not name_attr:
                    return None
                name = name_attr.value
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                if os.path.isabs(name):
                    return os.path.normpath(name)
                comp_dir_attr = top.attributes.get("DW_AT_comp_dir")
                if comp_dir_attr:
                    comp_dir = comp_dir_attr.value
                    if isinstance(comp_dir, bytes):
                        comp_dir = comp_dir.decode("utf-8", "replace")
                    return os.path.normpath(os.path.join(comp_dir, name))
                return os.path.normpath(name)

            # addr -> (path, line, col)
            addr_map: Dict[int, Tuple[str, int, int]] = {}

            for cu in dwarfinfo.iter_CUs():
                cu_path = cu_full_path(cu)
                if cu_path is None:
                    continue
                line_prog = dwarfinfo.line_program_for_CU(cu)
                if line_prog is None:
                    continue
                for entry in line_prog.get_entries():
                    state = entry.state
                    if state is None:
                        continue
                    addr_map[state.address] = (cu_path, state.line, state.column)

            _ADDR_CACHE[exe] = {
                "has_dwarf": True,
                "addr_map": addr_map,
            }

    cache = _ADDR_CACHE[exe]
    if not cache.get("has_dwarf"):
        return None

    addr_map: Dict[int, Tuple[str, int, int]] = cache["addr_map"]
    if not addr_map:
        return None

    # Nearest-previous address (addr2line behavior)
    addrs = sorted(addr_map.keys())
    idx = bisect.bisect_right(addrs, address) - 1
    if idx < 0:
        return None
    return addr_map[addrs[idx]]


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

    info = get_addr_info(args.executable_path, address_int)

    if info:
        filename, line, column = info
        print(f"{filename}:{line}:{column}")
    else:
        print(f"Could not find debug info for address {args.address} in '{args.executable_path}'.")
        exit(1)
