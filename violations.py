"""
Build the waypoints of a violation witness from the abstract execution's findings.

The abstract execution shows that reach_error may be reached, but not along which
concrete path. A branching or assumption waypoint that the real path does not take
makes the whole witness unconfirmable, so only the target is given and the validator
is left to find the path to it. generate_witness.write_violation_witness writes the
segments returned here.
"""

from invariants import parse_source_location


def reach_error_segments(reach_results, cfl_reachable_ids, file_name, max_line=None):
    """Return the segments of an unreach-call violation witness, or None.

    `reach_results` is the abstract execution's list of (feasible, call node) pairs
    for reach_error call sites. One feasible site becomes the target: preferably one
    that CFL reachability also reaches, then the earliest in the file, so the same
    run always picks the same site. `file_name` replaces the path SVF saw, which is
    the temporary copy that svf_run.py compiles.
    """
    candidates = []
    for feasible, node in reach_results:
        if not feasible or node is None:
            continue
        location = parse_source_location(node.getSourceLoc())
        if location is None:
            continue
        column = location.get("cl")
        if type(column) is not int or column < 1:
            continue
        if max_line is not None and location["ln"] > max_line:
            continue  # inside code appended by the nondet preprocessing, not the input
        function = node.getFun()
        candidates.append((node.getId() not in cfl_reachable_ids, location["ln"], column,
                           function.getName() if function else None))
    if not candidates:
        return None

    _, line, column, function = min(candidates)
    target = {"type": "target", "file_name": file_name, "line": line, "column": column}
    if function:
        target["function"] = function
    return [[target]]
