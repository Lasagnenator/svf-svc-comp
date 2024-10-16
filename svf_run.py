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

VERSION = "SVF-SVC 1.0 using SVF 3.0"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.join(os.path.dirname(__file__), relative)

# Generic preprocessor fix.
INCLUDE_REPLACE = get_real_path("include_replace.c")

# Patterns for replacement.
# This prevents the #define from making a duplicate.
svc_assert = "__VERIFIER_assert(int"
svc_assert_replace = f"__SVC_assert(int"

def replacement(text: str):
    # replace asserts with SVF's assert.
    return text.replace(svc_assert, svc_assert_replace)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--bits", choices=["32","64"], help="bit width", default="64")
    parser.add_argument("--prop", action="append", help="property files", default=[])
    parser.add_argument("c_file", help="input C file")

    args, extra = parser.parse_known_args()
    input_file = args.c_file
    bits = args.bits
    properties = args.prop

    # TODO: Find some way of making clang actually compile 32 bit
    # binaries on a 64 bit environment without errors.
    # Override bit width since it won't compile in 32 bit mode.
    bits = 64

    print(f"Running analysis: {input_file}.")
    print(f"Selected bit width: {bits}.")
    print(f"Properties: {properties}.")
    print(f"Extra (unused) options: {extra}.")

    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(INCLUDE_REPLACE, "r") as f:
        print(f"Using include_replace: {INCLUDE_REPLACE}.")
        buffer.write(f.read())

    with open(input_file, "r") as f:
        buffer.write(replacement(f.read()))

    # buffer now contains our fixed code to pass into SVF.
    buffer.flush()

    command = ["clang", "-S", "-emit-llvm", "-o", "working.ll", f"-m{bits}"]
    command.append(buffer.name)

    print(f"Running clang with command: {' '.join(command)}")
    subprocess.run(command)

    buffer.close()

    # Run SVF on the resulting file.
    # TODO: Get SVF running with other analysis options.
    svf_bin = get_real_path("svf/bin")
    extapi = get_real_path("svf/lib/extapi.bc")
    command = [f"{svf_bin}/wpa", f"-extapi={extapi}", "-stat=false"]

    # Specific analysis
    command.append("-ander")

    command.append("working.ll")
    print(f"Running SVF with command: {' '.join(command)}")
    subprocess.run(command)
