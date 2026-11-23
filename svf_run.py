#! /usr/bin/env python3

import argparse
import importlib.metadata

from util import *
from AbstractInterpretation import *

from analysis_session import *
from property_evaluation import evaluate_property
from witness_export import export_witness

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--bits", choices=["32","64"], help="bit width", default="64")
    parser.add_argument("--prop", help="property file", default=None)
    parser.add_argument("--time-limit", type=int, default=-1, help="SVF time limit")
    parser.add_argument("--claim-reach-violations", action="store_true",
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

    try:
        runSVF(args.c_file, args.prop, args.witness, args.bits, args.witness_format, args.claim_reach_violations)
    except ClangError as exc:
        log(str(exc))
        fail("ERROR(CLANG)", exc.returncode)
    except SVFSetupError as exc:
        log_exception(exc)
        fail("ERROR(SVF)")
    except AESetupError as exc:
        log_exception(exc)
        fail("ERROR(AE_SETUP)")


def runSVF(input_file_path, prop_file_path, witness_file_path, bits, witness_format, claim_reach_violations):

    prop = get_property(prop_file_path)

    threshold_widening = prop == Property.REACH_SAFETY
    stop_on_gap = prop in (Property.MEM_SAFETY, Property.MEM_CLEANUP)

    with analysis_session(input_file_path, bits, threshold_widening, stop_on_gap) as session:
        try:
            session.ae.analyse()
        except (AnalysisIncomplete, UnknownException) as exc:
            report_unknown(exc)
            return
        except Exception as exc:
            log_exception(exc)
            fail("ERROR(AE)")

        decision = evaluate_property(prop, session.ae, session.pag, claim_reach_violations)
        print(decision.verdict)
        export_witness(decision, prop, session.ae, session.pag, input_file_path, prop_file_path, witness_file_path, session.input_line_count, bits, witness_format)
    # Do NOT access session objections outside the `with` block.


if __name__ == "__main__":
    main()
