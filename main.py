# Wrapper around SVF to adapt to SVC
# SVF: https://github.com/SVF-tools/SVF
# SVC: https://sv-comp.sosy-lab.org/2025/

import argparse
import re
import sys
import subprocess
import tempfile

# Generic preprocessor fix.
INCLUDE_REPLACE = "include_replace.c"

# Patterns for replacement.
# This prevents the #define from making a duplicate.
svc_assert = "__VERIFIER_assert(int"
svc_assert_replace = f"__SVC_assert(int"

def replacement(text: str):
    # replace asserts with SVF's assert.
    return text.replace(svc_assert, svc_assert_replace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("c_file", help="The input C file")
    parser.add_argument("--bits", choices=["32", "64"], required=True, help="Bit depth of target")

    args = parser.parse_args()
    input_file = args.c_file

    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(INCLUDE_REPLACE, "r") as f:
        buffer.write(f.read())

    with open(input_file, "r") as f:
        buffer.write(replacement(f.read()))

    # buffer now contains our fixed code to pass into SVF.
    buffer.flush()

    command = ["clang", "-v", "-S", "-emit-llvm", "-o", "working.ll"]

    if args.bits == "32":
        command.append("-m32")
    elif args.bits == "64":
        command.append("-m64")

    command.append(buffer.name)
    subprocess.run(command)

    buffer.close()

    # Run SVF on the resulting file.
    # TODO: Get SVF built and ready to use.
    #subprocess.run(["./bin/svf-ex", "working.ll"])
