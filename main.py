# Wrapper around SVF to adapt to SVC
# SVF: https://github.com/SVF-tools/SVF
# SVC: https://sv-comp.sosy-lab.org/2025/

import argparse
import os
import re
import sys
import subprocess
import tempfile
import yaml

# Generic preprocessor fix.
INCLUDE_REPLACE = "include_replace.c"

# Patterns for replacement.
# This prevents the #define from making a duplicate.
svc_assert = "__VERIFIER_assert(int"
svc_assert_replace = f"__SVC_assert(int"

def replacement(text: str):
    # replace asserts with SVF's assert.
    return text.replace(svc_assert, svc_assert_replace)

def get_real_path(yaml_file, relative):
    # Find the real path given the base yaml file and a path relative to the yaml
    return os.path.join(os.path.dirname(yaml_file), relative)

def read_yaml(yaml_file: str):
    with open(yaml_file, "r") as f:
        specification =  yaml.safe_load(f.read())

    assert specification["format_version"] == "2.0"
    assert specification["options"]["language"] == "C"

    if specification["options"]["data_model"] == "ILP32":
        bits = 32
    else:
        bits = 64

    # TODO: Find some way of making clang actually compile 32 bit
    # binaries on a 64 bit environment without errors.
    # Override bit width since it won't compile in 32 bit mode.
    bits = 64

    c_file = get_real_path(yaml_file, specification["input_files"])

    # Properties is a list of dictionaries
    properties = []
    for prop in specification["properties"]:
        file = prop["property_file"]
        prop.update({"property_file": get_real_path(yaml_file, file)})
        properties.append(prop)

    return c_file, bits, properties

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("yaml_file", help="The input yaml file")

    args = parser.parse_args()

    input_file, bits, properties = read_yaml(args.yaml_file)

    print(f"Running analysis: {input_file}.")
    print(f"Selected bit width: {bits}.")
    print(f"Properties: {properties}.")

    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(INCLUDE_REPLACE, "r") as f:
        buffer.write(f.read())

    with open(input_file, "r") as f:
        buffer.write(replacement(f.read()))

    # buffer now contains our fixed code to pass into SVF.
    buffer.flush()

    command = ["clang", "-v", "-S", "-emit-llvm", "-o", "working.ll", f"-m{bits}"]

    command.append(buffer.name)
    subprocess.run(command)

    buffer.close()

    # Run SVF on the resulting file.
    # TODO: Get SVF built and ready to use.
    #subprocess.run(["./bin/svf-ex", "working.ll"])
