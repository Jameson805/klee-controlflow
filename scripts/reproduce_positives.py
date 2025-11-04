#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from typing import List, Optional, Tuple

import pandas as pd
import shutil

from common import load_combined_json, save_combined_json
from addrinfo import get_addr_info

script_dir = os.path.dirname(os.path.abspath(__file__))


def parse_list(s: str) -> List[str]:
    """Split a comma-separated list and ignore empty entries/spaces."""
    return [p.strip() for p in s.split(",") if p and p.strip()]


def require_tools(tools: List[str]) -> None:
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        print(
            f"Error: required tools not found on PATH: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)


def run_gdb_trace(executable: str, arg_files: List[str], timeout: int) -> str:
    """Run gdb batch trace script and return stdout (trace of PCs)."""
    script = os.path.join(script_dir, "trace.gdb")
    cmd = ["gdb", "-batch", "-x", script, "--args", executable] + arg_files
    proc = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        bufsize=-1,
        timeout=timeout,
    )
    return proc.stdout


def compare_traces_first_diff(trace_a: str, trace_b: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (index, addr_a, addr_b) at first differing line; None if identical."""
    lines_a = trace_a.splitlines()
    lines_b = trace_b.splitlines()
    max_len = max(len(lines_a), len(lines_b))
    for i in range(max_len):
        a = lines_a[i] if i < len(lines_a) else None
        b = lines_b[i] if i < len(lines_b) else None
        if a != b:
            addr_a = int(a, 16) if a is not None else None
            addr_b = int(b, 16) if b is not None else None
            return i, addr_a, addr_b
    return None, None, None


def compare_traces_prev_same(trace_a: str, trace_b: str) -> Tuple[Optional[int], Optional[int]]:
    """Return (index, addr_prev) where addr_prev is the line BEFORE first diff; None if identical."""
    lines_a = trace_a.splitlines()
    lines_b = trace_b.splitlines()
    max_len = max(len(lines_a), len(lines_b))
    for i in range(max_len):
        a = lines_a[i] if i < len(lines_a) else None
        b = lines_b[i] if i < len(lines_b) else None
        if a != b:
            if i - 1 < 0:
                return None, None
            return i, int(lines_a[i - 1], 16)
    return None, None


def format_addr_info(executable: str, addr: Optional[int]) -> str:
    if addr is None:
        return "<no address>"
    info = get_addr_info(executable, addr)
    if info is None:
        return f"0x{addr:x}: <no debug info>"
    file, line, col = info
    src_line = None
    try:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            for i, content in enumerate(f, start=1):
                if i == line:
                    src_line = content.rstrip("\n")
                    break
    except Exception:
        src_line = None
    if src_line is not None:
        return f"0x{addr:x}: {file}:{line}:{col} | {src_line}"
    else:
        return f"0x{addr:x}: {file}:{line}:{col}"


def print_nearest_debug_info(
    executable: str,
    trace_text: str,
    start_index: int,
    failed_addr: Optional[int],
    mode_label: Optional[str] = None,
) -> bool:
    """Walk backward from start_index (bounded) to find the nearest addr with debug info and print it.

    If mode_label is None, prints like original dataframe mode:
      nearest debug info at 0x<failed_addr> -> file:line:col

    If mode_label is provided (e.g., "  run A"), prints:
      <mode_label> nearest: 0xADDR: file:line:col | <source>

    Returns True if something was printed (found), else prints a 'no debug info' message and returns False.
    """
    lines = trace_text.splitlines()
    if not lines:
        if mode_label:
            print(f"{mode_label}: no debug info found for previous addresses")
        else:
            print("no debug info found for previous addresses")
        return False

    start = min(max(start_index, 0), len(lines) - 1)
    steps = 0
    j = start
    while j >= 0:
        try:
            addr = int(lines[j], 16)
        except Exception:
            j -= 1
            steps += 1
            continue
        info = get_addr_info(executable, addr)
        if info is not None:
            if mode_label:
                print(f"{mode_label} nearest:", format_addr_info(executable, addr))
            else:
                f, l, c = info
                # Match previous text exactly for dataframe mode
                if failed_addr is not None:
                    print(f"nearest debug info at 0x{failed_addr:x} -> {f}:{l}:{c}")
                else:
                    print(f"nearest debug info -> {f}:{l}:{c}")
            return True
        j -= 1
        steps += 1

    if mode_label:
        print(f"{mode_label}: no debug info found for previous addresses")
    else:
        print("no debug info found for previous addresses")
    return False


def mode_dataframe(input_json: str, klee_output: str, executable: str, secret: str, public: str, timeout: int, output: Optional[str]) -> None:
    """Original mode: iterate rows from a combined JSON and attempt reproduction."""
    require_tools(["ktest-tool", "gdb"])

    secrets = parse_list(secret)
    publics = parse_list(public)

    df = load_combined_json(input_json)
    df["reproduced"] = pd.NA

    for idx, row in df[df["non_ct_count"] > 0].iterrows():
        filename = f"branch_counterexample_{row['inst_id']}.ktest"
        print(
            f"Reproducing {row['filename']}:{row['line']}:{row['column']} with {filename} ... ",
            end="",
            flush=True,
        )
        ktest_file = os.path.join(klee_output, filename)

        def extract_var(var: str) -> None:
            cmd = ["ktest-tool", "--extract", var, ktest_file]
            subprocess.run(cmd, check=True)

        # Extract public and secret variables
        for var in publics:
            extract_var(var)
        for var in secrets:
            extract_var(var)
            extract_var(f"{var}__prime")

        def run_with_vars(vars_: List[str]) -> str:
            var_files = [ktest_file + f".{v}" for v in vars_]
            return run_gdb_trace(executable, var_files, timeout)

        try:
            trace = run_with_vars(secrets + publics)
            trace_prime = run_with_vars([f"{v}__prime" for v in secrets] + publics)
        except subprocess.TimeoutExpired:
            print("Timeout")
            df.at[idx, "reproduced"] = False
            continue

        pos, addr_prev = compare_traces_prev_same(trace, trace_prime)
        if addr_prev is None:
            print("Failed with identical traces")
            df.at[idx, "reproduced"] = False
            continue

        info = get_addr_info(executable, addr_prev)
        if info is None:
            print(f"Failed at 0x{addr_prev:x}, ", end="")
            start_idx = (pos - 1) if (pos is not None and pos > 0) else 0
            print_nearest_debug_info(executable, trace, start_idx, addr_prev)
            df.at[idx, "reproduced"] = False
        else:
            file, line, col = info
            if (
                row["filename"] == file
                and row["line"] == line
                and row["column"] == col
            ):
                print("Success")
                df.at[idx, "reproduced"] = True
            else:
                print(f"Failed at 0x{addr_prev:x} -> {file}:{line}:{col}")
                df.at[idx, "reproduced"] = False

    if output:
        save_combined_json(df, output)


def mode_files(executable: str, secret_files: str, secret_prime_files: str, public_files: str, timeout: int) -> int:
    """New mode activated by leading '--': run two traces directly from provided input files.

    Returns process exit code (0 on success, non-zero on timeout or issues).
    """
    require_tools(["gdb"])

    s_files = parse_list(secret_files) if secret_files else []
    sp_files = parse_list(secret_prime_files) if secret_prime_files else []
    p_files = parse_list(public_files) if public_files else []

    if not s_files or not sp_files:
        print("Error: --secret-files and --secret-prime-files are required in '--' mode.", file=sys.stderr)
        return 2

    try:
        trace_a = run_gdb_trace(executable, s_files + p_files, timeout)
        trace_b = run_gdb_trace(executable, sp_files + p_files, timeout)
    except subprocess.TimeoutExpired:
        print("Timeout while running gdb traces", file=sys.stderr)
        return 124

    idx, addr_a, addr_b = compare_traces_first_diff(trace_a, trace_b)
    if idx is None:
        print("Traces are identical; no differing instruction found.")
        return 1

    lines_a = trace_a.splitlines()
    prev_idx = idx - 1
    if prev_idx >= 0 and prev_idx < len(lines_a):
        try:
            prev_addr = int(lines_a[prev_idx], 16)
        except Exception:
            prev_addr = None

        if prev_addr is not None:
            info = get_addr_info(executable, prev_addr)
            if info is not None:
                print(format_addr_info(executable, prev_addr))
            else:
                print(f"Divergence after 0x{prev_addr:x}, ", end="")
                print_nearest_debug_info(
                    executable,
                    trace_a,
                    prev_idx,
                    prev_addr,
                    mode_label=None,
                )
        else:
            print("<invalid address before divergence>")
    else:
        print("<no instruction before divergence>")
    return 0


def build_parsers_and_dispatch(argv: List[str]) -> int:
    """Detect mode and dispatch to the appropriate handler.

    If argv[0] is '--', we enter file-based mode where we accept:
      script.py -- executable --secret-files S --secret-prime-files S' [--public-files P]

    Otherwise, we use the original dataframe mode:
      script.py input_json klee_output executable --secret S [--public P] [--output OUT]
    """
    # Detect leading '--' manually to avoid argparse treating it as option terminator.
    dashdash_mode = len(argv) > 0 and argv[0] == "--"
    if dashdash_mode:
        argv = argv[1:]

    if dashdash_mode:
        parser = argparse.ArgumentParser(
            description=(
                "Reproduce divergence from explicit input files. Use '--' as the first "
                "argument to enable this mode."
            )
        )
        parser.add_argument("executable", help="Path to the replay executable")
        parser.add_argument(
            "--secret-files",
            required=True,
            help="Comma-separated list of secret input files (ordered as program expects)",
        )
        parser.add_argument(
            "--secret-prime-files",
            required=True,
            help="Comma-separated list of primed secret input files (ordered as program expects)",
        )
        parser.add_argument(
            "--public-files",
            required=False,
            default="",
            help="Comma-separated list of public input files (optional)",
        )
        parser.add_argument(
            "--timeout",
            required=False,
            default=60,
            type=int,
            help="Maximum time (in seconds) to allow for each replay (default: 60s)",
        )
        args = parser.parse_args(argv)
        return mode_files(
            executable=args.executable,
            secret_files=args.secret_files,
            secret_prime_files=args.secret_prime_files,
            public_files=args.public_files,
            timeout=args.timeout,
        )
    else:
        parser = argparse.ArgumentParser(
            description=(
                "Extract secret/public inputs from KLEE ktest files and reproduce positives. "
                "Use '--' as the first argument to switch to direct-file mode."
            )
        )
        parser.add_argument("input_json", help="Path to combined dataframe JSON")
        parser.add_argument("klee_output", help="Path to KLEE output directory")
        parser.add_argument("executable", help="Path to the replay executable")
        parser.add_argument(
            "--secret",
            required=True,
            help="Comma-separated list of secret variable names (required)",
        )
        parser.add_argument(
            "--public",
            required=False,
            default="",
            help="Comma-separated list of public variable names (optional)",
        )
        parser.add_argument(
            "--output",
            required=False,
            default=None,
            help="Path to write output JSON with reproduced column (optional)",
        )
        parser.add_argument(
            "--timeout",
            required=False,
            default=60,
            type=int,
            help="Maximum time (in seconds) to allow for each replay (default: 60s)",
        )
        args = parser.parse_args(argv)
        mode_dataframe(
            input_json=args.input_json,
            klee_output=args.klee_output,
            executable=args.executable,
            secret=args.secret,
            public=args.public,
            timeout=args.timeout,
            output=args.output,
        )
        return 0


def main():
    sys.exit(build_parsers_and_dispatch(sys.argv[1:]))


if __name__ == "__main__":
    main()
