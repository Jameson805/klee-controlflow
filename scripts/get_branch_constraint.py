#!/usr/bin/env python3
"""Extract merged branch constraints for a given instruction id from KLEE messages.txt.

Usage: get_branch_constraint.py <klee_output_dir> <output_txt_path> --instruction INST_ID [--select 1,2,3]

The script finds lines starting with "KLEE: [BRANCH]" in messages.txt under the given
KLEE output directory, filters entries whose outer "inst_id" equals the provided
--instruction value, groups entries by identical "constraints" lists (preserving order),
and writes a plain-text report with sections per distinct constraints-list.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Tuple


def parse_args():
    p = argparse.ArgumentParser(description="Extract merged branch constraints for an instruction")
    p.add_argument("klee_output_dir", help="Path to KLEE output directory (contains messages.txt)")
    p.add_argument("output_txt", help="Path to write the text report")
    p.add_argument("--instruction", required=True, type=int, help="Instruction id to examine (outer inst_id)")
    p.add_argument("--select", default=None, help="Comma-separated list of instruction ids to select from constraints (e.g. 1,2,3)")
    return p.parse_args()


def load_branch_lines(messages_path: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not os.path.exists(messages_path):
        raise FileNotFoundError(f"messages.txt not found at {messages_path}")

    with open(messages_path, "r") as f:
        for line in f:
            if not line.startswith("KLEE: [BRANCH]"):
                continue
            idx = line.find("{")
            if idx == -1:
                continue
            try:
                payload = json.loads(line[idx:])
            except json.JSONDecodeError:
                # skip malformed JSON
                continue
            entries.append(payload)
    return entries


def canonicalize_constraints_list(constraints: List[Dict[str, Any]]) -> Tuple[Tuple[int, str], ...]:
    """Turn a constraints list into a hashable canonical tuple preserving order.

    Each constraint dict is expected to have at least a "constraint" string and an "inst_id".
    We normalize missing fields conservatively.
    """
    canonical: List[Tuple[int, str]] = []
    for c in constraints:
        try:
            cid = int(c.get("inst_id")) if c.get("inst_id") is not None else -1
        except Exception:
            cid = -1
        constr = c.get("constraint") if c.get("constraint") is not None else ""
        canonical.append((cid, constr))
    return tuple(canonical)


def format_constraint_item(item: Tuple[int, str]) -> str:
    cid, constr = item
    return f"{cid}:\n{constr}"


def write_report(out_path: str, instruction: int, merged: "OrderedDict[Tuple[Tuple[int,str],...], Dict]", select_ids: List[int] | None):
    sep = "=" * 80
    with open(out_path, "w") as fo:
        fo.write(f"Instruction: {instruction}\n")
        fo.write(f"Distinct merged entries: {len(merged)}\n\n")

        for idx, (key, info) in enumerate(merged.items()):
            condition = info.get("condition", "")
            constraints_tuple: Tuple[Tuple[int, str], ...] = key

            # Condition section
            fo.write(sep + "\n")
            fo.write(f"{idx}: condition\n")
            fo.write(sep + "\n\n")
            # condition may contain newlines; write as-is
            fo.write(condition + "\n\n")

            # If select_ids provided, create selected and not_selected sections
            if select_ids is not None:
                selected = [c for c in constraints_tuple if c[0] in select_ids]
                not_selected = [c for c in constraints_tuple if c[0] not in select_ids]

                # selected
                fo.write(sep + "\n")
                fo.write(f"{idx}: selected\n")
                fo.write(sep + "\n\n")
                if selected:
                    for si in selected:
                        fo.write(format_constraint_item(si) + "\n\n")
                else:
                    fo.write("(none)\n\n")

                # not_selected
                fo.write(sep + "\n")
                fo.write(f"{idx}: not_selected\n")
                fo.write(sep + "\n\n")
                if not_selected:
                    for ni in not_selected:
                        fo.write(format_constraint_item(ni) + "\n\n")
                else:
                    fo.write("(none)\n\n")

            # all_constraints
            fo.write(sep + "\n")
            fo.write(f"{idx}: all_constraints\n")
            fo.write(sep + "\n\n")
            if constraints_tuple:
                for ai in constraints_tuple:
                    fo.write(format_constraint_item(ai) + "\n\n")
            else:
                fo.write("(none)\n\n")


def main():
    args = parse_args()
    messages_path = os.path.join(args.klee_output_dir, "messages.txt")
    try:
        entries = load_branch_lines(messages_path)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    # Filter entries by outer inst_id matching the requested instruction
    filtered = []
    for e in entries:
        inst = e.get("inst_id")
        try:
            if inst is None:
                continue
            if int(inst) == int(args.instruction):
                filtered.append(e)
        except Exception:
            continue

    # Group by identical constraints list (canonicalized tuple). Preserve first-seen condition.
    merged: "OrderedDict[Tuple[Tuple[int,str],...], Dict]" = OrderedDict()
    for e in filtered:
        constraints = e.get("constraints") or []
        key = canonicalize_constraints_list(constraints)
        if key not in merged:
            merged[key] = {"condition": e.get("condition", "")}
        # else: already present, nothing else to collect for now

    # Parse select ids if provided
    select_ids = None
    if args.select:
        select_ids = []
        for token in args.select.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                select_ids.append(int(token))
            except ValueError:
                print(f"Warning: ignoring invalid select id '{token}'", file=sys.stderr)

    # Write the report
    write_report(args.output_txt, int(args.instruction), merged, select_ids)


if __name__ == "__main__":
    main()
