#!/usr/bin/env python3

import pandas as pd
import json
import argparse

parser = argparse.ArgumentParser(description="Join CtChecker and KLEE output and generate an HTML report.")
parser.add_argument("ctchecker_output", help="Path to CtChecker output file (results_with_source-WL-FS-SRC-1.txt)")
parser.add_argument("klee_output", help="Path to KLEE visited_branches.json")
parser.add_argument("report_path", help="Path to save the output HTML report")
args = parser.parse_args()

data = []
with open(args.ctchecker_output, "r") as f:
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

df_ctchecker = pd.DataFrame(data)

with open(args.klee_output, "r") as f:
    data = json.load(f)

df_klee = pd.DataFrame(data["visited_branches"])
df_klee = df_klee[["filename", "line", "inst_id", "count", "both_count"]].rename(columns={"filename": "file"})

df = pd.merge(df_ctchecker, df_klee, on=["file", "line"], how="left")
df["inst_id"] = df["inst_id"].astype("Int64")
df["count"] = df["count"].fillna(0).astype("int64")
df["both_count"] = df["both_count"].fillna(0).astype("int64")
df = df.sort_values(
    by=["both_count", "count", "file", "line"],
    ascending=[False, True, True, True]
).reset_index()

def highlight_row(row):
    if row["both_count"] > 0:
        return ['background-color: lightgreen'] * len(row)
    elif row["count"] == 0:
        return ['background-color: lightcoral'] * len(row)
    else:
        return [''] * len(row)

styled = df.style.apply(highlight_row, axis=1)

styled.to_html(args.report_path, escape=False)
