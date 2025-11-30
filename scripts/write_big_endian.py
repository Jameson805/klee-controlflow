#!/usr/bin/env python3

import argparse
import sys
from typing import Optional


def parse_int(s: str) -> int:
    """Parse an integer from string, supporting decimal and 0x-prefixed hex."""
    try:
        return int(s, 0)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid integer value '{s}'") from e


def write_big_endian(path: str, value: int, size: Optional[int] = None) -> None:
    """
    Write 'value' as an unsigned big-endian binary to 'path'.

    If size is None, use the minimum number of bytes required (at least 1).
    If size is given, ensure the value fits in that many bytes.
    """
    if value < 0:
        raise ValueError("value must be non-negative (unsigned)")

    # Minimal bytes needed (at least 1)
    min_bytes = 1 if value == 0 else (value.bit_length() + 7) // 8

    if size is None:
        size = min_bytes
    elif size < min_bytes:
        raise ValueError(
            f"value 0x{value:x} (= {value}) does not fit in {size} byte(s); "
            f"needs at least {min_bytes} byte(s)"
        )

    with open(path, "wb") as f:
        f.write(int(value).to_bytes(size, byteorder="big", signed=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Write an integer to a binary file in big-endian format.\n\n"
            "Examples:\n"
            "  write_big_endian.py --output input1 --value 100\n"
            "  write_big_endian.py --output input2 --value 0x1234 --bytes 4\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output filename for the binary value.",
    )
    parser.add_argument(
        "--value",
        "-v",
        required=True,
        type=parse_int,
        help="Integer value to write (decimal or 0x-prefixed hex).",
    )
    parser.add_argument(
        "--bytes",
        "-b",
        type=int,
        default=None,
        help=(
            "Number of bytes to use (unsigned big-endian). "
            "If omitted, the minimal number of bytes is used."
        ),
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.bytes is not None and args.bytes <= 0:
        print("--bytes must be a positive integer", file=sys.stderr)
        return 2

    try:
        write_big_endian(args.output, args.value, args.bytes)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
