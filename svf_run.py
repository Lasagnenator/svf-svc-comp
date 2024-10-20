#!/usr/bin/python3
# Wrapper around SVF to adapt to SVC
# SVF: https://github.com/SVF-tools/SVF
# SVC: https://sv-comp.sosy-lab.org/2025/

import argparse
import os
import re
import sys
import subprocess
import tempfile

from util import *
import strategies
import witness_output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--bits", choices=["32","64"], help="bit width", default="64")
    parser.add_argument("--prop", help="property file", default=None)
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose output")
    parser.add_argument("--debug", "-d", action="store_true", help="debug output")
    parser.add_argument("--time-limit", type=int, default=-1, help="SVF time limit")
    parser.add_argument("c_file", help="input C file in SV-Comp format")

    args, extra = parser.parse_known_args()
    input_file = args.c_file
    bits = args.bits
    prop_file = args.prop

    # TODO: Find some way of making clang actually compile 32 bit
    # binaries on a 64 bit environment without errors.
    # Override bit width since it won't compile in 32 bit mode.
    bits = "64"

    if args.verbose or args.debug:
        print(f"Running analysis: {input_file}.")
        print(f"Selected bit width: {bits}.")
        print(f"Property file: {prop_file}.")
        print(f"SVF time limit: {args.time_limit}.")
        print(f"Extra (unused) options: {extra}.")
        print(f"Using include_replace: {INCLUDE_REPLACE}.")

    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(INCLUDE_REPLACE, "r") as f:
        buffer.write(f.read())

    with open(input_file, "r") as f:
        strategy = strategies.apply_strategy(f.read(), prop_file)
        replaced, exe, svf_options, category = strategy
        buffer.write(replaced)

    # buffer now contains our fixed code to pass into SVF.
    buffer.flush()

    command = ["clang", "-S", "-emit-llvm", "-o", "working.ll", f"-m{bits}"]
    command.append(buffer.name)

    if args.verbose:
        print(f"Running clang with command: {' '.join(command)}")
    retcode = subprocess.run(command).returncode
    if retcode != 0:
        print(f"Clang exitted with code {retcode}.")

    if args.verbose or args.debug:
        buffer.seek(0)
        print(buffer.read())

    buffer.close()

    # Run SVF on the resulting file.
    # TODO: Get SVF running with other analysis options.
    # TODO: Incorporate cpu time limits.
    svf_bin = get_real_path(f"svf/bin/{exe}")
    extapi = get_real_path("svf/lib/extapi.bc")
    command = [f"{svf_bin}", f"-extapi={extapi}"]
    command.extend(svf_options)

    if not (args.verbose and args.debug):
        # Disable very long output from SVF.
        command.append("-stat=false")

    if args.time_limit != -1:
        command.extend(["-clock-type=cpu", f"-fs-time-limit={args.time_limit}"])

    command.append("working.ll")

    if args.verbose:
        print(f"Running SVF with command: {' '.join(command)}")

    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if args.debug:
        print(process.stdout)
        print(process.stderr)
    print(strategies.interpret_output(process, strategy))
    witness_output.generate_witness(process.stderr, args)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e.args}")
