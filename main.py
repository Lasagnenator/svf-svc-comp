# Wrapper around SVF
# SVF: https://github.com/SVF-tools/SVF

import argparse
import os
import re
import sys
import tempfile

# Generic preprocessor fix.
INCLUDE_REPLACE = "include_replace.c"
# The function name for SVF's assert.
SVF_ASSERT = "svf_assert"

# Patterns for replacement.
non_determinate = r"__VERIFIER_nondet_.*?\(\)"
svc_assert = r"__VERIFIER_assert\("
svc_assert_replace = f"{SVF_ASSERT}("

def replacement(text: str):
    return text.replace(svc_assert, svc_assert_replace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("c_file", help="The input C file")
    parser.add_argument("--bits", choices=["32", "64"], required=True, help="Bit depth of target")

    args = parser.parse_args()
    input_file = args["c_file"]

    buffer = tempfile.NamedTemporaryFile("w+")
    with open(INCLUDE_REPLACE, "r") as f:
        buffer.write(f.read())

    with open(input_file, "r") as f:
        buffer.write(replacement(f.read()))

    buffer.flush()

    # buffer now contains our fixed code to pass into SVF.
    command = f"clang -S --emit-llvm {buffer.name}"
    os.system(command)
