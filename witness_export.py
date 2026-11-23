"""Export an SV-COMP witness for a completed property decision."""

from __future__ import annotations

from typing import TYPE_CHECKING

import generate_witness
import invariants
import violations
from property_evaluation import DecisionStatus, PropertyDecision
from util import Log, Property, log

if TYPE_CHECKING:
    import pysvf

    from AbstractInterpretation import AbstractExecution


def export_witness(
    decision: PropertyDecision,
    prop: Property,
    ae: AbstractExecution,
    pag: pysvf.SVFIR,
    input_file_path: str,
    prop_file_path: str,
    witness_file_path: str,
    input_line_count: int,
    bits: str,
    witness_format: str,
) -> None:
    """Write the selected witness, if any, while the PAG is still live."""
    if decision.status is DecisionStatus.UNKNOWN:
        log(f"No witness for result: {decision.status.value}", category=Log.SETUP)
        return

    with open(prop_file_path) as f:
        spec = f.read().strip()
    data_model = "ILP32" if bits == "32" else "LP64"

    if decision.status is DecisionStatus.CORRECT:
        loop_invariants = invariants.extract_loop_invariants(
            ae, pag, input_file_path, input_line_count)
        log(f"Exported {len(loop_invariants)} loop invariant(s).", category=Log.SETUP)
        generate_witness.write_witness(
            loop_invariants, [input_file_path], spec, witness_file_path, witness_format, data_model)
        return

    if prop is Property.REACH_SAFETY:
        segments = violations.reach_error_segments(
            ae.results.get("reach", []), decision.cfl_reachable_ids,
            input_file_path, input_line_count)
    elif prop is Property.MEM_SAFETY:
        # Name only the violated subproperty, not the whole property file.
        spec = violations.specification_for(spec, decision.subproperty)
        segments = violations.memory_segments(
            ae.results[decision.finding_kind], violations.main_exit(pag),
            input_file_path, input_line_count)
    else:
        # Property.MEM_CLEANUP
        segments = violations.memory_segments(
            ae.results.get("memoryleak", []), violations.main_exit(pag),
            input_file_path, input_line_count)

    try:
        if segments is None:
            raise ValueError("no violation site has a usable source location")
        generate_witness.write_violation_witness(
            segments, [input_file_path], spec, witness_file_path, witness_format, data_model)
        log(f"Exported a violation witness with {len(segments)} segment(s).")
    except ValueError as exc:
        log(f"No violation witness: {exc}")
