#! /usr/bin/env python3

import pysvf
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

    runSVF(args.c_file, args.prop, args.witness)


# Accepts a C source file, and traverses its ICFG using the SVF framework
def runSVF(input_file_path, prop_file_path, witness_file_path):
    # Preprocesses the C source file by replacing the nondet function calls
    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(input_file_path, "r") as f:
        c_code = f.read()
        replaced_code = nondet.generate_nondet_replacing(c_code)

        buffer.write(replaced_code)

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
        log("ERROR(CLANG)")
        exit(retcode)

    buffer.close()

    # This code is copied from python/test-ae.py to use SVF
    pysvf.buildSVFModule(working_file.name)
    pag = pysvf.getPAG()

    # parse input prop file path to find the file name
    prop_file_name = prop_file_path.split('/')[-1]

    if prop_file_name == 'unreach-call.prp':
        # ae first
        ae = AbstractExecution(pag)
        ae.analyse()
        log(ae.results)

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
            witness_output.generate_witness_v2("Incorrect", input_file_path, prop_file_path, witness_file_path)
        else:
            print("REACH Correct")
            witness_output.generate_witness_v2("Correct", input_file_path, prop_file_path, witness_file_path)
    elif prop_file_name == 'no-overflow.prp':
        ae = AbstractExecution(pag)
        ae.analyse()
        log(ae.results)
        # if the list of SVFstmts where buffer overflows occur is non-zero, then there are buffer overflows
        # (kinda because of how our use of the SVF python API is done)
        if len(ae.results.get(["bufferoverflow"], [])) > 0:
            # idk if this is the right type of memory error
            print("OVERFLOW Incorrect")
            witness_output.generate_witness_v2("Incorrect", input_file_path, prop_file_path, witness_file_path)
        else:
            witness_output.generate_witness_v2("Correct", input_file_path, prop_file_path, witness_file_path)


    ###TODO: right now it doesnt do witness output, have to implement that soon

    pysvf.releasePAG()


if __name__ == "__main__":
    main()
