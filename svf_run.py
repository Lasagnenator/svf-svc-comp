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

import nondet
from util import *
import strategies
import witness_output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--bits", choices=["32","64"], help="bit width", default="64")
    parser.add_argument("--prop", help="property file", default=None)
    parser.add_argument("--verbose", "-v", action="store_true", help="display internals")
    parser.add_argument("--time-limit", type=int, default=-1, help="SVF time limit")
    parser.add_argument("--witness", default="witness.graphml", help="witness output")
    parser.add_argument("c_file", help="input C file in SV-Comp format")

    args, extra = parser.parse_known_args()
    log(f"Arguments: {args}")
    log(f"Extra (unused) arguments: {extra}")

    input_file = args.c_file
    bits = args.bits
    prop_file = args.prop
    witness_file = args.witness

    # TODO: Find some way of making clang actually compile 32 bit
    # binaries on a 64 bit environment without errors.
    # Override bit width since it won't compile in 32 bit mode.
    bits = "64"

    log(f"Running analysis: {input_file}.")
    log(f"Selected bit width: {bits}.")
    log(f"Property file: {prop_file}.")
    log(f"SVF time limit: {args.time_limit}.")
    log(f"Witness output file: {witness_file}.")

    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")

    with open(input_file, "r") as f:
        c_code = f.read()
        buffer.write(nondet.generate_nondet(c_code))
        strategy = strategies.apply_strategy(c_code, prop_file)
        replaced, exe, svf_options, category = strategy
        buffer.write(replaced)

    # buffer now contains our fixed code to pass into SVF.
    buffer.flush()

    if args.verbose:
        log("Generated file:")
        buffer.seek(0)
        log(buffer.read())

    working_file = tempfile.NamedTemporaryFile("w+", suffix=".ll")

    command = ["clang", "-S", "-emit-llvm", "-o", working_file.name, f"-m{bits}"]
    command.append(buffer.name)

    log(f"Running clang with command: {' '.join(command)}")
    retcode = subprocess.run(command).returncode
    log(f"Clang exitted with code {retcode}.")

    if retcode != 0:
        log(f"Clang failed to output {working_file.name}. SVF will fail.")
        fail("ERROR(CLANG)", retcode)

    buffer.close()

    # Run SVF on the resulting file.
    svf_bin = get_real_path(f"svf/bin/{exe}")
    extapi = get_real_path("svf/lib/extapi.bc")
    command = [f"{svf_bin}", f"-extapi={extapi}"]
    command.extend(svf_options)

    if not args.verbose:
        # Disable very long output from SVF.
        command.append("-stat=false")

    if args.time_limit != -1:
        command.extend(["-clock-type=cpu", f"-fs-time-limit={args.time_limit}"])

    command.append(working_file.name)

    log(f"Running SVF with command: {' '.join(command)}")

    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = strategies.interpret_output(process, strategy)
    print(result)
    witness_output.generate_witness(result, args, witness_file)
    working_file.close()

if __name__ == "__main__":
    main()
