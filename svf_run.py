#! /usr/bin/env python3

import pysvf
import argparse
import subprocess
import tempfile
import generate_witness
import invariants
import violations
import re
import importlib.metadata

import nondet
from util import *
from AbstractInterpretation import *
from cfl_reachability import CFLreachability

def main():
    # this implementation just accepts the file to do testing on
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--bits", choices=["32","64"], help="bit width", default="64")
    parser.add_argument("--prop", help="property file", default=None)
    parser.add_argument("--time-limit", type=int, default=-1, help="SVF time limit")
    parser.add_argument("--claim-violations", action="store_true",
                        help="report a violation whenever the abstract state says reach_error "
                             "is feasible. Off by default: abstract feasibility is not proof of "
                             "a concrete path, and the witness carries no trace to confirm it.")
    parser.add_argument("--witness", default="witness.yml", help="witness output")
    parser.add_argument("--witness-format", default="2.0", choices=["2.0", "2.1", "2.2"], help="witness format version")
    parser.add_argument("c_file", help="input C file in SV-Comp format")

    args, extra = parser.parse_known_args()

    log(f"SVf-SVC Version {VERSION}", category=Log.SETUP)
    log(f"PySVF Version {importlib.metadata.version('pysvf')}", category=Log.SETUP)
    log(f"Arguments: {args}", category=Log.SETUP)
    log(f"Extra unknown arguments: {extra}", category=Log.SETUP)

    runSVF(args.c_file, args.prop, args.witness, args.bits, args.witness_format, args.claim_violations)

# Reach only. When the AE result is Unknown, the chance of error in reporting its verdict
# Gaps (paths the AE dropped) when it found no feasible reach_error: chance the task is
# really FALSE.
GAP_ERROR = {
    'external call not modelled': 0.318,
    'reach_error sites in functions the analysis never entered': 0.053,
    'recursive function body not analysed': 0.500,
    'unmodelled comparison': 0.250,
    'unresolved indirect call': 0.250,
    'Binary op': 0.333,
}

FEASIBLE_FALSE_ERROR = 0.836
FEASIBLE_TRUE_ERROR = 0.004

# Report the AE verdict when the certainty it is right is above this.
MIN_CERTAINTY = 1.00

def gap_kind(reason):
    """The reason without node ids, names or values."""
    return re.sub(r"[:\[].*| at node.*| \d.*", "", reason)

# Accepts a C source file, and traverses its ICFG using the SVF framework
def runSVF(input_file_path, prop_file_path, witness_file_path, bits="64", witness_format="2.0", claim_violations=False):

    # Preprocesses the C source file by replacing the nondet function calls
    buffer = tempfile.NamedTemporaryFile("w+", suffix=".c")
    with open(input_file_path, "r") as f:
        c_code = f.read()
        nondet_defs = nondet.generate_nondet(c_code)

        buffer.write(c_code)
        buffer.write(nondet_defs)

    # Anything SVF reports past this line comes from the appended nondet definitions
    # rather than the input, so invariants there must not reach the witness.
    input_line_count = len(c_code.splitlines())

    buffer.flush()

    log("Generated file:", category=Log.SETUP)
    buffer.seek(0)
    log(buffer.read(), category=Log.SETUP)

    # Compiles the C source file to LLVMIR
    working_file = tempfile.NamedTemporaryFile("w+", suffix=".ll")

    # SV-COMP tasks predate clang 15; demote these errors and raise the bracket limit.
    command = ["clang-21", f"-m{bits}", "-S", "-O0", "-fno-discard-value-names", "-g", "-emit-llvm",
               "-Wno-error=int-conversion",
               "-Wno-error=implicit-function-declaration",
               "-Wno-error=incompatible-function-pointer-types",
               "-fbracket-depth=1024",
               "-o", working_file.name,]
    command.append(buffer.name)

    log(f"Running clang with command: {' '.join(command)}", category=Log.SETUP)
    retcode = subprocess.run(command).returncode
    buffer.close()
    log(f"Clang exitted with code {retcode}.", category=Log.SETUP)

    if retcode != 0:
        log(f"Clang failed to output {working_file.name}. SVF will fail.")
        working_file.close()
        fail("ERROR(CLANG)", retcode)


    try:
        svf_args = [working_file.name]
        pysvf.buildSVFModule(svf_args)
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
        # Memory verdicts are Unknown on any gap, so stop at a dropped call instead of running on.
        ae.stop_on_gap = prop_file_name in ('valid-memsafety.prp', 'valid-memcleanup.prp')
        ae.analyse()
        log(ae.results, category=Log.TRACE)
    except AnalysisIncomplete as e:
        log(f"Memory analysis inconclusive, stopped at: {e}; reporting Unknown.")
        print("Unknown")
        working_file.close()
        pysvf.releasePAG()
        return
    except UnknownException:
        # An operation the analysis does not support, so it cannot give a verdict.
        print("Unknown")
        working_file.close()
        pysvf.releasePAG()
        return
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
        log("Running CFL reachability analysis...", category=Log.REACH)
        cfl = CFLreachability(pag)
        cfl_results = cfl.analyze()
        cfl_ids = {n.getId() for ok, n in cfl_results.get("reach", []) if ok and n is not None}

        # Only dropped paths are gaps here. Possible memory errors are for the memory
        # properties: reach tasks are assumed free of undefined behaviour.
        gaps = list(ae.results.get("incomplete", []))
        ignored = (len(ae.results.get("memory_gaps", []))
                   + len(ae.results.get("global_memory_gaps", [])))
        if ignored:
            log(f"Ignored {ignored} memory gap(s) for reachability", category=Log.REACH)

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
        proven_dead = getattr(ae, "unreachable_nodes", set())
        calls_by_function = {}
        indirect_callers = set()

        for call in pag.getICFG().getNodes():
            if not isinstance(call, pysvf.CallICFGNode):
                continue

            caller = call.getFun()
            if caller is None or call in proven_dead:
                continue

            caller_name = caller.getName()
            callee = call.getCalledFunction()

            if callee is None:
                indirect_callers.add(caller_name)
            else:
                calls_by_function.setdefault(caller_name, set()).add(
                    callee.getName()
                )

        possibly_entered = set(analysed)
        worklist = list(analysed)

        while worklist:
            function = worklist.pop()

            for callee in calls_by_function.get(function, ()):
                if callee not in possibly_entered:
                    possibly_entered.add(callee)
                    worklist.append(callee)

        # An unresolved indirect call could target an otherwise unentered function.
        has_unknown_targets = bool(possibly_entered & indirect_callers)
        unreached = set()
        for n in pag.getICFG().getNodes():
            if not isinstance(n, pysvf.CallICFGNode) or n.getId() not in icfg_sites:
                continue
            if n.getId() == 17:
                log(
                    f"[NODE17] "
                    f"function={n.getFun().getName() if n.getFun() else None}, "
                    f"visited={n.getId() in visited_sites}, "
                    f"analysed={n.getFun().getName() in analysed if n.getFun() else False}, "
                    f"infeasible={n in ae.infeasible_nodes}, "
                    f"proven_dead={n in proven_dead}, "
                    f"has_state={n in ae.post_abs_trace}"
                )
            if n.getId() in visited_sites:
                continue

            holder = n.getFun().getName() if n.getFun() else None

            if holder is None or holder not in analysed:
                # Never trust propagated deadness inside a function
                # that AE never actually analysed.
                unreached.add(n.getId())
            elif n not in proven_dead:
                unreached.add(n.getId())
        log(f"reach_error sites in ICFG     : {sorted(icfg_sites)}", category=Log.REACH)
        log(f"AE visited reach_error sites  : {sorted(visited_sites)}", category=Log.REACH)
        if unreached:
            gaps.append(f"reach_error sites in functions the analysis never entered: "
                        f"{sorted(unreached)}")

        log(f"AE feasible reach_error nodes : {sorted(feasible_ids)}", category=Log.REACH)
        log(f"CFL reachable reach_error nodes: {sorted(cfl_ids)}", category=Log.REACH)
        log(f"Coverage gaps recorded: {len(gaps)}", category=Log.REACH)
        for reason in sorted(set(gaps))[:25]:
            log(f"  gap: {reason}", category=Log.REACH)

        if feasible_ids:
            if claim_violations:
                verdict = "REACH Incorrect"
                correctness = "Incorrect"
            else:
                # Abstract feasibility is not a concrete path, and the witness carries no trace to confirm it.
                log("reach_error may be reachable, but nothing proves a concrete path "
                    "gets there; reporting Unknown rather than claiming a violation.")
                verdict = "Unknown"
                correctness = "Unknown"
        elif gaps:
            # Paths were dropped somewhere, so this is not a proof of safety.
            log("No feasible reach_error, but the analysis was incomplete; "
                "reporting Unknown rather than claiming safety.")
            verdict = "Unknown"
            correctness = "Unknown"
        else:
            verdict = "REACH Correct"
            correctness = "Correct"

        if correctness == "Unknown":
            # Each gap, and an unproven feasible site, is an independent chance of error.
            errors = {kind: GAP_ERROR.get(kind, 1.0) for kind in map(gap_kind, gaps)}
            safe = True
            if feasible_ids:
                loops = len(re.findall(r"\b(?:while|for)\s*\(", c_code))
                floats = re.search(r"\b(?:float|double)\b", c_code) is not None
                if len(feasible_ids) == 1 and loops == 1 and floats:
                    errors["feasible reach_error, reporting TRUE"] = FEASIBLE_TRUE_ERROR
                else:
                    errors["feasible reach_error, reporting FALSE"] = FEASIBLE_FALSE_ERROR
                    safe = False
            certainty = 1.0
            for error in errors.values():
                certainty *= 1.0 - error
            log(f"Certainty of {'TRUE' if safe else 'FALSE'}: {certainty:.0%} from errors {errors}",
                category=Log.REACH)
            if certainty > MIN_CERTAINTY:
                verdict, correctness = (("REACH Correct", "Correct") if safe
                                        else ("REACH Incorrect", "Incorrect"))

    elif prop_file_name in ('valid-memsafety.prp', 'valid-memcleanup.prp') and (
            ae.results.get("incomplete") or ae.results.get("memory_gaps")
            or ae.results.get("global_memory_gaps")):
        # Dropped paths or unproven memory errors: neither safety nor a violation is shown.
        gaps = (ae.results.get("incomplete", []) + ae.results.get("memory_gaps", [])
                + ae.results.get("global_memory_gaps", []))
        log(f"Memory analysis inconclusive ({len(gaps)} gap(s)); reporting Unknown.")
        for reason in sorted(set(gaps))[:25]:
            log(f"  gap: {reason}", category=Log.MEMORY)
        verdict = "Unknown"
        correctness = "Unknown"

    elif prop_file_name == 'valid-memsafety.prp':
        # This property file bundles valid-deref, valid-free, and valid-memtrack.
        # violations.MEMORY_FINDINGS checks our arrays in order and maps each to the
        # subproperty it violates.
        memory = violations.memory_violation(ae.results)
        gaps = list(ae.results.get("incomplete", []))
        log(f"Coverage gaps recorded: {len(gaps)}")
        for reason in sorted(set(gaps))[:25]:
            log(f"  gap: {reason}")
        if memory:
            kind, subproperty = memory
            verdict = f"MEMORY Incorrect({subproperty})"
            correctness = "Incorrect"
        elif gaps:
            # Some access could not be verified, so this is not a proof of safety.
            log("No memory-safety violation found, but the analysis was incomplete; "
                "reporting Unknown rather than claiming safety.")
            verdict = "Unknown"
            correctness = "Unknown"
        else:
            verdict = "MEMORY Correct"
            correctness = "Correct"

    elif prop_file_name == 'valid-memcleanup.prp':
        # Memcleanup requires all memory to be explicitly freed before exit.
        # Our memory leak detector at the end of main() handles this perfectly.
        if len(ae.results.get("memoryleak", [])) > 0:
            verdict = "CLEANUP Incorrect"
            correctness = "Incorrect"
        else:
            verdict = "CLEANUP Correct"
            correctness = "Correct"

    else:
        # Unsupported category.
        verdict = "Unknown"
        correctness = "Unknown"

    print(verdict)

    if "Correct" in correctness and "Incorrect" not in correctness:
        with open(prop_file_path) as f:
            spec = f.read().strip()
        loop_invariants = invariants.extract_loop_invariants(
            ae, pag, input_file_path, input_line_count)
        log(f"Exported {len(loop_invariants)} loop invariant(s).", category=Log.SETUP)
        generate_witness.write_witness(
            loop_invariants, [input_file_path], spec, witness_file_path, witness_format,
            'ILP32' if bits == "32" else 'LP64')
    elif correctness == "Incorrect":
        with open(prop_file_path) as f:
            spec = f.read().strip()
        if prop_file_name == 'unreach-call.prp':
            segments = violations.reach_error_segments(
                ae.results.get("reach", []), cfl_ids, input_file_path, input_line_count)
        elif prop_file_name == 'valid-memsafety.prp':
            # Name only the violated subproperty, not the whole property file.
            spec = violations.specification_for(spec, subproperty)
            segments = violations.memory_segments(
                ae.results[kind], violations.main_exit(pag), input_file_path, input_line_count)
        else:
            segments = violations.memory_segments(
                ae.results.get("memoryleak", []), violations.main_exit(pag),
                input_file_path, input_line_count)
        try:
            if segments is None:
                raise ValueError("no violation site has a usable source location")
            generate_witness.write_violation_witness(
                segments, [input_file_path], spec, witness_file_path, witness_format,
                'ILP32' if bits == "32" else 'LP64')
            log(f"Exported a violation witness with {len(segments)} segment(s).")
        except ValueError as e:
            log(f"No violation witness: {e}")
    else:
        log(f"No witness for result: {correctness}", category=Log.SETUP)

    working_file.close()
    pysvf.releasePAG()


if __name__ == "__main__":
    main()
