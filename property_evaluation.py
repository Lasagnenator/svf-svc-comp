"""Decide SV-COMP properties from completed abstract execution results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import pysvf

from cfl_reachability import CFLreachability
from util import Log, Property, log
from violations import memory_violation

if TYPE_CHECKING:
    from AbstractInterpretation import AbstractExecution


class DecisionStatus(Enum):
    CORRECT = "Correct"
    INCORRECT = "Incorrect"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class PropertyDecision:
    status: DecisionStatus
    verdict: str
    finding_kind: str | None = None
    subproperty: str | None = None
    cfl_reachable_ids: frozenset[int] = frozenset()


_UNKNOWN = PropertyDecision(DecisionStatus.UNKNOWN, "Unknown")


def _evaluate_reach(
    ae: AbstractExecution,
    pag: pysvf.SVFIR,
    claim_reach_violations: bool,
) -> PropertyDecision:
    feasible_ids = set()
    for is_feasible, call_node in ae.results.get("reach", []):
        if is_feasible and call_node is not None:
            feasible_ids.add(call_node.getId())

    # CFL is a cross-check; its 2-frame stack cannot prove safety or veto a finding.
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

    # An empty reach list is ambiguous: a never-visited site can be a coverage gap.
    icfg_sites = set()
    for n in pag.getICFG().getNodes():
        if isinstance(n, pysvf.CallICFGNode):
            callee = n.getCalledFunction()
            if callee and callee.getName() == "reach_error":
                icfg_sites.add(n.getId())
    visited_sites = {node.getId() for _, node in ae.results.get("reach", [])
                     if node is not None}
    analysed = getattr(ae, "visited", set())
    proven_dead = getattr(ae, "unreachable_nodes", set())
    calls_by_function = {}
    indirect_callers = set()
    entry_roots = {"main", None}

    for call in pag.getICFG().getNodes():
        if isinstance(call, pysvf.FunEntryICFGNode):
            function = call.getFun()
            if function is not None and function.hasAddressTaken():
                entry_roots.add(function.getName())
        if not isinstance(call, pysvf.CallICFGNode):
            continue

        caller = call.getFun()
        caller_name = caller.getName() if caller is not None else None
        if caller_name in analysed and call in proven_dead:
            continue

        callee = call.getCalledFunction()

        if callee is None:
            indirect_callers.add(caller_name)
        else:
            calls_by_function.setdefault(caller_name, set()).add(callee.getName())

    possibly_entered = set(analysed) | entry_roots
    worklist = list(possibly_entered)

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
        if n.getId() in visited_sites:
            continue

        holder = n.getFun().getName() if n.getFun() else None

        if holder is None or holder not in analysed:
            # Never trust propagated deadness inside a function
            # that AE never actually analysed.
            if holder is None or has_unknown_targets or holder in possibly_entered:
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
    for reason in sorted(set(gaps)):
        log(f"  gap: {reason}", category=Log.REACH)

    if feasible_ids:
        if claim_reach_violations:
            return PropertyDecision(DecisionStatus.INCORRECT, "REACH Incorrect",
                                    cfl_reachable_ids=frozenset(cfl_ids))
        log("reach_error may be reachable, but nothing proves a concrete path "
            "gets there; reporting Unknown rather than claiming a violation.")
        return _UNKNOWN
    elif gaps:
        log("No feasible reach_error, but the analysis was incomplete; "
            "reporting Unknown rather than claiming safety.")
        return _UNKNOWN
    else:
        return PropertyDecision(DecisionStatus.CORRECT, "REACH Correct")


def _evaluate_memory(prop: Property, ae: AbstractExecution) -> PropertyDecision:
    results = ae.results
    gaps = [reason for key in ("incomplete", "memory_gaps", "global_memory_gaps")
            for reason in results.get(key, [])]
    if gaps:
        log(f"Memory analysis inconclusive ({len(gaps)} gap(s)); reporting Unknown.")
        for reason in sorted(set(gaps)):
            log(f"  gap: {reason}", category=Log.MEMORY)
        return _UNKNOWN

    if prop is Property.MEM_CLEANUP:
        if results.get("memoryleak"):
            return PropertyDecision(DecisionStatus.INCORRECT, "CLEANUP Incorrect",
                                    finding_kind="memoryleak")
        return PropertyDecision(DecisionStatus.CORRECT, "CLEANUP Correct")

    finding = memory_violation(results)
    log("Coverage gaps recorded: 0")
    if finding:
        kind, subproperty = finding
        return PropertyDecision(DecisionStatus.INCORRECT, f"MEMORY Incorrect({subproperty})",
                                finding_kind=kind, subproperty=subproperty)
    return PropertyDecision(DecisionStatus.CORRECT, "MEMORY Correct")


def evaluate_property(
    prop: Property,
    ae: AbstractExecution,
    pag: pysvf.SVFIR,
    claim_reach_violations: bool = False,
) -> PropertyDecision:
    """Evaluate a property after AE has completed, while the PAG is still live."""
    if prop is Property.REACH_SAFETY:
        return _evaluate_reach(ae, pag, claim_reach_violations)
    if prop in (Property.MEM_SAFETY, Property.MEM_CLEANUP):
        return _evaluate_memory(prop, ae)
    return _UNKNOWN
