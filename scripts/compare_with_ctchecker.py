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
args = parser.parse_args()

def load_ctchecker(path):
    data = []
    with open(path, "r") as f:
        for line in f:
            # Split at " line " to separate file and line number + code
            if " line " in line:
                file_part, rest = line.strip().split(" line ", 1)
                if " - " in rest:
                    line_num, code = rest.split(" - ", 1)
                    data.append({
                        "file": file_part.strip(),
                        "line": int(line_num.strip()),
                        "code": code.strip()
                    })
    return pd.DataFrame(data)

df_ctchecker = load_ctchecker(args.ctchecker_output)

def load_visited_branches(path):
    with open(path, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["visited_branches"])
    df = df[["filename", "line", "inst_id", "count", "both_count"]].rename(columns={"filename": "file"})
    return df

df_klee = load_visited_branches(os.path.join(args.klee_output, "visited_branches.json"))

# Join all the positives reported either by CtChecker or KLEE
df_joined = pd.merge(df_ctchecker, df_klee, on=["file", "line"], how="left")
df_klee_filtered = df_klee[df_klee["both_count"] > 0]
df_klee_only = df_klee_filtered.merge(df_ctchecker, on=["file", "line"], how="left", indicator=True)
df_klee_only = df_klee_only[df_klee_only["_merge"] == "left_only"].drop(columns="_merge")
df = pd.concat([df_joined, df_klee_only], ignore_index=True)

df["inst_id"] = df["inst_id"].astype("Int64")
df["count"] = df["count"].fillna(0).astype("int64")
df["both_count"] = df["both_count"].fillna(0).astype("int64")

def load_messages(path):
    branch_pat = re.compile(r"^KLEE: \[BRANCH\]\s+([\d\.]+)\s*:\s*(\d+)")
    nonct_pat = re.compile(r"^KLEE: \[NON-CT BRANCH\]\s+([\d\.]+)\s*:\s*(\d+)")

    branch_data = []
    nonct_data = []

    with open(path, "r") as f:
        for line in f:
            if line.startswith("KLEE: [BRANCH]"):
                m = branch_pat.search(line)
                if m:
                    branch_data.append({
                        "inst_id": int(m.group(2)),
                        "visit_time": float(m.group(1))
                    })
            elif line.startswith("KLEE: [NON-CT BRANCH]"):
                m = nonct_pat.search(line)
                if m:
                    nonct_data.append({
                        "inst_id": int(m.group(2)),
                        "both_time": float(m.group(1))
                    })

    df_branch = pd.DataFrame(branch_data, columns=["inst_id", "visit_time"])
    df_nonct = pd.DataFrame(nonct_data, columns=["inst_id", "both_time"])
    df = pd.merge(df_branch, df_nonct, on="inst_id", how="left")
    df["visit_time"] = df["visit_time"].astype(float)
    df["both_time"] = df["both_time"].astype(float)
    return df

df_time = load_messages(os.path.join(args.klee_output, "messages.txt"))
df = pd.merge(df, df_time, on="inst_id", how="left")

df.reset_index(drop=True, inplace=True)

def make_report(df_in, path):
    df = df_in.copy()
    df = df.sort_values(
        by=["both_count", "count", "file", "line"],
        ascending=[False, True, True, True]
    )
    df["code"] = df["code"].fillna("")

    def highlight_row(row):
        if row["code"] == "":
            return ["background-color: lightsalmon"] * len(row)
        elif row["both_count"] > 0:
            return ["background-color: lightgreen"] * len(row)
        elif row["count"] == 0:
            return ["background-color: lightcoral"] * len(row)
        else:
            return [""] * len(row)

    styled = df.style.apply(highlight_row, axis=1)
    styled.to_html(path, escape=False, na_rep="")

make_report(df, args.report_path)

def make_time_vulnerabilities_plot(df, name, path):
    # Drop missing visit times
    visited_times = df["visit_time"].dropna().sort_values().to_numpy()
    confirmed_times = df["both_time"].dropna().sort_values().to_numpy()

    total_vulnerabilities = len(df)

    # Time axis: combine all interesting timepoints
    time_axis = np.unique(np.concatenate([visited_times, confirmed_times]))
    
    visited_counts = []
    confirmed_counts = []

    for t in time_axis:
        visited_counts.append(np.sum(visited_times <= t))
        confirmed_counts.append(np.sum(confirmed_times <= t))

    # Plot
    plt.figure(figsize=(8, 5))
    plt.plot(time_axis, visited_counts, marker="o", linestyle="-", color="b", label="Visited Vulnerabilities")
    plt.plot(time_axis, confirmed_counts, marker="o", linestyle="-", color="g", label="Confirmed Vulnerabilities")
    plt.axhline(y=total_vulnerabilities, color="r", linestyle="--", label=f"Total Vulnerabilities ({total_vulnerabilities})")

    plt.xlabel("Time (seconds)")
    plt.ylabel("Number of Vulnerabilities")
    plt.yticks(range(0, total_vulnerabilities + 1, max(1, total_vulnerabilities // 10)))
    plt.title(name + " Vulnerabilities Over Time")
    plt.legend()
    plt.grid(True, which="both", linestyle="--", linewidth=0.5)
    plt.savefig(path, dpi=300, bbox_inches="tight")

make_time_vulnerabilities_plot(df, args.program_name, args.plot_path)