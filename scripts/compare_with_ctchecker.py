#!/usr/bin/env python3

import pandas as pd
import numpy as np
import argparse
import os
import json
import subprocess
import sys
import shutil

from common import save_combined_json

parser = argparse.ArgumentParser(description="Join CtChecker and KLEE output and save combined data to JSON.")
parser.add_argument("ct_type", choices=["branch", "memory"], help="Type of constant-time check: 'branch' or 'memory'")
parser.add_argument("ctchecker_output", help="Path to CtChecker output file (results_with_source-WL-FS-SRC-1.txt)")
parser.add_argument("klee_output", help="Path to KLEE output directory")
parser.add_argument("output_path", help="Path to save the combined dataframe in JSON format")
parser.add_argument("--code-path", default="", help="Path to the source code for the filenames in the KLEE output (defaults to empty string)")
parser.add_argument("--filename", default="", help="Filename to filter (e.g., main.c)")
parser.add_argument("--lines", default="", help="Line number range to filter (e.g., 100:200)")
parser.add_argument(
    "--src-prefix",
    default="",
    help="If set, keep only KLEE rows whose filename starts with this prefix and strip the prefix from the filename (e.g., 'crypto/bn' makes 'crypto/bn/bn_exp.c' -> 'bn_exp.c')."
)
parser.add_argument(
    "--ctchecker-prefix",
    default="",
    help="If set, prepend this prefix to every filename in the CtChecker output."
)
parser.add_argument("--secret", default="", help="Comma-separated list of secret variable names (e.g., key)")
parser.add_argument("--public", default="", help="Comma-separated list of public variable names (e.g., length,nonce)")
args = parser.parse_args()

def parse_list(s: str):
    return [p.strip() for p in s.split(",") if p and p.strip()]

def require_tools(tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        print(f"Error: required tools not found on PATH: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

def load_ctchecker(ct_type, path, prefix=""):
    with open(path, "r") as f:
        data = json.load(f)
    key = "branches" if ct_type == "branch" else "indices"
    df = pd.DataFrame(data.get(key, []))
    df["filename"] = df["filename"].apply(lambda x: os.path.join(prefix, x))
    return df

df_ctchecker = load_ctchecker(args.ct_type, args.ctchecker_output, args.ctchecker_prefix)

def load_preaggregated_from_messages(path, tag, code_path_prefix=""):
    """
    Parse KLEE messages.txt entries tagged as [tag] that already contain aggregated data.
    Each entry is expected to carry visit/non-constant-time counters and timing information.
    """
    entries = []
    with open(path, "r") as f:
        for line in f:
            if not line.startswith(f"KLEE: [{tag}]"):
                continue
            idx = line.find("{")
            if idx == -1:
                continue
            try:
                payload = json.loads(line[idx:])
            except json.JSONDecodeError:
                continue
            try:
                inst_id = int(payload.get("inst_id"))
            except (TypeError, ValueError):
                continue

            def to_int(value):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return np.nan

            def to_float(value):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return np.nan

            entries.append({
                "filename": payload.get("filename"),
                "line": to_int(payload.get("line")),
                "column": to_int(payload.get("col")),
                "inst_id": inst_id,
                "visit_count": to_int(payload.get("visit_count")),
                "non_ct_count": to_int(payload.get("non_ct_count")),
                "visit_time": to_float(payload.get("visit_time")),
                "non_ct_time": to_float(payload.get("non_ct_time"))
            })

    columns = ["filename", "line", "column", "inst_id", "visit_count", "non_ct_count", "visit_time", "non_ct_time"]
    if not entries:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(entries, columns=columns)
    df["inst_id"] = pd.to_numeric(df["inst_id"], errors="coerce").astype("Int64")
    for col in ["line", "column", "visit_count", "non_ct_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ["visit_time", "non_ct_time"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.drop_duplicates(subset=["inst_id"], keep="first")

    return df

# Build df_klee from messages.txt based on ct_type
if args.ct_type == "branch":
    df_klee = load_preaggregated_from_messages(os.path.join(args.klee_output, "messages.txt"), "BRANCH", args.code_path)
else:
    df_klee = load_preaggregated_from_messages(os.path.join(args.klee_output, "messages.txt"), "MEMORY", args.code_path)

# Optionally filter and normalize KLEE filenames by a source prefix
if args.src_prefix:
    pref_parts = [p for p in os.path.normpath(args.src_prefix).split(os.sep) if p not in ("", ".")]

    def _split_parts(name):
        if not isinstance(name, str):
            return None
        return [p for p in os.path.normpath(name).split(os.sep) if p not in ("", ".")]

    def _find_subseq(parts, subseq):
        if parts is None or not subseq:
            return -1
        n, m = len(parts), len(subseq)
        if m > n:
            return -1
        for i in range(n - m + 1):
            if parts[i:i + m] == subseq:
                return i
        return -1

    def _has_prefix(name):
        parts = _split_parts(name)
        return _find_subseq(parts, pref_parts) != -1

    def _strip_prefix(name):
        parts = _split_parts(name)
        idx = _find_subseq(parts, pref_parts)
        if idx == -1:
            return name
        rest = parts[idx + len(pref_parts):]
        return os.path.join(*rest) if rest else ""

    if not df_klee.empty and "filename" in df_klee.columns:
        mask = df_klee["filename"].apply(_has_prefix)
        df_klee = df_klee[mask].copy()
        df_klee["filename"] = df_klee["filename"].apply(_strip_prefix)

# Join all the positives reported by CtChecker
df_joined = df_ctchecker.merge(
    df_klee,
    on=["filename", "line", "column"],
    how="left",
    indicator=True
)
# Fill missing counts with 0 for entries that came from ctchecker only (avoid FutureWarning by ensuring numeric dtype first)
df_joined["visit_count"] = pd.to_numeric(df_joined["visit_count"], errors="coerce").fillna(0).astype("int64")
df_joined["non_ct_count"] = pd.to_numeric(df_joined["non_ct_count"], errors="coerce").fillna(0).astype("int64")
df_joined["in_ctchecker"] = df_joined["_merge"].apply(lambda x: x in ["both", "left_only"])
df_joined = df_joined.drop(columns="_merge")

# Find KLEE-only entries: those KLEE aggregated entries that have non_ct_count > 0 but are not in ctchecker
df_klee_filtered = df_klee[df_klee["non_ct_count"] > 0]
df_klee_only = df_klee_filtered.merge(
    df_ctchecker,
    on=["filename", "line", "column"],
    how="left",
    indicator=True
)
df_klee_only = df_klee_only[df_klee_only["_merge"] == "left_only"].drop(columns="_merge")
df_klee_only["in_ctchecker"] = False

df = pd.concat([df_joined, df_klee_only], ignore_index=True)

def get_code(code_path, filenames, lines):
    def get_line(filename, line_number):
        try:
            with open(filename, "r") as f:
                for current, line in enumerate(f, start=1):
                    if current == line_number:
                        return line.rstrip("\n")
            return None
        except (FileNotFoundError, IOError):
            return None

    return [get_line(os.path.join(code_path, f), l) for f, l in zip(filenames, lines)]

if args.code_path:
    df["code"] = get_code(args.code_path, df["filename"], df["line"])

if args.lines:
    line_range = args.lines.split(":")
    assert len(line_range) == 2, "Lines argument must be in the format start:end"
    start = int(line_range[0])
    end = int(line_range[1])
    df = df[(df["line"] >= start) & (df["line"] <= end)]

if args.filename:
    df = df[df["filename"] == args.filename]

def extract_counterexamples(df: pd.DataFrame, args, secrets, publics):
    """
    For rows with non_ct_count > 0 and inst_id present, extract variables
    from ktest files and store them as integers (machine endian) in df['counterexamples'].
    """
    if "counterexamples" not in df.columns:
        # Create the column with proper length so .at assignments work without KeyError
        df["counterexamples"] = [None] * len(df)

    require_tools(["ktest-tool"])
    prefix = "branch" if args.ct_type == "branch" else "memory"

    def int_from_file(path: str):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if not data:
                return 0
            return int.from_bytes(data, byteorder=sys.byteorder, signed=False)
        except FileNotFoundError as e:
            print(f"[counterexamples] File not found: {path} ({e})", file=sys.stderr)
            return None
        except OSError as e:
            print(f"[counterexamples] OS error reading {path}: {e}", file=sys.stderr)
            return None

    def extract_var(ktest_file: str, var: str) -> bool:
        try:
            subprocess.run(
                ["ktest-tool", "--extract", var, ktest_file],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"[counterexamples] ktest-tool failed extracting '{var}' from {ktest_file}: {e}", file=sys.stderr)
            return False

    df["non_ct_count"] = pd.to_numeric(df["non_ct_count"], errors="coerce").fillna(0).astype("int64")
    if "inst_id" not in df.columns:
        print("[counterexamples] inst_id column missing; skipping extraction", file=sys.stderr)
        return df

    mask = (df["non_ct_count"] > 0) & df["inst_id"].notna()
    for idx, row in df[mask].iterrows():
        try:
            inst_id = int(row["inst_id"])
        except (TypeError, ValueError) as e:
            print(f"[counterexamples] Invalid inst_id '{row['inst_id']}' at index {idx}: {e}", file=sys.stderr)
            continue

        ktest_file = os.path.join(args.klee_output, f"{prefix}_counterexample_{inst_id}.ktest")
        if not os.path.exists(ktest_file):
            print(f"[counterexamples] Missing ktest file: {ktest_file}", file=sys.stderr)
            continue

        ce = {}
        for var in publics:
            if extract_var(ktest_file, var):
                val = int_from_file(f"{ktest_file}.{var}")
                if val is not None:
                    ce[var] = val

        for var in secrets:
            if extract_var(ktest_file, var):
                valb = int_from_file(f"{ktest_file}.{var}")
                if valb is not None:
                    ce[var] = valb
            prime_variants = [f"{var}__prime", f"{var}_prime"]
            for pv in prime_variants:
                if extract_var(ktest_file, pv):
                    valp = int_from_file(f"{ktest_file}.{pv}")
                    if valp is not None:
                        ce[pv] = valp
                    break
            else:
                print(f"[counterexamples] Could not extract prime variant for secret '{var}' in {ktest_file}", file=sys.stderr)

        if ce:
            df.at[idx, "counterexamples"] = ce

    return df

secrets = parse_list(args.secret)
publics = parse_list(args.public)

if secrets or publics:
    df = extract_counterexamples(df, args, secrets, publics)

out_dir = os.path.dirname(args.output_path)
if out_dir:
    os.makedirs(out_dir, exist_ok=True)

save_combined_json(df, args.output_path)
