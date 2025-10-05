#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from typing import List, Dict, Any

import pandas as pd
import shutil

from common import load_combined_json, save_combined_json
from addrinfo import get_addr_info

script_dir = os.path.dirname(os.path.abspath(__file__))

def main():
    parser = argparse.ArgumentParser(
        description="Extract secret/public inputs from KLEE counterexample ktest files"
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
    args = parser.parse_args()

    required_tools = ["ktest-tool", "gdb"]
    missing = [t for t in required_tools if shutil.which(t) is None]
    if missing:
        print(f"Error: required tools not found on PATH: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

    def parse_var_list(s: str) -> List[str]:
        # split a comma-separated list and ignore empty entries/spaces
        return [p.strip() for p in s.split(",") if p and p.strip()]
    secrets = parse_var_list(args.secret)
    publics = parse_var_list(args.public)

    df = load_combined_json(args.input_json)

    df["reproduced"] = pd.NA

    for idx, row in df[df["non_ct_count"] > 0].iterrows():
        print(f"Reproducing {row['filename']}:{row['line']}:{row['column']} ...", end="", flush=True)
        ktest_file = os.path.join(args.klee_output, f"branch_counterexample_{row['inst_id']}.ktest")

        def extract_var(var):
            cmd = ["ktest-tool", "--extract", var, ktest_file]
            proc = subprocess.run(cmd, capture_output=True)

        for var in publics:
            extract_var(var)
        for var in secrets:
            extract_var(var)
            extract_var(f"{var}__prime")

        def run(vars):
            script = os.path.join(script_dir, "trace.gdb")
            var_files = [ktest_file + f".{v}" for v in vars]
            cmd = ["gdb", "-batch", "-x", script, "--args", args.executable] + var_files
            proc = subprocess.run(cmd, capture_output=True, text=True)
            return proc.stdout

        trace = run(secrets + publics)
        trace_prime = run([f"{v}__prime" for v in secrets] + publics)

        def get_diverging_addr():
            """compare line-by-line return the line before the first differing line"""
            lines = trace.splitlines()
            lines_p = trace_prime.splitlines()

            max_len = max(len(lines), len(lines_p))
            for i in range(max_len):
                a = lines[i] if i < len(lines) else None
                b = lines_p[i] if i < len(lines_p) else None
                if a != b:
                    if i - 1 < 0:
                        return None
                    else:
                        return int(lines[i - 1], 16)
            return None

        info = get_addr_info(args.executable, get_diverging_addr())
        if info is None:
            print("Failed to get debug info")
            df.at[idx, "reproduced"] = False
        else:
            file, line, col = info
            if (row["filename"] == file and row["line"] == line and row["column"] == col):
                print("Success")
                df.at[idx, "reproduced"] = True
            else:
                print(f"Mismatch with {file}:{line}:{col}")
                df.at[idx, "reproduced"] = False

    if args.output:
        save_combined_json(df, args.output)


if __name__ == "__main__":
    main()
