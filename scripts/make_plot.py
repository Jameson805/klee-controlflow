#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
import os

parser = argparse.ArgumentParser(description="Generate time-vulnerabilities plot from combined CtChecker/KLEE JSON output.")
parser.add_argument("input_json", help="Path to combined dataframe JSON (records orient)")
parser.add_argument("program_name", help="Name of the program analyzed")
parser.add_argument("plot_path", help="Path to save the output plot image")
args = parser.parse_args()

def make_time_vulnerabilities_plot_from_json(input_json, name, path):
    df = pd.read_json(input_json, orient="records")

    # Drop missing visit times
    visited_times = df.get("visit_time", pd.Series([], dtype=float)).dropna().sort_values().to_numpy()
    confirmed_times = df.get("non_ct_time", pd.Series([], dtype=float)).dropna().sort_values().to_numpy()

    total_vulnerabilities = len(df)

    # Time axis: combine all interesting timepoints
    if visited_times.size + confirmed_times.size > 0:
        time_axis = np.unique(np.concatenate([visited_times, confirmed_times]))
    else:
        time_axis = np.array([0.0])

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

    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    plt.savefig(path, dpi=300, bbox_inches="tight")

if __name__ == "__main__":
    make_time_vulnerabilities_plot_from_json(args.input_json, args.program_name, args.plot_path)
