"""
Run SVF-SVC on all the SV-COMP cases locally.

Note that this doesn't follow the benchexec script or any other
definitions and will probably break if the names of things are
changed later. It exists in a "it works on my machine" state.

This script also doesn't check the type of violation returned.

The goal is to run SVF-SVC and gauge effectiveness changes.
CSV file output.
"""

import argparse
import csv
from collections import Counter
from enum import Enum, auto
import glob
import subprocess
import sys
from typing import Tuple
import os
import yaml

# Simple checks for output result.
TRUE_PATTERN = b"Correct"
FALSE_PATTERN = b"Incorrect"
UNKNOWN_PATTERN = b"Unknown"
ERROR_PATTERN = b"Error"

class VERDICT(Enum):
    TRUE = auto()
    FALSE = auto()
    UNKNOWN = auto()
    ERROR = auto()
    MULTIPLE_INPUTS = auto()

    # SVF's result, expected result
    TRUE_CORRECT = auto()
    TRUE_INCORRECT = auto()
    FALSE_CORRECT = auto()
    FALSE_INCORRECT = auto()

def interpret_output(stdout) -> VERDICT:
    if TRUE_PATTERN in stdout:
        return VERDICT.TRUE
    if FALSE_PATTERN in stdout:
        return VERDICT.FALSE
    if UNKNOWN_PATTERN in stdout:
        return VERDICT.UNKNOWN
    return VERDICT.ERROR

def run_prop(prop_file, definition, args) -> VERDICT:
    if isinstance(definition["input_files"], list) and len(definition["input_files"]) > 1:
        # SVF can only handle one input file.
        return VERDICT.MULTIPLE_INPUTS

    c_file = definition["input_files"]
    svf_run = os.path.normpath(os.path.join(args.svf_root, "svf_run.py"))
    command = [svf_run, c_file, "--prop", prop_file, "--witness", ""]

    if args.verbose:
        # This produces a LOT of output.
        #command.append("-v")
        stderr = sys.stderr
    else:
        stderr = subprocess.PIPE

    process = subprocess.run(command, cwd=".", stdout=subprocess.PIPE, stderr=stderr)

    return interpret_output(process.stdout)

def run_yaml(yaml_path: str, args) -> Tuple[dict[str, VERDICT], str]:
    """Returns results and total."""
    with open(yaml_path) as f:
        definition = yaml.safe_load(f)
    os.chdir(os.path.dirname(yaml_path))

    output = dict()

    for prop in definition["properties"]:
        prop_file = prop["property_file"]
        if (
            (args.reach and "unreach-call.prp" in prop_file)
            or (args.safety and "valid-memsafety.prp" in prop_file)
            or (args.cleanup and "valid-memcleanup.prp" in prop_file)
            or (args.overflow and "no-overflow.prp" in prop_file)
            ):
            verdict = run_prop(prop_file, definition, args)
        else:
            # Unsupported property
            continue

        if verdict == VERDICT.MULTIPLE_INPUTS:
            # SVF cannot handle multiple input files.
            continue
        elif verdict == VERDICT.TRUE and prop["expected_verdict"] == True:
            output[prop_file] = VERDICT.TRUE_CORRECT
        elif verdict == VERDICT.TRUE and prop["expected_verdict"] == False:
            output[prop_file] = VERDICT.TRUE_INCORRECT
        elif verdict == VERDICT.FALSE and prop["expected_verdict"] == False:
            output[prop_file] = VERDICT.FALSE_CORRECT
        elif verdict == VERDICT.FALSE and prop["expected_verdict"] == True:
            output[prop_file] = VERDICT.FALSE_INCORRECT
        else:
            # ERROR or UNKNOWN
            output[prop_file] = verdict

    return output, yaml_path

def compute_results(results, args):
    # results is a list of dicts
    header = ["name", "T/C", "T/W", "F/C", "F/W", "U", "E", "M"]
    rows = []
    totals = Counter()
    for output, name in results:
        row = [name]
        row_count = Counter()
        for v in output.values():
            row_count[v] += 1

        for col in [VERDICT.TRUE_CORRECT, VERDICT.TRUE_INCORRECT, VERDICT.FALSE_CORRECT, VERDICT.FALSE_INCORRECT, VERDICT.UNKNOWN, VERDICT.ERROR, VERDICT.MULTIPLE_INPUTS]:
            row.append(row_count.get(col, 0))

        rows.append(row)
        totals.update(row_count)

    for k,v in totals.items():
        print(f"{k.name:<17}: {v:>5}")

    if args.output is None:
        # No output file requested.
        return
    with open(args.output, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(rows)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bench_root", help="root directory of benchmarks, absolute path only")
    parser.add_argument("svf_root", help="root directory of SVF-SVC, absolute path only")

    parser.add_argument("--version", action="version", version="1.0")
    parser.add_argument("--reach", action="store_true", help="Enable reachability")
    parser.add_argument("--safety", action="store_true", help="Enable memory safety")
    parser.add_argument("--cleanup", action="store_true", help="Enable memory cleanup")
    parser.add_argument("--overflow", action="store_true", help="Enable overflow detection")
    parser.add_argument("--specific", help="use specific benchmark inside bench root", default=None)

    parser.add_argument("--output", default=None, help="CSV output")

    parser.add_argument("--verbose", "-v", action="store_true")

    args, extra = parser.parse_known_args()
    if args.verbose:
        print(f"Arguments: {args}")
        print(f"Extra (unused) arguments: {extra}")

    results = []

    original_cwd = os.path.abspath(".")
    os.chdir(args.bench_root)
    for bench in glob.glob("c/**/*.yml", recursive=True):
        if "witness" in bench:
            # Pretty broad hammer to ignore witness files.
            continue
        if args.specific is not None and args.specific not in bench:
            # Specific bench specified and doesn't match.
            continue
        if args.verbose:
            print(bench)
        os.chdir(args.bench_root)
        results.append(run_yaml(bench, args))
        if args.verbose:
            print(results[-1])

    os.chdir(original_cwd)
    compute_results(results, args)
