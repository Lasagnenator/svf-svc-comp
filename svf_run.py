#! /usr/bin/env python3

import pysvf
import argparse
import subprocess
import tempfile

import nondet
from util import *
import witness_output
from AbstractInterpretation import *
from cfl_reachability import CFLreachability

def main():
    # this implementation just accepts the file to do testing on
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
    log(f"Extra unknown arguments: {extra}")

    runSVF(args.c_file, args.prop, args.witness)

# Accepts a C source file, and traverses its ICFG using the SVF framework
def runSVF(input_file_path, prop_file_path, witness_file_path):
    # Preprocesses the C source file by replacing the nondet function calls
    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(input_file_path, "r") as f:
        c_code = f.read()
        nondet_defs = nondet.generate_nondet(c_code)

        buffer.write(c_code)
        buffer.write(nondet_defs)

    buffer.flush()

    log("Generated file:")
    buffer.seek(0)
    log(buffer.read())

    # Compiles the C source file to LLVMIR
    working_file = tempfile.NamedTemporaryFile("w+", suffix=".ll")

    command = ["clang", "-S", "-c", "-O0", "-fno-discard-value-names", "-g", "-emit-llvm", "-o", working_file.name,]
    command.append(buffer.name)

    log(f"Running clang with command: {' '.join(command)}")
    retcode = subprocess.run(command).returncode
    log(f"Clang exitted with code {retcode}.")

    if retcode != 0:
        log(f"Clang failed to output {working_file.name}. SVF will fail.")
        fail("ERROR(CLANG)", retcode)

    buffer.close()

    try:
        # This code is copied from python/test-ae.py to use SVF
        pysvf.buildSVFModule(working_file.name)
        pag = pysvf.getPAG()
    except Exception as e:
        log(f"pysvf: Failed with {e}. SVF-SVC will fail.")
        log_exception(e)
        fail("ERROR(SVF)")

    # parse input prop file path to find the file name
    prop_file_name = prop_file_path.split('/')[-1]

    # ae first
    try:
        ae = AbstractExecution(pag)
        ae.analyse()
        log(ae.results)
    except Exception as e:
        log(f"AbstractExecution: Failed with {e}. SVF-SVC will not continue.")
        log_exception(e)
        fail("ERROR(AE)")

    if prop_file_name == 'unreach-call.prp':
        # Reachability
        feasible_ids = set()
        for (is_feasible, callNode) in ae.results.get("reach", []):
            if is_feasible and callNode is not None:
                feasible_ids.add(callNode.getId())
        # Then CFL
        log("Running CFL reachability analysis...")

        cfl = CFLreachability(pag)
        cfl_results = cfl.analyze()
        error_detected = False
        # currently for the nodes with unreach_call, if they are traversed to from the ICFG traversal,
        # their feasibility will be added to this part of the results dictionary
        #
        # if an unreach_call node is reachable, then it will always be added to the list results["reach"] = [list of nodes]
        #
        # we only care about the reachable nodes, because if they are reachable, there is an error in the C code
        for (is_reachable, callNode) in cfl_results.get("reach", []):
            if is_reachable and callNode and callNode.getId() in feasible_ids:
                error_detected = True
                break

        if error_detected:
            print("REACH Incorrect")
            correctness = "Incorrect"
        else:
            print("REACH Correct")
            correctness = "Correct"
    elif prop_file_name == 'no-overflow.prp':
        # TODO: Identify if this is the correct memory error type.
        # if the list of SVFstmts where buffer overflows occur is non-zero, then there are buffer overflows
        # (kinda because of how our use of the SVF python API is done)
        if len(ae.results.get("bufferoverflow", [])) > 0:
            print("OVERFLOW Incorrect")
            correctness = "Incorrect"
        else:
            print("OVERFLOW Correct")
            correctness = "Correct"

    else:
        # Unsupported category.
        print("UNKNOWN")
        correctness = "Unknown"

    ###TODO: right now it doesnt do invariants
    witness_output.generate_witness(correctness, input_file_path, prop_file_path, witness_file_path)

    pysvf.releasePAG()


if __name__ == "__main__":
    main()
