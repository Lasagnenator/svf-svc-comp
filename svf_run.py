#! /usr/bin/env python3

import pysvf
import argparse
import subprocess
import tempfile
import generate_witness

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
    parser.add_argument("--claim-violations", action="store_true",
                        help="report a violation whenever the abstract state says reach_error "
                             "is feasible. Off by default: abstract feasibility is not proof of "
                             "a concrete path, and the witness carries no trace to confirm it.")
    parser.add_argument("--witness", default=None, help="witness output")
    parser.add_argument("--witness-format", default="1.0", choices=["1.0", "2.0"], help="witness version")
    parser.add_argument("c_file", help="input C file in SV-Comp format")

    args, extra = parser.parse_known_args()
    log(f"Arguments: {args}")
    log(f"Extra unknown arguments: {extra}")

    # format 2.0+ only accept .yml file
    if args.witness is None:
        args.witness = "witness.yml" if args.witness_format == "2.0" else "witness.graphml"
    if args.witness_format == "2.0" and not args.witness.endswith(".yml"):
        log(f"Warning: format 2.0 requires .yml, ignoring {args.witness}")
        args.witness = "witness.yml"

    runSVF(args.c_file, args.prop, args.witness, args.bits, args.witness_format, args.claim_violations)

# Accepts a C source file, and traverses its ICFG using the SVF framework
def runSVF(input_file_path, prop_file_path, witness_file_path, bits="64", witness_format="1.0", claim_violations=False):
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

    # SV-COMP tasks predate clang 15; demote these errors and raise the bracket limit.
    command = ["clang", f"-m{bits}", "-S", "-c", "-O0", "-fno-discard-value-names", "-g", "-emit-llvm",
               "-Wno-error=int-conversion",
               "-Wno-error=implicit-function-declaration",
               "-Wno-error=incompatible-function-pointer-types",
               "-fbracket-depth=1024",
               "-o", working_file.name,]
    command.append(buffer.name)

    log(f"Running clang with command: {' '.join(command)}")
    retcode = subprocess.run(command).returncode
    buffer.close()
    log(f"Clang exitted with code {retcode}.")

    if retcode != 0:
        log(f"Clang failed to output {working_file.name}. SVF will fail.")
        working_file.close()
        fail("ERROR(CLANG)", retcode)

    try:
        # This code is copied from python/test-ae.py to use SVF
        pysvf.buildSVFModule(working_file.name)
        pag = pysvf.getPAG()
    except Exception as e:
        log(f"pysvf: Failed with {repr(e)}. SVF-SVC will fail.")
        log_exception(e)
        working_file.close()
        fail("ERROR(SVF)")

    # parse input prop file path to find the file name
    prop_file_name = prop_file_path.split('/')[-1]

    # ae first
    try:
        ae = AbstractExecution(pag)
        ae.analyse()
        log(ae.results)
    except Exception as e:
        log(f"AbstractExecution: Failed with {repr(e)}. SVF-SVC will not continue.")
        log_exception(e)
        working_file.close()
        fail("ERROR(AE)")

    if prop_file_name == 'unreach-call.prp':
        feasible_ids = set()
        for (is_feasible, callNode) in ae.results.get("reach", []):
            if is_feasible and callNode is not None:
                feasible_ids.add(callNode.getId())

        # CFL is a log-only cross-check: its 2-frame stack cannot prove safety or veto a finding.
        log("Running CFL reachability analysis...")
        cfl = CFLreachability(pag)
        cfl_results = cfl.analyze()
        cfl_ids = {n.getId() for ok, n in cfl_results.get("reach", []) if ok and n is not None}

        gaps = list(ae.results.get("incomplete", []))

        ###SVF SV-COMP-ADDITION
        # An empty reach list is ambiguous: a never-visited site is a coverage gap, not a proof.
        icfg_sites = set()
        for n in pag.getICFG().getNodes():
            if isinstance(n, pysvf.CallICFGNode):
                callee = n.getCalledFunction()
                if callee and callee.getName() == "reach_error":
                    icfg_sites.add(n.getId())
        visited_sites = {node.getId() for (_, node) in ae.results.get("reach", [])
                         if node is not None}
        # Only a gap if the holding function was never analysed; otherwise the guard was pruned.
        analysed = getattr(ae, "visited", set())
        unreached = set()
        for n in pag.getICFG().getNodes():
            if not isinstance(n, pysvf.CallICFGNode) or n.getId() not in icfg_sites:
                continue
            if n.getId() in visited_sites:
                continue
            holder = n.getFun().getName() if n.getFun() else None
            if holder is None or holder not in analysed:
                unreached.add(n.getId())
        log(f"reach_error sites in ICFG     : {sorted(icfg_sites)}")
        log(f"AE visited reach_error sites  : {sorted(visited_sites)}")
        if unreached:
            gaps.append(f"reach_error sites in functions the analysis never entered: "
                        f"{sorted(unreached)}")

        log(f"AE feasible reach_error nodes : {sorted(feasible_ids)}")
        log(f"CFL reachable reach_error nodes: {sorted(cfl_ids)}")
        log(f"Coverage gaps recorded: {len(gaps)}")
        for reason in sorted(set(gaps))[:25]:
            log(f"  gap: {reason}")

        if feasible_ids:
            if claim_violations:
                print("REACH Incorrect")
                correctness = "Incorrect"
            else:
                # Abstract feasibility is not a concrete path, and the witness carries no trace to confirm it.
                log("reach_error may be reachable, but nothing proves a concrete path "
                    "gets there; reporting Unknown rather than claiming a violation.")
                print("Unknown")
                correctness = "Unknown"
        elif gaps:
            # Paths were dropped somewhere, so this is not a proof of safety.
            log("No feasible reach_error, but the analysis was incomplete; "
                "reporting Unknown rather than claiming safety.")
            print("Unknown")
            correctness = "Unknown"
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
        print("Unknown")
        correctness = "Unknown"

    ### TODO: neither path exports invariants yet (2.0 passes an empty invariant set)
    if witness_format == "2.0":
        if "Correct" in correctness and "Incorrect" not in correctness:
            with open(prop_file_path) as f:
                spec = f.read().strip()
            generate_witness.write_witness([], [input_file_path], spec, witness_file_path)
        else:
            # violation_sequence not implemented yet; produce nothing
            log(f"No 2.0 witness for result: {correctness}")
        generate_witness.write_witness([], [input_file_path], spec, witness_file_path)
    else:
        witness_output.generate_witness(
            correctness, input_file_path, prop_file_path, witness_file_path, bits)

    working_file.close()
    pysvf.releasePAG()


if __name__ == "__main__":
    main()
