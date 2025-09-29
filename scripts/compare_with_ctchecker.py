#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
import os
import re
import json

parser = argparse.ArgumentParser(description="Join CtChecker and KLEE output and generate an HTML report.")
parser.add_argument("ctchecker_output", help="Path to CtChecker output file (results_with_source-WL-FS-SRC-1.txt)")
parser.add_argument("klee_output", help="Path to KLEE output directory")
parser.add_argument("report_path", help="Path to save the output HTML report")
parser.add_argument("plot_path", help="Path to save the output plot image")
parser.add_argument("program_name", help="Name of the program analyzed")
parser.add_argument("--ctchecker-prefix", default="", help="Prefix to the filenames in the CtChecker output (defaults to empty string)")
parser.add_argument("--code-path", default="", help="Path to the source code for the filenames in the KLEE output (defaults to empty string)")
parser.add_argument("--lines", default="", help="Line number range to filter (e.g., 100:200)")
args = parser.parse_args()

def load_ctchecker(path, prefix):
    with open(path, "r") as f:
        data = json.load(f)
    df = pd.DataFrame(data["branches"])
    df["filename"] = df["filename"].apply(lambda f: os.path.join(prefix, f))
    return df

df_ctchecker = load_ctchecker(args.ctchecker_output, args.ctchecker_prefix)

def load_and_aggregate_branches_from_messages(path, code_path_prefix=""):
    """
    Parse messages.txt lines like:
    KLEE: [BRANCH] {"col":17,"condition":"...","filename":"klee-example.c","inst_id":27,"line":13,"non_ct":true,"time":0.1}
    The only mandatory fields are "inst_id" and "non_ct"; other fields may be missing.
    Aggregate by inst_id:
      - visit_count: total number of entries for that inst_id
      - non_ct_count: number of entries with non_ct == True
      - visit_time: minimum time among all entries (NaN if none)
      - non_ct_time: minimum time among entries with non_ct == True (NaN if none)
    Returns a DataFrame with columns:
      filename, line, column, inst_id, visit_count, non_ct_count, visit_time, non_ct_time
    """
    branch_entries = []
    with open(path, "r") as f:
        for line in f:
            if not line.startswith("KLEE: [BRANCH]"):
                continue
            idx = line.find("{")
            if idx == -1:
                continue
            try:
                payload = json.loads(line[idx:])
            except json.JSONDecodeError:
                continue
            # inst_id is mandatory; skip if missing or invalid
            inst_id = payload.get("inst_id")
            if inst_id is None:
                continue
            try:
                inst_id = int(inst_id)
            except Exception:
                continue
            non_ct = bool(payload.get("non_ct", False))
            filename = payload.get("filename")
            raw_line = payload.get("line")
            raw_col = payload.get("col")
            raw_time = payload.get("time")

            # Normalize optional numeric fields; use NaN when missing/invalid
            try:
                line_no = int(raw_line) if raw_line is not None else np.nan
            except Exception:
                line_no = np.nan
            try:
                col = int(raw_col) if raw_col is not None else np.nan
            except Exception:
                col = np.nan
            try:
                time_val = float(raw_time) if raw_time is not None else np.nan
            except Exception:
                time_val = np.nan

            branch_entries.append({
                "inst_id": inst_id,
                "filename": filename,
                "line": line_no,
                "column": col,
                "time": time_val,
                "non_ct": non_ct
            })

    if not branch_entries:
        return pd.DataFrame(columns=["filename", "line", "column", "inst_id", "visit_count", "non_ct_count", "visit_time", "non_ct_time"])

    df_be = pd.DataFrame(branch_entries)

    # Aggregate by inst_id. Keep first non-missing filename/line/column when available.
    def first_non_na(series):
        s = series.dropna()
        return s.iloc[0] if not s.empty else (None if series.name == "filename" else np.nan)

    def min_time_ignore_na(t):
        t2 = t.dropna()
        return float(t2.min()) if not t2.empty else np.nan

    # For non_ct_time we need min time among rows where non_ct is True
    def min_time_for_nonct(t):
        mask = df_be.loc[t.index, "non_ct"] & t.notna()
        if mask.any():
            return float(t[mask].min())
        return np.nan

    agg = df_be.groupby("inst_id").agg(
        filename=pd.NamedAgg(column="filename", aggfunc=first_non_na),
        line=pd.NamedAgg(column="line", aggfunc=first_non_na),
        column=pd.NamedAgg(column="column", aggfunc=first_non_na),
        visit_count=pd.NamedAgg(column="inst_id", aggfunc="count"),
        non_ct_count=pd.NamedAgg(column="non_ct", aggfunc=lambda s: int(s.sum())),
        visit_time=pd.NamedAgg(column="time", aggfunc=min_time_ignore_na),
        non_ct_time=pd.NamedAgg(column="time", aggfunc=min_time_for_nonct)
    ).reset_index()

    # Ensure dtypes
    agg["inst_id"] = agg["inst_id"].astype("Int64")
    agg["visit_count"] = agg["visit_count"].astype("int64")
    agg["non_ct_count"] = agg["non_ct_count"].astype("int64")
    agg["visit_time"] = agg["visit_time"].astype(float)
    agg["non_ct_time"] = agg["non_ct_time"].astype(float)

    return agg

# Build df_klee from messages.txt instead of visited_branches.json
df_klee = load_and_aggregate_branches_from_messages(os.path.join(args.klee_output, "messages.txt"), args.code_path)

# Join all the positives reported by CtChecker
df_joined = df_ctchecker.merge(
    df_klee,
    on=["filename", "line", "column"],
    how="left",
    indicator=True
)
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

df["inst_id"] = df["inst_id"].astype("Int64")
# Fill missing counts with 0 for entries that came from ctchecker only
df["visit_count"] = df["visit_count"].fillna(0).astype("int64")
df["non_ct_count"] = df["non_ct_count"].fillna(0).astype("int64")
# visit_time / non_ct_time may be NaN if missing; keep as floats

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

def make_report(df_in, path):
    df = df_in.copy()
    df = df.sort_values(
        by=["non_ct_count", "filename", "line", "column"],
        ascending=[False, True, True, True]
    ).reset_index(drop=True)
    in_ctchecker_series = df["in_ctchecker"]
    df_to_report = df.drop(columns=["in_ctchecker"])

    def highlight_row(row):
        if not in_ctchecker_series[row.name]:
            return ["background-color: lightsalmon"] * len(row)
        elif row["non_ct_count"] > 0:
            return ["background-color: lightgreen"] * len(row)
        elif row["visit_count"] == 0:
            return ["background-color: lightcoral"] * len(row)
        else:
            return [""] * len(row)

    styled = df_to_report.style.apply(highlight_row, axis=1)
    styled.to_html(path, escape=False, na_rep="")

make_report(df, args.report_path)

def make_time_vulnerabilities_plot(df, name, path):
    # Drop missing visit times
    visited_times = df["visit_time"].dropna().sort_values().to_numpy()
    confirmed_times = df["non_ct_time"].dropna().sort_values().to_numpy()

    total_vulnerabilities = len(df)

    # Time axis: combine all interesting timepoints
    time_axis = np.unique(np.concatenate([visited_times, confirmed_times])) if (visited_times.size + confirmed_times.size) > 0 else np.array([0.0])

    visited_counts = []
    confirmed_counts = []

    for t in time_axis:
        visited_counts.append(np.sum(visited_times <= t))
        confirmed_counts.append(np.sum(confirmed_times <= t))

    # Plot
    plt.figure(figsize=(8, 5))
    plt.plot(time_axis, visited_counts, marker="o", linestyle="-", color="b", label=f"Visited ({visited_counts[-1] if visited_counts else 0})")
    plt.plot(time_axis, confirmed_counts, marker="o", linestyle="-", color="g", label=f"Confirmed ({confirmed_counts[-1] if confirmed_counts else 0})")
    plt.axhline(y=total_vulnerabilities, color="r", linestyle="--", label=f"Total ({total_vulnerabilities})")

    plt.xlabel("Time (seconds)")
    plt.ylabel("Number of Vulnerabilities")
    plt.yticks(range(0, total_vulnerabilities + 1, max(1, total_vulnerabilities // 10)))
    plt.title(name + " Vulnerabilities Over Time")
    plt.legend()
    plt.grid(True, which="both", linestyle="--", linewidth=0.5)
    plt.savefig(path, dpi=300, bbox_inches="tight")

make_time_vulnerabilities_plot(df, args.program_name, args.plot_path)