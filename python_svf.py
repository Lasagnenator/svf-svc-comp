#! /usr/bin/env python3


import argparse
import yaml
import os
import sys
import subprocess
import tempfile

import nondet
from util import *
import strategies
import witness_output
from AbstractInterpretation import *
from cfl_reachability.py import CFLreachability

def main():
    # this implementation just accepts the file to do testing on
    parser = argparse.ArgumentParser()
    parser.add_argument("sourcefile", help="c source file to be verified")
    parser.add_argument("propfile", help="property file to be checked for")

    args, extra = parser.parse_known_args()
    log(f"Arguments: {args}")

    runSVF(args.sourcefile, args.propfile)



    # Im not sure of the actual input format, implemented it to follow the format for verification
    # tasks from gitlab.com/sosy-lab/benchmarking/sv-benchmarks/ but that seems to be
    # different to whats actually used in the competition

    # parser = argparse.ArgumentParser()
    # parser.add_argument("yamlfile", help="yaml file that defines verification task")

    # args, extra = parser.parse_known_args()
    # log(f"Arguments: {args}")

    # # Reading verification specification from provided yaml file
    # with open(args.yamlfile) as stream:
    #     try:
    #         yaml_contents = yaml.safe_load(stream)
    #         input_file_name = yaml_contents["input_files"]
    #         path_prefix = args.yamlfile[::-1].split("/", 1)[1][::-1]
    #         input_file_path = path_prefix + "/" + input_file_name

    #         # This creates the paths for the property files (assuming sv-benchmarks is installed)
    #         property_files = [(x["property_file"]).replace("../", "sv-benchmarks/c/") for x in yaml_contents["properties"]]


    #         # Currently attempting to modify our use of SVF itself instead of modifying the code
            

    #     except yaml.YAMLError as exc:
    #         log(exc)


# Accepts a C source file, and traverses its ICFG using the SVF framework
def runSVF(input_file_path, prop_file_path):
    # Preprocesses the C source file by replacing the nondet function calls
    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(input_file_path, "r") as f:
        c_code = f.read()
        c_code = nondet.generate_nondet_replacing(c_code)
        buffer.write(c_code)
        buffer.flush()
    log("Generated file:")
    buffer.seek(0)
    log(buffer.read())

    # Compiles the C source file to LLVMIR
    working_file = tempfile.NamedTemporaryFile("w+", suffix=".ll")
    command = [
        "clang", "-S", "-c", "-O0", "-fno-discard-value-names",
        "-g", "-emit-llvm", "-o", working_file.name,
        buffer.name
    ]
    log(f"Running clang with command: {&apos; &apos;.join(command)}")
    retcode = subprocess.run(command).returncode
    log(f"Clang exitted with code {retcode}.")
    if retcode != 0:
        log(f"Clang failed to output {working_file.name}. SVF will fail.")
        log("ERROR(CLANG)")
        exit(retcode)
    buffer.close()

    prop_file_name = prop_file_path.split(&apos;/&apos;)[-1]

    pysvf.buildSVFModule(working_file.name)
    pag = pysvf.getPAG()

    if prop_file_name == &apos;unreach-call.prp&apos;:
        log("Running CFL reachability analysis...")
        cfl = CFLreachability(pag)
        cfl.analyze()
        results = cfl.results

        error_detected = False
        for (is_feasible, callNode) in results["reach"]:
            error_detected |= is_feasible

        if error_detected:
            print("REACH Incorrect")
            witness_output.generate_witness_v2(
                "Incorrect", input_file_path, prop_file_path, "witness.xml"
            )
        else:
            witness_output.generate_witness_v2(
                "Correct", input_file_path, prop_file_path, "witness.xml"
            )

    elif prop_file_name == &apos;no-overflow.prp&apos;:

        log("Running Abstract Execution (AE) for overflow...")
        ass3 = AbstractExecution(pag)
        ass3.analyse()
        log(ass3.results)

        if len(ass3.results["bufferoverflow"]) > 0:
            print("OVERFLOW Incorrect")
            witness_output.generate_witness_v2(
                "Incorrect", input_file_path, prop_file_path, "witness.xml"
            )
        else:
            witness_output.generate_witness_v2(
                "Correct", input_file_path, prop_file_path, "witness.xml"
            )

    else:
        log(f"Unsupported property file: {prop_file_name}")
        pysvf.releasePAG()
        sys.exit(1)


    pysvf.releasePAG()


if __name__ == "__main__":
    main()

