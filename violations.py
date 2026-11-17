"""
Build the waypoints of a violation witness from the abstract execution's findings.

The abstract execution shows where a violation may happen, but not along which
concrete path it is reached. A branching or assumption waypoint that the real path
does not take makes the whole witness unconfirmable, so only the target is given and
the validator is left to find the path to it. generate_witness.write_violation_witness
writes the segments returned here.
"""

import operator
from pathlib import Path
import re
import time

from invariants import _source_loops, parse_source_location

# The memory-safety subproperty each kind of finding violates, in the order svf_run.py
# reports them. A use after free is an invalid dereference: sv-benchmarks labels its
# *_uaf tasks valid-deref, and only a bad call to free itself violates valid-free.
MEMORY_FINDINGS = (
    ("bufferoverflow", "valid-deref"),
    ("nulldereference", "valid-deref"),
    ("invaliddereference", "valid-deref"),
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


def definite_reach_segments(analysis, pag, file_name, max_line=None, bits="64",
                            nondet_choices=(), proof_status=None, deadline=None):
    """Replay an exact scalar prefix, rejecting unknown values and unsupported operations.

    Values retain their SVF type; integers carry both signed and unsigned views.
    Pointer identities include the invocation that allocated their stack object.
    """
    import pysvf
    from AbstractInterpretation import Predicate

    graph = pag.getICFG()
    main = pag.getFunObjVar("main")
    if main is None:
        return None
    if any(isinstance(node, pysvf.FunEntryICFGNode) and node.getFun() != main
           and node.getFun().hasAddressTaken() for node in graph.getNodes()):
        return None
    globals_values = {}
    values = globals_values
    objects = {}
    readonly_objects = set()
    memory = {}
    frames = []
    frame_id = 0
    next_frame = 1
    nondet_reads = 0
    source_nodes = None
    phi_previous = None
    phi_values = None
    comparisons = {
        Predicate.ICMP_EQ: operator.eq, Predicate.ICMP_NE: operator.ne,
        Predicate.ICMP_SLT: operator.lt, Predicate.ICMP_SLE: operator.le,
        Predicate.ICMP_SGT: operator.gt, Predicate.ICMP_SGE: operator.ge,
        Predicate.ICMP_ULT: operator.lt, Predicate.ICMP_ULE: operator.le,
        Predicate.ICMP_UGT: operator.gt, Predicate.ICMP_UGE: operator.ge,
    }
    unsigned = {Predicate.ICMP_ULT, Predicate.ICMP_ULE,
                Predicate.ICMP_UGT, Predicate.ICMP_UGE}

    def integer_value(number, native_type, width):
        unsigned_number = number % (1 << width)
        signed_number = unsigned_number if unsigned_number < (1 << (width - 1)) else unsigned_number - (1 << width)
        return "integer", (signed_number, unsigned_number), native_type

    def checked_source(target=None):
        nonlocal source_nodes
        if re.search(r'^\s*#\s*(?:line\s+)?\d+', Path(file_name).read_text(), re.MULTILINE):
            return False
        if source_nodes is None:
            source_nodes = _source_loops(
                file_name, ("CallExpr", "CompoundStmt", "ForStmt", "VarDecl", "CompoundLiteralExpr"), bits)
        for function in visited_functions:
            members = [entry for entry in source_nodes if entry['linkage_name'] == function]
            scopes = [entry for entry in members if entry['kind'] in ("CompoundStmt", "ForStmt")]
            if not scopes:
                return False
            for declaration in members:
                if declaration['kind'] not in ("VarDecl", "CompoundLiteralExpr"):
                    continue
                point = (declaration['line'], declaration['column'])
                if sum((scope['line'], scope['column']) <= point < scope['end'] for scope in scopes) > 1:
                    return False
        if target is not None:
            matches = [call for call in source_nodes if call.get('callee') == 'reach_error'
                       and (call['line'], call['column']) == (target['line'], target['column'])]
            if len(matches) != 1:
                return False
            target['function'] = matches[0]['function']
        return True

    def prove_safe(kind):
        if proof_status is not None and nondet_reads == 0 and checked_source():
            proof_status.update(safe=True, kind=kind)

    def scalar_type(var):
        native_type = var.getType() if var is not None else None
        if native_type is not None:
            if native_type.isPointerTy():
                return "pointer", native_type
            if native_type.isIntegerType() and 0 < native_type.getByteSize() <= 8:
                return "integer", native_type
        return None

    def value_of(var, scope=None):
        kind = scalar_type(var)
        if kind is None:
            return None
        if isinstance(var, (pysvf.ConstIntValVar, pysvf.ConstIntObjVar)):
            return "integer", (var.getSExtValue(), var.getZExtValue()), kind[1]
        if isinstance(var, (pysvf.ConstNullPtrValVar, pysvf.ConstNullPtrObjVar)):
            return "pointer", None, kind[1]
        scope = values if scope is None else scope
        value = scope.get(var.getId(), globals_values.get(var.getId()))
        if value is not None and value[0] == "pointer":
            if value[1] is not None and value[1] not in objects:
                return None
        return value

    def execute(statement, global_init=False):
        nonlocal phi_previous, phi_values
        if not isinstance(statement, pysvf.PhiStmt):
            phi_previous = None
            phi_values = None
        if isinstance(statement, pysvf.AddrStmt):
            rhs = statement.getRHSVar()
            value = value_of(rhs)
            if value is None:
                obj = pag.getBaseObject(rhs.getId())
                kind = scalar_type(obj)
                if (obj is not None and kind is not None and obj.isConstantByteSize()
                        and (obj.isStack() or obj.isGlobalObj())):
                    address = (obj.getId(), frame_id if obj.isStack() else None)
                    objects[address] = kind[1].getByteSize()
                    if obj.isConstDataOrConstGlobal():
                        readonly_objects.add(address)
                    value = "pointer", address, statement.getLHSVar().getType()
            values[statement.getLHSVarID()] = value
            return value is not None or global_init
        if isinstance(statement, pysvf.CopyStmt):
            value = value_of(statement.getRHSVar())
            kind = scalar_type(statement.getLHSVar())
            if value is not None and kind is not None:
                if statement.isValueCopy() and value[2] == kind[1]:
                    values[statement.getLHSVarID()] = value
                    return True
                if value[0] == kind[0] == "integer":
                    cast = re.search(r'\b(trunc|sext|zext)\s+i(\d+)\b[^\n]*\bto\s+i(\d+)\b', statement.getLHSVar().toString())
                    if cast:
                        operation, source_width, result_width = cast.group(1), int(cast.group(2)), int(cast.group(3))
                        if not (0 < source_width <= 64 and 0 < result_width <= 64):
                            return False
                        if kind[1].getByteSize() != (result_width + 7) // 8:
                            return False
                        number = value[1][0] if operation == 'sext' else value[1][0] % (1 << source_width)
                        values[statement.getLHSVarID()] = integer_value(number, kind[1], result_width)
                        return True
                    signed_value, unsigned_value = value[1]
                    if statement.isZext() and unsigned_value is not None:
                        values[statement.getLHSVarID()] = (
                            "integer", (unsigned_value, unsigned_value), kind[1])
                        return True
                    if statement.isSext() and signed_value is not None:
                        values[statement.getLHSVarID()] = (
                            "integer", (signed_value, signed_value if signed_value >= 0 else None), kind[1])
                        return True
            values[statement.getLHSVarID()] = None
            return global_init
        if isinstance(statement, pysvf.BinaryOPStmt):
            left = value_of(statement.getOpVar(0))
            right = value_of(statement.getOpVar(1))
            kind = scalar_type(statement.getRes())
            if (left is None or right is None or kind is None or kind[0] != 'integer'
                    or (left[0], left[2]) != kind or (right[0], right[2]) != kind):
                return False
            operations = {pysvf.OpCode.Add: ('add', operator.add), pysvf.OpCode.Sub: ('sub', operator.sub),
                          pysvf.OpCode.Mul: ('mul', operator.mul), pysvf.OpCode.And: ('and', operator.and_),
                          pysvf.OpCode.Or: ('or', operator.or_), pysvf.OpCode.Xor: ('xor', operator.xor)}
            operation = operations.get(statement.getOpcode())
            if operation is None:
                return False
            instruction = re.search(r'\b' + operation[0] + r'\s+((?:(?:nsw|nuw)\s+)*)i(\d+)\b', statement.getRes().toString())
            if instruction is None:
                return False
            flags, width = instruction.group(1).split(), int(instruction.group(2))
            if not 0 < width <= 64 or kind[1].getByteSize() != (width + 7) // 8:
                return False
            signed_result = operation[1](left[1][0], right[1][0])
            unsigned_result = operation[1](left[1][0] % (1 << width), right[1][0] % (1 << width))
            if 'nsw' in flags and not -(1 << (width - 1)) <= signed_result < (1 << (width - 1)):
                return False
            if 'nuw' in flags and not 0 <= unsigned_result < (1 << width):
                return False
            values[statement.getResId()] = integer_value(unsigned_result, kind[1], width)
            return True
        if isinstance(statement, pysvf.StoreStmt):
            pointer = value_of(statement.getLHSVar())
            value = value_of(statement.getRHSVar())
            if pointer is None or pointer[0] != "pointer" or pointer[1] not in objects:
                return global_init
            if not global_init and pointer[1] in readonly_objects:
                return False
            if value is None or value[2].getByteSize() != objects[pointer[1]]:
                memory[pointer[1]] = None
                return global_init
            memory[pointer[1]] = value
            return True
        if isinstance(statement, pysvf.LoadStmt):
            pointer = value_of(statement.getRHSVar())
            kind = scalar_type(statement.getLHSVar())
            if pointer is None or pointer[0] != "pointer" or pointer[1] not in objects:
                return False
            value = memory.get(pointer[1])
            if value is None or kind is None or (value[0], value[2]) != kind:
                return False
            if value[0] == "pointer" and value[1] is not None and value[1] not in objects:
                return False
            values[statement.getLHSVarID()] = value
            return True
        if isinstance(statement, pysvf.CmpStmt):
            left = value_of(statement.getOpVar(0))
            right = value_of(statement.getOpVar(1))
            predicate = statement.getPredicate()
            if (left is None or right is None or (left[0], left[2]) != (right[0], right[2])
                    or predicate not in comparisons):
                return False
            if left[0] == "pointer":
                if predicate not in (Predicate.ICMP_EQ, Predicate.ICMP_NE):
                    return False
                left_value, right_value = left[1], right[1]
            else:
                view = 1 if predicate in unsigned else 0
                left_value, right_value = left[1][view], right[1][view]
                if left_value is None or right_value is None:
                    return False
            result = comparisons[predicate](left_value, right_value)
            values[statement.getResId()] = (
                "integer", (-1 if result else 0, int(result)),
                pag.getGNode(statement.getResId()).getType())
            return True
        if isinstance(statement, pysvf.CallPE):
            if not frames:
                return False
            call, caller_values, _ = frames[-1]
            operands = [index for index in range(statement.getOpVarNum())
                        if statement.getOpCallICFGNode(index) == call]
            if len(operands) != 1:
                return False
            value = value_of(pag.getGNode(statement.getOpVarId(operands[0])), caller_values)
            values[statement.getResId()] = value
            return value is not None
        if isinstance(statement, pysvf.PhiStmt):
            if phi_values is None:
                phi_previous = previous
                phi_values = values.copy()
            operands = [index for index in range(statement.getOpVarNum())
                        if statement.getOpICFGNode(index) == phi_previous]
            if statement.getOpVarNum() == 1:
                operands = [0]
            if len(operands) != 1:
                return False
            scope = values if statement.getOpVarNum() == 1 and re.search(
                r'(?m)^\s*ret\b', statement.toString()) else phi_values
            value = value_of(statement.getOpVar(operands[0]), scope)
            values[statement.getResId()] = value
            return value is not None
        if isinstance(statement, pysvf.RetPE):
            return value_of(statement.getLHSVar()) is not None
        if isinstance(statement, pysvf.SelectStmt):
            condition = value_of(statement.getCondition())
            if condition is None or condition[0] != 'integer' or condition[1][1] not in (0, 1):
                return False
            selected = statement.getTrueValue() if condition[1][1] else statement.getFalseValue()
            value = value_of(selected)
            values[statement.getResId()] = value
            return value is not None
        if isinstance(statement, pysvf.BranchStmt):
            return True
        if global_init and isinstance(statement, pysvf.GepStmt):
            values[statement.getLHSVarID()] = None
            return True
        return False

    global_statements = list(graph.getGlobalICFGNode().getSVFStmts())
    if len(global_statements) > 5000 or not all(execute(statement, True) for statement in global_statements):
        return None
    values = {}
    node = graph.getFunEntryICFGNode(main)
    previous = None
    visited = set()
    visited_functions = set()
    for _ in range(5000):
        if deadline is not None and time.process_time() >= deadline:
            return None
        if node is None:
            return None
        context = (node.getId(), tuple(call.getId() for call, _, _ in frames))
        state = (context, tuple(sorted(values.items())), tuple(sorted(globals_values.items())),
                 tuple(sorted(memory.items())), tuple(sorted(objects.items())), tuple(sorted(readonly_objects)),
                 tuple((call.getId(), scope, tuple(sorted(caller.items()))) for call, caller, scope in frames), frame_id)
        if state in visited:
            prove_safe('exact-state loop invariant')
            return None
        visited.add(state)
        if node.getFun() is not None:
            visited_functions.add(node.getFun().getName())
        if analysis.scope_exit_objects.get((previous, node)) and not checked_source():
            return None
        if not all(execute(statement) for statement in node.getSVFStmts()):
            return None
        if isinstance(node, pysvf.CallICFGNode):
            callee = node.getCalledFunction()
            if callee is not None and callee.getName() == "reach_error":
                segments = _target([(False, node)], file_name, max_line)
                if segments is None:
                    return None
                target = segments[0][0]
                if checked_source(target):
                    return segments
                return None
            if (callee is not None and callee.isDeclaration()
                    and callee.getName() in ('__VERIFIER_assume', 'llvm.assume')):
                arguments = node.getActualParms()
                if len(arguments) != 1:
                    return None
                condition = value_of(arguments[0])
                if condition is None or condition[0] != 'integer' or condition[1][0] == 0:
                    return None
                previous, node = node, node.getRetICFGNode()
                continue
            if callee is not None and nondet_choices and callee.getName().startswith('__VERIFIER_nondet_'):
                location = None if callee.isDeclaration() else parse_source_location(
                    graph.getFunEntryICFGNode(callee).getSourceLoc())
                appended = location is not None and max_line is not None and location['ln'] > max_line
                if callee.isDeclaration() or appended:
                    returned = node.getRetICFGNode().getActualRet()
                    kind = scalar_type(returned)
                    instruction = re.search(r'\bcall\b[^\n]*?\bi(\d+)\s+@', returned.toString()) if returned else None
                    if kind is None or kind[0] != 'integer' or instruction is None or node.getActualParms():
                        return None
                    width = int(instruction.group(1))
                    if not 0 < width <= 64 or kind[1].getByteSize() != (width + 7) // 8:
                        return None
                    chosen = nondet_choices[nondet_reads % len(nondet_choices)]
                    if callee.getName() == '__VERIFIER_nondet_bool' and chosen not in (0, 1):
                        return None
                    values[returned.getId()] = integer_value(chosen, kind[1], width)
                    nondet_reads += 1
                    previous, node = node, node.getRetICFGNode()
                    continue
            if callee is None or callee.isDeclaration() or pysvf.isExtCall(callee):
                return None
            if callee == main or (len(frames) >= 16 and any(
                    call.getCalledFunction() == callee for call, _, _ in frames)):
                return None
            frames.append((node, values, frame_id))
            values = {}
            frame_id = next_frame
            next_frame += 1
            previous, node = node, graph.getFunEntryICFGNode(callee)
            continue
        if isinstance(node, pysvf.FunExitICFGNode):
            if not frames:
                prove_safe('complete exact path')
                return None
            call = frames[-1][0]
            returns = [(statement.getLHSVarID(), value_of(statement.getRHSVar()))
                       for statement in call.getRetICFGNode().getSVFStmts() if isinstance(statement, pysvf.RetPE)]
            for address in [address for address in objects if address[1] == frame_id]:
                objects.pop(address)
                memory.pop(address, None)
            call, values, frame_id = frames.pop()
            values.update(returns)
            previous, node = node, call.getRetICFGNode()
            continue
        edges = list(node.getOutEdges())
        if any(not edge.isIntraCFGEdge() for edge in edges):
            return None
        if len(edges) == 1 and edges[0].getCondition() is None:
            previous, node = node, edges[0].getDstNode()
            continue
        if len(edges) != 2 or {edge.getSuccessorCondValue() for edge in edges} != {0, 1}:
            return None
        conditions = [edge.getCondition() for edge in edges]
        if any(condition is None for condition in conditions) or conditions[0] != conditions[1]:
            return None
        condition = value_of(conditions[0])
        if condition is None or condition[0] != "integer" or condition[1][1] not in (0, 1):
            return None
        edge = next(edge for edge in edges if edge.getSuccessorCondValue() == condition[1][1])
        previous, node = node, edge.getDstNode()
    return None


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
