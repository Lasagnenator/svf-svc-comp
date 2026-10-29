"""
Build the waypoints of a violation witness from the abstract execution's findings.

The abstract execution shows where a violation may happen, but not along which
concrete path it is reached. A branching or assumption waypoint that the real path
does not take makes the whole witness unconfirmable, so only the target is given and
the validator is left to find the path to it. generate_witness.write_violation_witness
writes the segments returned here.
"""

from invariants import parse_source_location

# The memory-safety subproperty each kind of finding violates, in the order svf_run.py
# reports them. A use after free is an invalid dereference: sv-benchmarks labels its
# *_uaf tasks valid-deref, and only a bad call to free itself violates valid-free.
MEMORY_FINDINGS = (
    ("bufferoverflow", "valid-deref"),
    ("nulldereference", "valid-deref"),
    ("useafterfree", "valid-deref"),
    ("doublefree", "valid-free"),
    ("memoryleak", "valid-memtrack"),
    ("badfree", "valid-free"),
)


def memory_violation(results):
    """Return (finding kind, violated subproperty) for the first memory-safety
    finding in `results`, or None when the analysis found none."""
    for kind, subproperty in MEMORY_FINDINGS:
        if results.get(kind):
            return kind, subproperty
    return None


def specification_for(property_text, subproperty):
    """Return the line of a property file that states `subproperty`.

    valid-memsafety.prp lists valid-free, valid-deref and valid-memtrack on separate
    lines, and a violation witness should name only the one that is violated.
    """
    for line in property_text.splitlines():
        if f"G {subproperty})" in " ".join(line.split()):
            return line.strip()
    return property_text.strip()


def _site(finding):
    """Return the source location and function of an ICFG node or SVF statement."""
    node = finding
    if not hasattr(node, "getSourceLoc") and hasattr(node, "getICFGNode"):
        node = node.getICFGNode()  # statements carry their location on the ICFG node
    location = parse_source_location(node.getSourceLoc()) if hasattr(node, "getSourceLoc") else None
    if location is None and hasattr(finding, "toString"):
        location = parse_source_location(finding.toString())
    function = node.getFun() if hasattr(node, "getFun") else None
    return location, function.getName() if function else None


def _target(findings, file_name, max_line):
    """Turn the best of `findings`, given as (rank, node) pairs, into target segments."""
    candidates = []
    for rank, finding in findings:
        if finding is None:
            continue
        location, function = _site(finding)
        if location is None:
            continue
        column = location.get("cl")
        if type(column) is not int or column < 1:
            continue
        if max_line is not None and location["ln"] > max_line:
            continue  # inside code appended by the nondet preprocessing, not the input
        candidates.append((rank, location["ln"], column, function))
    if not candidates:
        return None

    _, line, column, function = min(candidates)
    target = {"type": "target", "file_name": file_name, "line": line, "column": column}
    if function:
        target["function"] = function
    return [[target]]


def reach_error_segments(reach_results, cfl_reachable_ids, file_name, max_line=None):
    """Return the segments of an unreach-call violation witness, or None.

    `reach_results` is the abstract execution's list of (feasible, call node) pairs
    for reach_error call sites. One feasible site becomes the target: preferably one
    that CFL reachability also reaches, then the earliest in the file, so the same
    run always picks the same site. `file_name` replaces the path SVF saw, which is
    the temporary copy that svf_run.py compiles.
    """
    return _target([(node.getId() not in cfl_reachable_ids, node)
                    for feasible, node in reach_results if feasible and node is not None],
                   file_name, max_line)


def main_exit(pag):
    """Return main's exit node, where the abstract execution checks for leaks."""
    for node in pag.getICFG().getNodes():
        function = node.getFun()
        if node.isFunExit() and function and function.getName() == "main":
            return node
    return None


def memory_segments(findings, exit_node, file_name, max_line=None):
    """Return the segments of a memory-safety violation witness, or None.

    `findings` are what the abstract execution recorded for one kind of violation:
    the ICFG nodes or statements where it happens, or, for leaks, the ids of the
    leaked objects. A leak is only detected when main returns, so leaks target the
    statements that reach `exit_node`, main's exit, which is typically its return:
    the exit node's own location is just the function's line, without a column.
    The earliest site in the file becomes the target.
    """
    sites = [finding for finding in findings if not isinstance(finding, int)]
    if len(sites) < len(findings) and exit_node is not None:
        sites.extend(edge.getSrcNode() for edge in exit_node.getInEdges())
    return _target([(False, site) for site in sites], file_name, max_line)
