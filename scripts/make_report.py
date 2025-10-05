#!/usr/bin/env python3

import pandas as pd
import argparse
import os

from common import load_combined_json

parser = argparse.ArgumentParser(description="Generate HTML report from combined CtChecker/KLEE JSON output.")
parser.add_argument("input_json", help="Path to combined dataframe JSON (records orient)")
parser.add_argument("report_path", help="Path to save the output HTML report")
args = parser.parse_args()

def make_report_from_json(input_json, report_path):
    df = load_combined_json(input_json)

    # Ensure expected columns exist
    if "in_ctchecker" not in df.columns:
        df["in_ctchecker"] = True

    df = df.sort_values(
        by=["non_ct_count", "filename", "line", "column"],
        ascending=[False, True, True, True]
    ).reset_index(drop=True)
    in_ctchecker_series = df["in_ctchecker"]
    df_to_report = df.drop(columns=["in_ctchecker"]) if "in_ctchecker" in df.columns else df

    def highlight_row(row):
        if not in_ctchecker_series[row.name]:
            return ["background-color: lightsalmon"] * len(row)
        elif row.get("non_ct_count", 0) > 0:
            return ["background-color: lightgreen"] * len(row)
        elif row.get("visit_count", 0) == 0:
            return ["background-color: lightcoral"] * len(row)
        else:
            return [""] * len(row)

    styled = df_to_report.style.apply(highlight_row, axis=1)

    out_dir = os.path.dirname(report_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    styled.to_html(report_path, escape=False, na_rep="")

if __name__ == "__main__":
    make_report_from_json(args.input_json, args.report_path)
