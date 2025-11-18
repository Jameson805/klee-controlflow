#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from typing import List, Optional, Tuple, Dict

import pandas as pd
import shutil
import tempfile  # new

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
    """Run gdb batch trace script and return stdout (trace of PCs).

    On non-zero exit, print stdout/stderr so the user can inspect the failure.
    """
    script = os.path.join(script_dir, "trace.gdb")
    cmd = ["gdb", "-batch", "-x", script, "--args", executable] + arg_files
    proc = subprocess.run(
        cmd,
        # check=False so we can inspect stdout/stderr on failure
        check=False,
        capture_output=True,
        text=True,
        bufsize=-1,
        timeout=timeout,
    )
    if proc.returncode != 0:
        print(
            f"gdb exited with status {proc.returncode} running: {' '.join(cmd)}",
            file=sys.stderr,
        )
        if proc.stdout:
            print("=== gdb stdout ===", file=sys.stderr)
            print(proc.stdout, file=sys.stderr, end="")
        if proc.stderr:
            print("=== gdb stderr ===", file=sys.stderr)
            print(proc.stderr, file=sys.stderr, end="")
        # Re-raise as CalledProcessError to keep existing error handling semantics
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )
    return proc.stdout


def analyze_traces(trace_a: str, trace_b: str) -> Dict[str, Optional[int]]:
    """Return dict with first_diff_index, addr_a, addr_b, prev_addr."""
    lines_a = trace_a.splitlines()
    lines_b = trace_b.splitlines()
    max_len = max(len(lines_a), len(lines_b))
    for i in range(max_len):
        a = lines_a[i] if i < len(lines_a) else None
        b = lines_b[i] if i < len(lines_b) else None
        if a != b:
            addr_a = int(a, 16) if a is not None else None
            addr_b = int(b, 16) if b is not None else None
            prev_addr = None
            if i - 1 >= 0 and i - 1 < len(lines_a):
                try:
                    prev_addr = int(lines_a[i - 1], 16)
                except Exception:
                    prev_addr = None
            return {
                "first_diff_index": i,
                "addr_a": addr_a,
                "addr_b": addr_b,
                "prev_addr": prev_addr,
            }
    return {
        "first_diff_index": None,
        "addr_a": None,
        "addr_b": None,
        "prev_addr": None,
    }


def print_nearest_debug_info(
    executable: str,
    trace_text: str,
    start_index: int,
) -> bool:
    """Walk backward from start_index (bounded) to find the nearest addr with debug info and print it.

    print:
      nearest debug info at 0x<failed_addr> -> file:line:col

    Returns True if something was printed (found), else prints a 'no debug info' message and returns False.
    """
    lines = trace_text.splitlines()
    if not lines:
        print("no debug info found for previous addresses")
        return False

    start = min(max(start_index, 0), len(lines) - 1)
    j = start
    while j >= 0:
        try:
            addr = int(lines[j], 16)
        except Exception:
            j -= 1
            continue
        info = get_addr_info(executable, addr)
        if info is not None:
            f, l, c = info
            print(f"nearest debug info at 0x{addr:x} -> {f}:{l}:{c}")
            return True
        j -= 1

    print("no debug info found for previous addresses")
    return False


def extract_inputs(ktest_file: str, secrets: List[str], publics: List[str]) -> None:
    """Extract variables (including secret primes) using ktest-tool."""
    def extract_var(var: str) -> None:
        cmd = ["ktest-tool", "--extract", var, ktest_file]
        subprocess.run(cmd, check=True)
    for v in publics:
        extract_var(v)
    for s in secrets:
        extract_var(s)
        extract_var(f"{s}__prime")


def run_traces(executable: str, ktest_file: str, secrets: List[str], publics: List[str], timeout: int) -> Tuple[str, str]:
    """Run original (secrets) and prime (secret__prime) traces."""
    trace_a = run_gdb_trace(executable, [ktest_file + f".{v}" for v in secrets + publics], timeout)
    trace_b = run_gdb_trace(executable, [ktest_file + f".{v}__prime" for v in secrets] + [ktest_file + f".{v}" for v in publics], timeout)
    return trace_a, trace_b


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

        try:
            extract_inputs(ktest_file, secrets, publics)
            trace_a, trace_b = run_traces(executable, ktest_file, secrets, publics, timeout)
        except subprocess.TimeoutExpired:
            print("Timeout")
            df.at[idx, "reproduced"] = False
            continue

        analysis = analyze_traces(trace_a, trace_b)
        prev_addr = analysis["prev_addr"]
        pos = analysis["first_diff_index"]
        if prev_addr is None:
            print("Failed with identical traces")
            df.at[idx, "reproduced"] = False
            continue

        info = get_addr_info(executable, prev_addr)
        if info is None:
            print(f"Failed at 0x{prev_addr:x}, ", end="")
            start_idx = (pos - 1) if (pos is not None and pos > 0) else 0
            print_nearest_debug_info(executable, trace_a, start_idx)
            df.at[idx, "reproduced"] = False
        else:
            f, l, c = info
            # NOTE: only compare basenames to avoid issues with different paths
            if os.path.basename(row["filename"]) == os.path.basename(f) and row["line"] == l and row["column"] == c:
                print("Success")
                df.at[idx, "reproduced"] = True
            else:
                print(f"Failed at 0x{prev_addr:x} -> {f}:{l}:{c}")
                df.at[idx, "reproduced"] = False

    if output:
        save_combined_json(df, output)


def mode_ktest_file(executable: str, ktest_file: str, secret: str, public: str, timeout: int) -> int:
    """Run two traces for a single .ktest by extracting inputs like in dataframe mode."""
    require_tools(["ktest-tool", "gdb"])

    secrets = parse_list(secret)
    publics = parse_list(public)

    try:
        extract_inputs(ktest_file, secrets, publics)
        trace_a, trace_b = run_traces(executable, ktest_file, secrets, publics, timeout)
    except subprocess.TimeoutExpired:
        print("Timeout while running gdb traces", file=sys.stderr)
        return 124

    analysis = analyze_traces(trace_a, trace_b)
    prev_addr = analysis["prev_addr"]
    pos = analysis["first_diff_index"]
    if prev_addr is None:
        print("Identical traces")
        return 1

    info = get_addr_info(executable, prev_addr)
    if info is None:
        print(f"Divergence after 0x{prev_addr:x}, ", end="")
        start_idx = (pos - 1) if (pos is not None and pos > 0) else 0
        print_nearest_debug_info(executable, trace_a, start_idx, prev_addr)
    else:
        f, l, c = info
        print(f"0x{prev_addr:x}: {f}:{l}:{c}")
    return 0


def parse_secret_input_spec(spec: str) -> Dict[str, Tuple[int, int, int]]:
    """
    Parse secret input spec of the form: v1:8=100/200,v2:4=300/400
    Returns mapping: name -> (size_bytes, orig_value, prime_value)
    """
    result: Dict[str, Tuple[int, int, int]] = {}
    if not spec:
        return result
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid secret specification '{item}', expected name:bytes=val/val")
        name_part, vals = item.split("=", 1)
        name_part = name_part.strip()
        if ":" not in name_part:
            raise ValueError(f"Invalid secret specification '{item}', expected name:bytes=val/val")
        name, size_str = name_part.split(":", 1)
        name = name.strip()
        try:
            size = int(size_str, 0)
        except ValueError:
            raise ValueError(f"Invalid byte size in secret specification '{item}'")
        if size <= 0:
            raise ValueError(f"Byte size must be positive in secret specification '{item}'")
        if "/" not in vals:
            raise ValueError(f"Invalid secret specification '{item}', expected name:bytes=val/val")
        v1_str, v2_str = vals.split("/", 1)
        v1 = int(v1_str, 0)
        v2 = int(v2_str, 0)
        result[name] = (size, v1, v2)
    return result


def parse_public_input_spec(spec: str) -> Dict[str, Tuple[int, int]]:
    """
    Parse public input spec of the form: v3:8=500,v4:4=0x10
    Returns mapping: name -> (size_bytes, value)
    """
    result: Dict[str, Tuple[int, int]] = {}
    if not spec:
        return result
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid public specification '{item}', expected name:bytes=val")
        name_part, v_str = item.split("=", 1)
        name_part = name_part.strip()
        if ":" not in name_part:
            raise ValueError(f"Invalid public specification '{item}', expected name:bytes=val")
        name, size_str = name_part.split(":", 1)
        name = name.strip()
        try:
            size = int(size_str, 0)
        except ValueError:
            raise ValueError(f"Invalid byte size in public specification '{item}'")
        if size <= 0:
            raise ValueError(f"Byte size must be positive in public specification '{item}'")
        val = int(v_str, 0)
        result[name] = (size, val)
    return result


def write_int_file(path: str, value: int, size: int) -> None:
    """Write an integer with given byte size (little-endian, signed) to path."""
    with open(path, "wb") as f:
        f.write(int(value).to_bytes(size, byteorder="little", signed=True))


def mode_input_values(executable: str, secret_spec: str, public_spec: str, timeout: int) -> int:
    """
    Mode --input:
      --secret v1:8=100/200,v2:4=300/400
      --public v3:8=500
    Creates temporary files for each variable and runs two traces:
      A: secrets(orig) + publics
      B: secrets(prime) + publics
    """
    require_tools(["gdb"])

    try:
        secrets = parse_secret_input_spec(secret_spec)
        publics = parse_public_input_spec(public_spec)
    except ValueError as e:
        print(f"Error parsing inputs: {e}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmpdir:
        files_run_a: List[str] = []
        files_run_b: List[str] = []

        # Secret variables: create orig and prime files; run A uses name, run B uses name__prime
        for name, (size, v_orig, v_prime) in secrets.items():
            path_orig = os.path.join(tmpdir, name)
            path_prime = os.path.join(tmpdir, f"{name}__prime")
            write_int_file(path_orig, v_orig, size)
            write_int_file(path_prime, v_prime, size)
            files_run_a.append(path_orig)
            files_run_b.append(path_prime)

        # Public variables: same file for both runs
        for name, (size, val) in publics.items():
            path_pub = os.path.join(tmpdir, name)
            write_int_file(path_pub, val, size)
            files_run_a.append(path_pub)
            files_run_b.append(path_pub)

        try:
            trace_a = run_gdb_trace(executable, files_run_a, timeout)
            trace_b = run_gdb_trace(executable, files_run_b, timeout)
        except subprocess.TimeoutExpired:
            print("Timeout while running gdb traces", file=sys.stderr)
            return 124

        analysis = analyze_traces(trace_a, trace_b)
        prev_addr = analysis["prev_addr"]
        pos = analysis["first_diff_index"]

        if prev_addr is None:
            print("Identical traces")
            return 1

        info = get_addr_info(executable, prev_addr)
        if info is None:
            print(f"Divergence after 0x{prev_addr:x}, ", end="")
            start_idx = (pos - 1) if (pos is not None and pos > 0) else 0
            print_nearest_debug_info(executable, trace_a, start_idx, prev_addr)
        else:
            f, l, c = info
            print(f"0x{prev_addr:x}: {f}:{l}:{c}")
        return 0


def build_parsers_and_dispatch(argv: List[str]) -> int:
    """CLI with mutually-exclusive modes: --json (batch), --file (.ktest), or --input (manual values)."""
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce divergence either from a dataframe (--json), "
            "a single .ktest (--file), or explicit values (--input)."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--json",
        dest="json_path",
        help="Path to combined dataframe JSON (batch mode).",
    )
    group.add_argument(
        "--file",
        dest="ktest_file",
        help="Path to a single KLEE .ktest file (e.g., branch_counterexample_<id>.ktest).",
    )
    group.add_argument(
        "--input",
        dest="input_mode",
        action="store_true",
        help=(
            "Manually supply inputs on the command line: "
            "--secret v1:8=100/200,v2:4=300/400 --public v3:8=500"
        ),
    )
    parser.add_argument(
        "--klee-output",
        dest="klee_output",
        help="Path to KLEE output directory (required with --json).",
    )
    parser.add_argument(
        "--executable",
        required=True,
        help="Path to the replay executable.",
    )
    parser.add_argument(
        "--secret",
        required=True,
        help=(
            "In --json/--file modes: comma-separated secret variable names.\n"
            "In --input mode: comma-separated name:bytes=orig/prime (e.g., v1:8=100/200)."
        ),
    )
    parser.add_argument(
        "--public",
        required=False,
        default="",
        help=(
            "In --json/--file modes: comma-separated public variable names.\n"
            "In --input mode: comma-separated name:bytes=value (e.g., v3:8=500)."
        ),
    )
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="Path to write output JSON with reproduced column (only with --json).",
    )
    parser.add_argument(
        "--timeout",
        required=False,
        default=60,
        type=int,
        help="Maximum time (in seconds) to allow for each replay (default: 60s).",
    )
    args = parser.parse_args(argv)

    if args.json_path:
        if not args.klee_output:
            parser.error("--klee-output is required when using --json")
        mode_dataframe(
            input_json=args.json_path,
            klee_output=args.klee_output,
            executable=args.executable,
            secret=args.secret,
            public=args.public,
            timeout=args.timeout,
            output=args.output,
        )
        return 0

    if args.ktest_file:
        return mode_ktest_file(
            executable=args.executable,
            ktest_file=args.ktest_file,
            secret=args.secret,
            public=args.public,
            timeout=args.timeout,
        )

    # --input mode
    return mode_input_values(
        executable=args.executable,
        secret_spec=args.secret,
        public_spec=args.public,
        timeout=args.timeout,
    )


def main():
    sys.exit(build_parsers_and_dispatch(sys.argv[1:]))


if __name__ == "__main__":
    main()
