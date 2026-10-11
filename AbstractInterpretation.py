from abc import abstractmethod

from pysvf import ICFG, ICFGNode
from typing import List, Dict, Set, Optional
import pysvf
import faulthandler
faulthandler.enable()
from util import *
import pysvf
from pysvf import IntervalValue, AddressValue, AbstractValue, AbstractState
import sys
from pysvf.enums import OpCode, Predicate

from enum import Enum

class AllocationCount(Enum):
    ZERO = 0
    ONE = 1
    MANY = 2

class Lifetime(Enum):
    ALLOCATED = 1
    MAY_FREED = 2
    FREED = 3

class UnknownException(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg 

    def __str__(self) -> str:
        return self.msg

class WTOCycleDepth:
    def __init__(self):
        self._heads: List[ICFGNode] = []

    def add(self, head: ICFGNode):
        self._heads.append(head)

    def __iter__(self):
        return iter(self._heads)

    def __str__(self):
        return f"{self._heads}"

    def __repr__(self):
        return f"{self._heads}"

    def compare(self, other):
        if self == other:
            return 0
        this_it = iter(self)
        other_it = iter(other)
        while this_it:
            if not other_it:
                return 1
            elif this_it == other_it:
                this_it = next(this_it)
                other_it = next(other_it)
            else:
                return 2
        if not other_it:
            return 0
        else:
            return -1

    def __lt__(self, other):
        return self.compare(other) == -1

    def __le__(self, other):
        return self.compare(other) <= 0

    def __eq__(self, other):
        return self.compare(other) == 0

    def __ge__(self, other):
        return self.compare(other) >= 0

    def __gt__(self, other):
        return self.compare(other) == 1



class ICFGWTOComp:
    def __init__(self, node: ICFGNode):
        self.node = node


    def getICFGNode(self) -> ICFGNode:
        return self.node

    @abstractmethod
    def accept(self, visitor):
        pass


class ICFGWTONode(ICFGWTOComp):
    def __init__(self, node: ICFGNode):
        self.node = node

    def accept(self, visitor):
        visitor.visitNode(self)


class ICFGWTOCycle(ICFGWTOComp):
    def __init__(self, head: ICFGWTONode, components: List[ICFGWTOComp]):
        self.head = head
        self.components = components

    def accept(self, visitor):
        visitor.visit(self)


class ICFGWTO:

    class WTOCycleDepthBuilder:
        def __init__(self, node_to_wto_cycle_depth):
            self.wto_cycle_depth = WTOCycleDepth()
            self.node_to_wto_cycle_depth = node_to_wto_cycle_depth

        def visit(self, cycle: ICFGWTOCycle):
            head = cycle.head.getICFGNode()
            previous_cycle_depth = self.wto_cycle_depth
            self.node_to_wto_cycle_depth[head] = self.wto_cycle_depth
            self.wto_cycle_depth = WTOCycleDepth()
            self.wto_cycle_depth.add(head)
            for component in cycle.components:
                component.accept(self)
            self.wto_cycle_depth = previous_cycle_depth

        def visitNode(self, node: ICFGWTONode):
            self.node_to_wto_cycle_depth[node.getICFGNode()] = self.wto_cycle_depth


    def __init__(self, graph: ICFG, entry: ICFGNode):
        self.graph = graph
        self.entry = entry
        self.components: List[ICFGWTOComp] = []
        self.all_components : Set[ICFGWTOComp] = set()
        self.head_ref_to_cycle: Dict[ICFGNode, ICFGWTOCycle] = {}
        self.node_to_depth: Dict[ICFGNode, int] = {}

        self._num = 0
        self._CDN: Dict[ICFGNode, int] = {}
        self._stack: List[ICFGNode] = []

    def init(self):
        self.visit(self.entry, self.components)
        self._CDN.clear()
        self._stack.clear()
        self.build_node_to_depth()


    def component(self, node: ICFGNode) -> ICFGWTOCycle:
        partition = []
        for succ in self.get_successors(node):
            if self._CDN.get(succ, 0) == 0:
                self.visit(succ, partition)
        head = ICFGWTONode(node)
        ptr = ICFGWTOCycle(head, partition)
        self.head_ref_to_cycle[node] = ptr
        return ptr


    def visit(self, node: ICFGNode, components: List[ICFGWTOComp]):
        head = 0 # CycleDepthNumber head(0)
        min = 0 # CycleDepthNumber min(0)
        loop = False # bool loop
        self._stack.append(node)    # push(node)
        self._num += 1  # _num += CycleDepthNumber(1)
        head = self._num # head = _num
        self._CDN[node] = head # setCDN(node, head)
        for succ in self.get_successors(node): # forEachSuccessor(node, [&](const NodeT* succ)
            succ_dfn = self._CDN.get(succ, 0) # CycleDepthNumber succ_dfn = getCDN(succ)
            if succ_dfn == 0: # if (succ_dfn == CycleDepthNumber(0))
                min = self.visit(succ, components) # min = visit(succ, partition)
            else:
                min = succ_dfn # min = succ_dfn
            if min <= head: # if (min <= head)
                head = min # head = min
                loop = True # loop = true

        if head == self._CDN[node]: # if (head == getCDN(node))
            self._CDN[node] = 0x7fffffff # setCDN(node, UINT_MAX)
            element = self._stack.pop()
            if loop:
                while element != node:
                    self._CDN[element] = 0 # setCDN(element, 0)
                    element = self._stack.pop() # element = pop()
                components.insert(0, self.component(node)) # partition.push_front(component(node))
            else:
                components.insert(0, ICFGWTONode(node)) # partition.push_front(newNode(node))
        return head


    def get_successors(self, node: ICFGNode) -> List[ICFGNode]:
        successors = []
        if isinstance(node, pysvf.CallICFGNode):
            return [node.getRetICFGNode()]
        else:
            for e in node.getOutEdges():
                if not e.isIntraCFGEdge() or node.getFun() != e.getDstNode().getFun():
                    continue
                else:
                    successors.append(e.getDstNode())
        return successors


    def build_node_to_depth(self):
        builder = self.WTOCycleDepthBuilder(self.node_to_depth)
        for component in self.components:
            component.accept(builder)


    def __str__(self):
        return f"ICFGWTO: {self.components}"



class AbstractExecutionHelper:
    """
    A helper class for abstract execution, providing functionality for bug reporting,
    managing GEP object offsets, and other utilities.
    """

    def __init__(self, svfir: pysvf.SVFIR, ae_manager):
        """
        Initialize member variables.
        """
        # Map a GEP objVar to its offset from the base address
        # Example: alloca [i32*10] x; lhs = gep x, 3
        # gep_obj_offset_from_base[lhs] = [12, 12]
        self.gep_obj_offset_from_base = {}

        # Map to store exception information for each ICFGNode
        self.node_to_bug_info = {}
        self.svfir = svfir
        self.ae_manager = ae_manager

        self.bug_reports = {
            "Buffer Overflow": [],
            "Null Pointer Dereference": [],
            "Use After Free": [],
            "Double Free": [],
            "Memory Leak": [],
            "Bad Free": []
        }
    
    def _register_bug(self, category: str, node, msg: str):
        """Internal helper to ensure all bugs are recorded consistently."""
        self.node_to_bug_info[node] = msg
        self.bug_reports[category].append((node, msg))

    def reportBufOverflow(self, node, msg):
        self._register_bug("Buffer Overflow", node, msg)

    def reportNullDereference(self, node, msg):
        self._register_bug("Null Pointer Dereference", node, msg)

    def reportUseAfterFree(self, node, msg):
        self._register_bug("Use After Free", node, msg)

    def reportDoubleFree(self, node, msg):
        self._register_bug("Double Free", node, msg)

    def reportMemoryLeak(self, node, msg):
        self._register_bug("Memory Leak", node, msg)

    def reportBadFree(self, node, msg):
        self._register_bug("Bad Free", node, msg)

    def printReport(self):
        
        total_bugs = len(self.node_to_bug_info)
        if total_bugs == 0:
            print("No memory safety violations detected. Program is safe!")
            print("=======================================================\n")
            return

        print(f"Total Memory Safety Violations Found: {total_bugs}\n")
        
        for category, reports in self.bug_reports.items():
            if len(reports) > 0:
                print(f"###################### {category} ({len(reports)} found) ######################")
                print("---------------------------------------------")
                for node, msg in reports:
                    print(f"{node}: {msg}")
                    print("---------------------------------------------")
                print()


    def updateGepObjOffsetFromBase(self, abstractState: pysvf.AbstractState, gepAddrs: pysvf.AddressValue, objAddrs: pysvf.AddressValue, offset: pysvf.IntervalValue):
        """
        Update the GEP object offset from the base address.

        :param gepAddrs: List of GEP address values.
        :param objAddrs: List of object address values.
        :param offset: IntervalValue representing the offset.
        """
        for obj_addr in objAddrs:
            obj_id = abstractState.getIDFromAddr(obj_addr)
            obj = self.svfir.getGNode(obj_id)
            if isinstance(obj, pysvf.BaseObjVar):
                for gep_addr in gepAddrs:
                    gep_obj = abstractState.getIDFromAddr(gep_addr)
                    gep_obj_var = self.svfir.getGNode(gep_obj)
                    self.addToGepObjOffsetFromBase(gep_obj_var, offset)
            elif isinstance(obj, pysvf.GepObjVar):
                obj_var = obj
                for gep_addr in gepAddrs:
                    gep_obj = abstractState.getIDFromAddr(gep_addr)
                    gep_obj_var = self.svfir.getGNode(gep_obj)
                    if self.hasGepObjOffsetFromBase(obj_var):
                        obj_offset_from_base = self.getGepObjOffsetFromBase(obj_var)
                        # Ensure gep_obj_var has not been written before
                        if not self.hasGepObjOffsetFromBase(gep_obj_var):
                            self.addToGepObjOffsetFromBase(gep_obj_var, obj_offset_from_base + offset)
                    else:
                        raise AssertionError("gepRhsObjVar has no gepObjOffsetFromBase")


    def handleMemcpy(self, abstractState: pysvf.AbstractState, dst: pysvf.SVFVar,
                     src: pysvf.SVFVar, len: pysvf.IntervalValue, start_idx: int, node):
        """
        Handle a memcpy operation in the abstract state.
        """
        dstId = dst.getId()
        srcId = src.getId()
        elemSize = 1
        if isinstance(dst, pysvf.ValVar):
            if dst.getType().isArrayTy():
                elemSize = dst.getType().getTypeOfElement().getByteSize()
            elif dst.getType().isPointerTy():
                elemType = self.ae_manager.getPointeeElement(dst, node)
                if elemType.isArrayTy():
                    elemSize = elemType.getTypeOfElement().getByteSize()
                else:
                    elemSize = elemType.getByteSize()
            else:
                raise AssertionError("Unsupported type")
        size = len.lb().getNumeral()
        range_val = size/elemSize
        if abstractState.inVarToAddrsTable(dstId) and abstractState.inVarToAddrsTable(srcId):
            self.ae_manager.updateAbsState(node, abstractState)
            for index in range(0, int(range_val)):
                expr_src = self.ae_manager.getGepObjAddrs(src, pysvf.IntervalValue(index))
                expr_dst = self.ae_manager.getGepObjAddrs(dst, pysvf.IntervalValue(index + start_idx))
                for addr_src in expr_src:
                    for addr_dst in expr_dst:
                        objId = abstractState.getIDFromAddr(addr_src)
                        if objId in abstractState.getLocToVal():
                            lhs = abstractState.load(addr_src)
                            abstractState.store(addr_dst, lhs)


    def getStrlen(self, abstractState, strValue, node):
        """
        Calculate the length of a string in the abstract state.

        :param abstractState: The abstract state containing variable information.
        :param strValue: The SVF variable representing the string.
        :return: An IntervalValue representing the string length.
        """
        value_id = strValue.getId()
        dst_size = 0

        # Determine the size of the destination object
        for addr in abstractState[value_id].getAddrs():
            obj_id = abstractState.getIDFromAddr(addr)
            base_object = self.svfir.getBaseObject(obj_id)

            if base_object.isConstantByteSize():
                dst_size = base_object.getByteSizeOfObj()
            else:
                icfg_node = base_object.getICFGNode()
                for stmt in icfg_node.getSVFStmts():
                    if isinstance(stmt, pysvf.AddrStmt):
                        dst_size = self.ae_manager.getAllocaInstByteSize(stmt)

        length = 0
        elem_size = 1

        # Calculate the string length
        if abstractState.getVar(value_id).isAddr():
            self.ae_manager.updateAbsState(node, abstractState)
            for index in range(dst_size):
                expr0 = self.ae_manager.getGepObjAddrs(strValue, pysvf.IntervalValue(index))
                val = pysvf.AbstractValue()

                for addr in expr0:
                    val.join_with(abstractState.load(addr))

                if val.isInterval() and chr(val.getInterval().getIntNumeral()) == '\0':
                    break

                length += 1

            # Determine the size of each element in the string
            if strValue.getType().isArrayTy():
                elem_size = strValue.getType().getTypeOfElement().getByteSize()
            elif strValue.getType().isPointerTy():
                elem_type = self.ae_manager.getPointeeElement(strValue, node)
                if elem_type:
                    if elem_type.isArrayTy():
                        elem_size = elem_type.getTypeOfElement().getByteSize()
                    else:
                        elem_size = elem_type.getByteSize()
                else:
                    elem_size = 1
            else:
                raise AssertionError("Unsupported type")

        # Return the calculated string length as an IntervalValue
        if length == 0:
            return pysvf.IntervalValue(0, pysvf.Options.max_field_limit())
        else:
            return pysvf.IntervalValue(length * elem_size)

    def addToGepObjOffsetFromBase(self, obj, offset):
        """
        Add a GEP object variable and its offset from the base address.

        :param obj: The GEP object variable.
        :param offset: The offset as an IntervalValue.
        """
        self.gep_obj_offset_from_base[obj] = offset

    def hasGepObjOffsetFromBase(self, obj):
        """
        Check if a GEP object variable has an offset from the base address.

        :param obj: The GEP object variable.
        :return: True if the offset exists, False otherwise.
        """
        return obj in self.gep_obj_offset_from_base

    def getGepObjOffsetFromBase(self, obj):
        """
        Get the offset of a GEP object variable from the base address.

        :param obj: The GEP object variable.
        :return: The offset as an IntervalValue.
        :raises AssertionError: If the object is not found.
        """
        if obj not in self.gep_obj_offset_from_base:
            raise AssertionError(f"Object {obj} not found in gep_obj_offset_from_base")
        else:
            return self.gep_obj_offset_from_base[obj]


class AbstractExecution:
    def __init__(self, pag: pysvf.SVFIR):
        self.svfir = pag
        self.icfg = pag.getICFG()
        self.call_site_stack = []
        self.func_to_wto = {}
        self.recursive_funs = set()
        self.pre_abs_trace = {}
        self.post_abs_trace = {}
        self.ae_manager = pysvf.AbstractInterpretation.getAEInstance()
        self.buf_overflow_helper = AbstractExecutionHelper(self.svfir, self.ae_manager)
        self.assert_points = set()
        self.widen_delay = 3
        self.addressMask = 0x7f000000
        self.flippedAddressMask = (self.addressMask^0xffffffff)


        #mem safety stuff
        #this is used to map allocated memory to its state, ALLOCATED, and FREED
        self.node_to_alloc_state = {}

        # Lifetime abstract state before/after each ICFG node
        # node -> {heap_obj_id: Lifetime}
        self.pre_lifetime_trace = {}
        self.post_lifetime_trace = {}

        #used for tracking offsets for pointers
        self.pre_ptr_offset_trace = {}   # node -> {var_id: IntervalValue}
        self.post_ptr_offset_trace = {}  # node -> {var_id: IntervalValue}

        # Allocation abstract state before/after each ICFG node
        self.pre_alloc_count_trace = {}
        self.post_alloc_count_trace = {}

        # For calls whose body is skipped, analogous to skipped_states
        self.skipped_lifetime_states = {}

        ###SVF SV-COMP-ADDITION
        # storing results here for now, feel free to replace or update how we store it
        self.results = {}
        self.results["reach"] = []
        self.results["bufferoverflow"] = []

        # Stores dropped paths
        self.results["incomplete"] = []
        # Functions actually entered
        self.visited = set()
        # Nodes handleICFGNode visited and proved infeasible.
        self.infeasible_nodes = set()
        # (node, result var) of comparisons we had no model for; deduped
        self.unmodelled_cmps = set()
        # Nodes that reached the merge with no predecessor state.
        self.orphan_nodes = set()
        # Stores unreachable nodes -> nodes proven dead
        self.unreachable_nodes = set()
        # Ret node -> state carried over from its call node when the function body is not analysed.
        self.skipped_states = {}

        self.results["memoryleak"] = []
        self.results["nulldereference"] = []
        self.results["useafterfree"] = []
        self.results["doublefree"] = []
        self.results["badfree"] = []

    """
    Initialize the WTO (Weak topological order) for each function.
    """
    def initWto(self):
        callgraphScc = pysvf.getCallGraphSCC()
        for node in self.svfir.getCallGraph().getNodes():
            if callgraphScc.isInCycle(node.getId()):
                self.recursive_funs.add(node.getFunction())
            fun = node.getFunction()
            assert isinstance(fun, pysvf.FunObjVar)
            if fun.isDeclaration():
                continue
            wto = ICFGWTO(self.icfg, self.icfg.getFunEntryICFGNode(fun))
            wto.init()
            self.func_to_wto[fun] = wto
            
        # Build mapping from cycle head nodes to their corresponding cycles
        self.cycle_head_to_cycle = {}
        
        #Recursively extract ALL cycles, including nested inner loops
        def extract_cycles(components):
            for comp in components:
                if isinstance(comp, ICFGWTOCycle):
                    self.cycle_head_to_cycle[comp.head.node] = comp
                    extract_cycles(comp.components)
                    
        for fun, wto in self.func_to_wto.items():
            extract_cycles(wto.components)


    """
    Placeholder for additional documentation or functionality.
    """
    def getVirtualMemAddress(self, idx: int) -> int:
        return self.addressMask + idx
    
    def joinPtrOffsetMaps(self, dst: Dict[int, pysvf.AbstractValue], src: Dict[int, pysvf.AbstractValue]):
        """ Safely join dictionary-based offset traces """
        for var_id, src_val in src.items():
            if var_id not in dst:
                dst[var_id] = src_val.clone()
            else:
                dst[var_id].join_with(src_val)


    """
    Handle the global ICFG node by initializing its abstract state and updating it based on its statements.

    This function performs the following steps:
    1. Initializes the abstract state for the global ICFG node in both pre- and post-abstract traces.
    2. Sets the initial value of variable 0 to an address value of 0.
    3. Iterates through all statements in the global ICFG node and updates the abstract state accordingly.
    """
    def handleGlobalNode(self):
        global_node = self.icfg.getGlobalICFGNode()

        self.post_abs_trace[global_node] = AbstractState()
        self.pre_abs_trace[global_node] = self.post_abs_trace[global_node]
        self.post_abs_trace[global_node][0]  = AbstractValue(AddressValue(set()))

        self.pre_lifetime_trace[global_node] = {}
        self.post_lifetime_trace[global_node] = {}

        # Initialize the offset trace natively as standard Python dictionaries
        self.pre_ptr_offset_trace[global_node] = {}
        self.post_ptr_offset_trace[global_node] = {}

        global_state = self.post_abs_trace[self.icfg.getGlobalICFGNode()]
        global_state[0] = AbstractValue(AddressValue(set()))

        for var_id, var in self.svfir:
            if var.isValVar():
                val_var = var.asValVar()
                if val_var.isConstNullPtrValVar():
                    global_state[var_id] = AbstractValue(AddressValue(pysvf.NullMemAddr))
                elif val_var.isConstIntValVar():
                    global_state[var_id] = AbstractValue(IntervalValue(val_var.asConstIntValVar().getSExtValue()))

        for stmt in self.icfg.getGlobalICFGNode().getSVFStmts():
            self.updateAbsState(stmt)


    """
    Handle the WTO (Weak Topological Order) components.
    This function iterates through the WTO components and handles them based on their type.
    It calls the appropriate helper function for each component, such as handle_singleton_wto or handleCycleWto.
    """
    def handleWtoComponents(self, wtoComps):
        for comp in wtoComps:
            if isinstance(comp, ICFGWTONode):
                # Unwrap the node before passing it
                self.handleICFGNode(comp.node)
            elif isinstance(comp, ICFGWTOCycle):
                # Call the correct cycle handler
                self.handleICFGCycle(comp)

    """
    Handle a function in the ICFG using WTO components and worklist algorithm.
    
    This function processes a function by:
    1. Building a set of WTO components for the function
    2. Using a worklist algorithm to process nodes in topological order
    3. Handling cycles and singleton nodes appropriately
    4. Managing the flow between different components
    """
    def handleFunction(self, funEntry: pysvf.ICFGNode):
        fun = funEntry.getFun()
        if fun is not None:
            self.visited.add(fun.getName())
            
        wto = self.func_to_wto.get(fun)
        if wto:
            # Structurally delegate all traversal to the WTO components
            self.handleWtoComponents(wto.components)

    """
    Get the next nodes of a given ICFG node.
    
    This function returns the successor nodes of a given ICFG node by examining
    its outgoing edges. It handles both intra-procedural edges and call-return edges.
    
    :param node: The ICFG node whose successors are to be found
    :type node: pysvf.ICFGNode
    :return: List of successor nodes
    :rtype: List[pysvf.ICFGNode]
    """
    def getNextNodes(self, node: pysvf.ICFGNode) -> List[pysvf.ICFGNode]:
        out_edges = []
        for edge in node.getOutEdges():
            dst = edge.getDstNode()
            if dst.getFun() == node.getFun():
                out_edges.append(dst)
        
        # Handle call-return edges
        if isinstance(node, pysvf.CallICFGNode):
            ret_node = node.getRetICFGNode()
            out_edges.append(ret_node)
        
        return out_edges

    """
    Get the next nodes of a cycle.
    
    This function returns the next nodes of a cycle by iterating through the cycle's components.
    The next nodes of a cycle are the next nodes of the cycle nodes (including cycle head and cycle components)
    that are located outside the cycle.
    
    Inner cycles are skipped because their next nodes cannot be outside the outer cycle.
    Only the next nodes of cycle nodes that point to nodes outside the cycle are included in cycleNext.
    
    :param cycle: The WTO cycle whose next nodes are to be found
    :type cycle: ICFGWTOCycle
    :return: List of next nodes that are outside the cycle
    :rtype: List[pysvf.ICFGNode]
    """
    def getNextNodesOfCycle(self, cycle: ICFGWTOCycle) -> List[pysvf.ICFGNode]:
        cycle_nodes = set()
        
        # Recursively collect every single node inside the entire cycle structure
        def collect_nodes(c: ICFGWTOCycle):
            cycle_nodes.add(c.head.node)
            for comp in c.components:
                if isinstance(comp, ICFGWTONode):
                    cycle_nodes.add(comp.node)
                elif isinstance(comp, ICFGWTOCycle):
                    collect_nodes(comp)
                    
        collect_nodes(cycle)
        
        out_edges = []
        
        # Any edge coming from a node inside the cycle pointing to a node
        # OUTSIDE the cycle is a valid exit path.
        for node in cycle_nodes:
            for next_node in self.getNextNodes(node):
                if next_node not in cycle_nodes:
                    out_edges.append(next_node)
                    
        return out_edges


    """
    Handle a singleton WTO
    This function handles a node in the ICFG by merging the abstract states of its predecessors,
    updating the abstract state based on the node's statements, and handling stub functions.
    It also checks if the abstract state has reached a fixpoint and returns the result.
    Return true means the abstract state has changed
    Return false means the abstract state has reached a fixpoint or is infeasible
    
    """
    def handleICFGNode(self, node: pysvf.ICFGNode):
        is_feasible, self.pre_abs_trace[node] = self.mergeStatesFromPredecessors(node)

        if isinstance(node, pysvf.CallICFGNode):
            callNode = node.asCall()
            # An indirect call SVF could not resolve has no callee
            callee = callNode.getCalledFunction()
            if callee is not None and callee.getName() == "reach_error":
                self.results["reach"].append((is_feasible, callNode))

        if not is_feasible:
            self.infeasible_nodes.add(node)
            return False

        self.infeasible_nodes.discard(node)
        
        last_as = self.post_abs_trace[node] if node in self.post_abs_trace else None
        last_lifetime = self.post_lifetime_trace[node].copy() if node in self.post_lifetime_trace else None
        last_alloc_count = self.post_alloc_count_trace[node].copy() if node in self.post_alloc_count_trace else None
        
        last_ptr_offsets = {}
        if node in self.post_ptr_offset_trace:
            for k, v in self.post_ptr_offset_trace[node].items():
                last_ptr_offsets[k] = v.clone()

        self.post_abs_trace[node] = self.pre_abs_trace[node]
        self.post_lifetime_trace[node] = self.pre_lifetime_trace.get(node, {}).copy()
        self.post_alloc_count_trace[node] = self.pre_alloc_count_trace.get(node, {}).copy()
        
        self.post_ptr_offset_trace[node] = {}
        for k, v in self.pre_ptr_offset_trace.get(node, {}).items():
            self.post_ptr_offset_trace[node][k] = v.clone()

        try:
            self.ae_manager.updateAbsState(node, self.pre_abs_trace[node])
        except Exception:
            pass
        
        for stmt in node.getSVFStmts():
            self.updateAbsState(stmt)

        if isinstance(node, pysvf.CallICFGNode):
            self.handleCallSite(node)
        
        abs_unchanged = (last_as is not None and self.post_abs_trace[node] == last_as)
        lifetime_unchanged = (last_lifetime is not None and self.post_lifetime_trace[node] == last_lifetime)
        alloc_count_unchanged = (last_alloc_count is not None and self.post_alloc_count_trace[node] == last_alloc_count)
        
        ptr_offsets_unchanged = True
        if last_ptr_offsets is None:
            ptr_offsets_unchanged = False
        else:
            for k, v in self.post_ptr_offset_trace[node].items():
                old_v = last_ptr_offsets.get(k)
                if old_v is None or not old_v.getInterval().equals(v.getInterval()):
                    ptr_offsets_unchanged = False
                    break

        if abs_unchanged and lifetime_unchanged and alloc_count_unchanged and ptr_offsets_unchanged:
            return False
        
        return True
    
    """
    Handle a call site in the control flow graph
    
    This function processes a call site by updating the abstract state, handling the called function,
    and managing the call stack. It resumes the execution state after the function call.
    return void
    """

    ###SVF SV-COMP-ADDITION
    # The SV-COMP verification harness only. Anything absent records a gap, so the verdict
    # degrades to Unknown.
    SAFE_EXTERNALS = {
        "abort", "exit", "_exit",
        "__assert_fail", "__assert", "__assert_perror_fail",
        "reach_error", "__VERIFIER_error",
    }

    # Externals that write to a stream and never to program memory. The
    # exception is printf("%n"), which SV-COMP tasks do not use. Anything that writes
    # through a pointer argument (sprintf, snprintf, memcpy, scanf) must stay out.
    PURE_EXTERNALS = {
        "printf", "fprintf", "vprintf", "vfprintf", "puts", "fputs", "putchar",
        "fputc", "putc", "fflush", "perror",
    }

    # The SV-COMP harness writes every input constraint as assume_abort_if_not(cond):
    # the callee aborts unless cond holds, so any continuation in the caller implies it
    # did.
    ASSUME_HELPERS = {"assume_abort_if_not", "__VERIFIER_assume"}

    # Memory functions, modelled assuming the program is memory safe
    MEMORY_EXTERNALS = ("malloc", "llvm.stacksave", "llvm.stackrestore", "llvm.memcpy")

    # stacksave and stackrestore have suffix, matched by prefix
    # to cover overload suffixes (.p0, .i32).
    def isMemoryExternal(self, fun_name: str) -> bool:
        return any(fun_name == name or fun_name.startswith(name + ".")
                   for name in self.MEMORY_EXTERNALS)

    def handleMemoryCall(self, node: pysvf.CallICFGNode, fun_name: str):
        # Check to see if its been broken down by svf simple for now
        # Record a gap if we couldnt find a lowered version
        if fun_name.startswith("llvm.memcpy") and not any(
                isinstance(stmt, pysvf.StoreStmt) for stmt in node.getSVFStmts()):
            self.recordGap(f"memcpy not lowered by SVF: {fun_name}")
            self.resumeAfterUnanalysedCall(node)

    def computeUnreachableNodes(self):
        """Nodes with no live path in: every incoming edge comes from an unreachable node.
        Starts from the infeasible nodes and propagates forward. Analysed nodes are excluded.
        """
        unreachable = {node for node in self.infeasible_nodes
                       if node not in self.post_abs_trace}
        # Nodes with no in-edges are unreachable unless they're a walk start point.
        # Add them to the starting set, since propagation can't discover them.
        for node in self.icfg.getNodes():
            if node in self.post_abs_trace or node in unreachable:
                continue
            if isinstance(node, (pysvf.FunEntryICFGNode, pysvf.GlobalICFGNode)):
                continue
            if not list(node.getInEdges()):
                unreachable.add(node)
        worklist = list(unreachable)
        while worklist:
            node = worklist.pop()
            successors = [edge.getDstNode() for edge in node.getOutEdges()]
            if isinstance(node, pysvf.CallICFGNode):
                successors.append(node.getRetICFGNode())
            for dst in successors:
                if dst is None or dst in self.post_abs_trace or dst in unreachable:
                    continue
                if self.isUnreachableGiven(dst, unreachable):
                    unreachable.add(dst)
                    worklist.append(dst)
        return unreachable

    def isUnreachableGiven(self, node: pysvf.ICFGNode, unreachable) -> bool:
        """True when every way of arriving at `node` is already known unreachable."""
        if isinstance(node, pysvf.RetICFGNode):
            call = node.getCallICFGNode()
            if call is not None and call in unreachable:
                return True
        in_edges = list(node.getInEdges())
        return bool(in_edges) and all(e.getSrcNode() in unreachable for e in in_edges)

    def finaliseGaps(self):
        """Turn the deferred orphans into gaps, keeping only those that are not proofs."""
        self.unreachable_nodes = self.computeUnreachableNodes()
        for block in self.orphan_nodes:
            if block in self.post_abs_trace:
                continue  # a later iteration gave it a state after all
            pending = [edge.getSrcNode() for edge in block.getInEdges()
                       if edge.getSrcNode() not in self.post_abs_trace
                       and edge.getSrcNode() not in self.unreachable_nodes]
            if pending:
                self.recordGap(f"node {block.getId()} has {len(pending)} "
                               f"unanalysed predecessor(s)")

    def recordGap(self, reason: str):
        """Record that the analysis gave up"""
        self.results["incomplete"].append(reason)

    def markCallNeverReturns(self, node: pysvf.CallICFGNode):
        """The callee cannot return, so the code after the call is unreachable, not missing."""
        ret = node.getRetICFGNode()
        if ret is not None and ret not in self.post_abs_trace:
            self.infeasible_nodes.add(ret)

    def resumeAfterUnanalysedCall(self, node: pysvf.CallICFGNode):
        """Continue analysis past a call whose body we didn't analyse.

        Stages the caller's state for the ret node, with the return value set to top
        (callee's result unknown). Stored in `skipped_states`, not the trace, since a
        pre-filled trace entry would look like a fixpoint and stop the walk.
        """
        ret = node.getRetICFGNode()
        if ret is None or node not in self.post_abs_trace:
            return
        state = self.post_abs_trace[node].clone()
        actual_ret = ret.getActualRet()
        if actual_ret is not None:
            state[actual_ret.getId()] = AbstractValue(IntervalValue.top())
        self.skipped_states[ret] = state
        self.skipped_lifetime_states[ret] = (
            self.post_lifetime_trace.get(node, {}).copy()
        )

    def cmpVarBehind(self, var, depth: int = 4):
        """Walk back through value-preserving copies to the comparison that produced `var`.
        Returns None if no comparison is found (no narrowing is possible).

        Used by applyAssumption for ASSUME_HELPERS such as __VERIFIER_assume(x < 5). Clang
        widens the i1 compare to the parameter's type, so the call argument is a CopyStmt
        rather than a CmpStmt. zext of an i1 is 0 or 1 and sext is 0 or -1, so in both cases
        "argument is non-zero" is exactly "the comparison held".
        """
        for _ in range(depth):
            if var is None:
                return None
            edges = var.getInEdges()
            if not edges:
                return None
            edge = edges[0]
            if isinstance(edge, pysvf.CmpStmt):
                return var
            if isinstance(edge, pysvf.CopyStmt) and (
                    edge.isZext() or edge.isSext() or edge.isValueCopy()):
                var = edge.getRHSVar()
                continue
            return None
        return None

    def applyAssumption(self, node: pysvf.CallICFGNode) -> bool:
        """Apply an assume helper's constraint to the *caller's* state.
        Returns False when the assumption cannot hold, i.e. the helper aborts on every
        path in, so the code after the call is dead.
        """
        if node not in self.post_abs_trace:
            # Fail safe case
            return True
        parms = node.getActualParms()
        if len(parms) != 1:
            return True
        cmp_var = self.cmpVarBehind(parms[0])
        if cmp_var is None:
            # Not a comparison we can take apart -- an already-widened flag, a phi merge
            # from `&&` (3.4), or a call result. Sound, just no narrowing.
            return True
        if self.refineOnBranch(cmp_var, 1, self.post_abs_trace[node]):
            return True
        self.markCallNeverReturns(node)
        return False

    def handleCallSite(self, node: pysvf.CallICFGNode):
        callee = node.getCalledFunction()
        
        # Handle Indirect Calls
        if callee is None:
            has_indirect = False
            for edge in node.getOutEdges():
                # Identify interprocedural call edges
                if not edge.isIntraCFGEdge() and node.getFun() and edge.getDstNode().getFun() != node.getFun():
                    target_func = edge.getDstNode().getFun()
                    if target_func:
                        has_indirect = True
                        target_name = target_func.getName()
                        
                        # Break indirect cycles using absolute string identity
                        if target_name not in self.call_site_stack:
                            self.call_site_stack.append(target_name)
                            self.handleFunction(self.svfir.getICFG().getFunEntryICFGNode(target_func))
                            self.call_site_stack.pop()
                        else:
                            self.recordGap(f"recursive indirect function body not analysed: {target_name}")
                            self.resumeAfterUnanalysedCall(node)
            
            if not has_indirect:
                # Unresolved indirect call: there is no callee to walk, so this is a dropped path
                # rather than a no-op and recorded.
                self.recordGap(f"unresolved indirect call at node {node.getId()}")
                self.resumeAfterUnanalysedCall(node)
                if node.getRetICFGNode() and node.getRetICFGNode().getActualRet():
                    lhs_id = node.getRetICFGNode().getActualRet().getId()
                    self.post_abs_trace[node][lhs_id] = pysvf.AbstractValue(pysvf.IntervalValue.top())
            return
            
        # Handle Direct Calls
        fun_name = callee.getName()
        print(fun_name)
        
        # Narrow the caller before the body is walked; the body is then analysed as usual,
        # because the return node takes its state from the callee's exit.
        if fun_name in self.ASSUME_HELPERS and not self.applyAssumption(node):
            return

        if fun_name in ["OVERFLOW", "svf_assert", "svf_assert_eq"]:
            self.handleStubFunction(node)
        elif fun_name in ["nd", "rand"]:
            if node.getRetICFGNode() and node.getRetICFGNode().getActualRet():
                lhs_id = node.getRetICFGNode().getActualRet().getId()
                self.post_abs_trace[node][lhs_id] = AbstractValue(IntervalValue.top())
        elif fun_name in ["mem_insert", "str_insert", "malloc", "free", "calloc", "realloc"]: 
            self.updateStateOnExtCall(node)
        elif pysvf.isExtCall(callee):
            # The body is never walked, so the callee's exit gets no state,
            # deal with it here.
            if fun_name in self.SAFE_EXTERNALS:
                self.markCallNeverReturns(node)
            elif fun_name in self.ASSUME_HELPERS:
                # applyAssumption has already applied to the caller's state: resume with it, no gap.
                self.resumeAfterUnanalysedCall(node)
            elif fun_name in self.PURE_EXTERNALS:
                # No effect on program memory: resume with the caller's state, no gap.
                self.resumeAfterUnanalysedCall(node)
            elif self.isMemoryExternal(fun_name):
                self.handleMemoryCall(node, fun_name)
            else:
                self.recordGap(f"external call not modelled: {fun_name}")
                self.resumeAfterUnanalysedCall(node)
        # Break direct recursive cycles using absolute string identity
        elif callee in self.recursive_funs or fun_name in self.call_site_stack:
            self.recordGap(f"recursive function body not analysed: {fun_name}")
            self.resumeAfterUnanalysedCall(node)
            return
        else:
            fun_entry = self.svfir.getICFG().getFunEntryICFGNode(callee)
            old_entry_state = self.post_abs_trace.get(fun_entry)
            
            # Fast-path: Only analyze the callee if the incoming state shifted
            is_feasible, merged_as = self.mergeStatesFromPredecessors(fun_entry)
            if not is_feasible:
                return
                
            if old_entry_state is None or merged_as != old_entry_state:
                self.call_site_stack.append(fun_name)
                self.handleFunction(fun_entry)
                self.call_site_stack.pop()

    """
    Handle stub functions such as 'svf_assert' and 'OVERFLOW'.

    This function processes specific stub functions in the program's control flow graph (CFG) 
    to validate assertions or detect buffer overflows. It performs the following tasks:

    1. For 'svf_assert':
       - Adds the call node to the set of assertion points.
       - Checks the abstract state of the argument to determine if the assertion is valid.
       - If the assertion is invalid or unsatisfiable, raises an error.

    2. For 'OVERFLOW':
       - Adds the call node to the set of assertion points.
       - Checks if the right-hand side (RHS) value is an address.
       - Iterates through the addresses to calculate the access offset and compare it 
         with the object size to detect buffer overflows.
       - If a buffer overflow is detected, records the overflow node and prints a success message.
       - If no overflow is detected, raises an error.

    :param call_node: The call node representing the stub function in the CFG.
    :type call_node: pysvf.CallICFGNode
    """
    def handleStubFunction(self, callNode: pysvf.CallICFGNode):
        # Get the callee function associated with the call site
        if callNode.getCalledFunction().getName() == "svf_assert":
            self.assert_points.add(callNode)
            # If the condition is false, the program is infeasible
            arg0 = callNode.getArgument(0).getId()
            abstract_state = self.post_abs_trace[callNode]

            # Check if the interval for the argument is infinite
            if abstract_state[arg0].getInterval().isTop():
                print(f"svf_assert Fail. {callNode}")
                assert False
            else:
                if (abstract_state[arg0].getInterval().equals(IntervalValue(1, 1)) or
                        abstract_state[arg0].getInterval().equals(IntervalValue(-1, -1))):
                    print(f"The assertion ({callNode}) is successfully verified!!")
                else:
                    print(f"The assertion ({callNode}) is unsatisfiable!!")
                    assert False

        elif callNode.getCalledFunction().getName() == "OVERFLOW":
            # If the condition is false, the program is infeasible
            self.assert_points.add(callNode)
            arg0 = callNode.getArgument(0).getId()
            arg1 = callNode.getArgument(1).getId()

            abstract_state = self.post_abs_trace[callNode]
            gep_rhs_val = abstract_state[arg0]

            # Check if the RHS value is an address
            if gep_rhs_val.isAddr():
                overflow = False
                for addr in gep_rhs_val.getAddrs():
                    access_offset = abstract_state[arg1].getInterval().getIntNumeral()
                    obj_id = abstract_state.getIDFromAddr(addr)
                    gep_lhs_obj_var = self.svfir.getGNode(obj_id).asGepObjVar()
                    size = self.svfir.getBaseObject(obj_id).getByteSizeOfObj()

                    if self.buf_overflow_helper.hasGepObjOffsetFromBase(gep_lhs_obj_var):
                        overflow = (
                                int(self.buf_overflow_helper.getGepObjOffsetFromBase(gep_lhs_obj_var).ub())
                                + access_offset >= size
                        )
                        if overflow:
                            print("obj len: {}, you want to access: {}.".format(size, access_offset))
                    else:
                        raise AssertionError("Pointer not found in gepObjOffsetFromBase")

                if overflow:
                    print("Your implementation successfully detected the buffer overflow")
                else:
                    print(f"Your implementation failed to detect the buffer overflow! {callNode}")
                    assert False
            else:
                print(f"Your implementation failed to detect the buffer overflow! {callNode}")
                assert False
    """
    Join Lifetime
    """
    def joinLifetime(self, lhs: Lifetime, rhs: Lifetime) -> Lifetime:
        if lhs == rhs:
            return lhs

        # disagreement means the object may or may not be freed
        return Lifetime.MAY_FREED

    def joinLifetimeMaps(self, dst, src):
        for obj_id, src_state in src.items():
            if obj_id not in dst:
                dst[obj_id] = src_state
            else:
                dst[obj_id] = self.joinLifetime(
                    dst[obj_id],
                    src_state
                )

    """
    Join Allocation 
    """
    def joinAllocCount(self, lhs: AllocationCount,
                   rhs: AllocationCount) -> AllocationCount:

        if lhs == rhs:
            return lhs

        if lhs == AllocationCount.MANY or rhs == AllocationCount.MANY:
            return AllocationCount.MANY

        # ZERO ⊔ ONE means there may be zero or one allocation.
        # With this small domain, conservatively promote it.
        return AllocationCount.MANY

    def joinAllocCountMaps(self, dst, src):
        for obj_id, src_count in src.items():
            if obj_id not in dst:
                dst[obj_id] = src_count
            else:
                dst[obj_id] = self.joinAllocCount(dst[obj_id], src_count)

    """
    Merge abstract states from the predecessors of a given ICFG node.

    This function collects and combines the abstract states from all incoming edges
    of the specified ICFG node. It ensures that the abstract state of the current node
    is consistent with the states of its predecessors. The merging process involves
    joining the abstract states from all valid incoming edges.

    Steps:
    1. Initialize an empty abstract state and a counter for valid incoming edges.
    2. Iterate through all incoming edges of the given block:
       - If the source node of the edge has a post-abstract state, process the edge.
       - For intra-procedural edges with conditions, check branch feasibility.
       - If the branch is feasible, join the source's abstract state with the current state.
       - For inter-procedural or unconditional edges, directly join the source's state.
    3. If no valid incoming edges are found, print an error and return failure.
    4. Return a tuple indicating whether the merge was successful and the merged abstract state.

    :param block: The ICFG node whose predecessors' states are to be merged.
    :type block: pysvf.ICFGNode
    :return: A tuple (is_feasible, merged_state), where:
             - is_feasible (bool): True if at least one predecessor exists, False otherwise.
             - merged_state (AbstractState): The resulting merged abstract state.
    """
    def mergeStatesFromPredecessors(self, block: pysvf.ICFGNode):
        in_edge_num = 0
        # Unanalysed predecessor = coverage gap; a pruned one = analysis working.
        unanalysed_preds = 0
        abstract_state = pysvf.AbstractState()

        #if a path includes a freed memory obj, then the state when merged is set to freed to be conservative
        merged_alloc_state = {}
        # Heap simulated Lifetime  merge
        merged_lifetime = {}
        # Alloc count
        merged_alloc_count = {}
        merged_ptr_offsets = {} 
        
        is_ret_node = isinstance(block, pysvf.RetICFGNode)
        call_node = block.getCallICFGNode() if is_ret_node else None
        
        callee_analyzed = False
        if is_ret_node:
            for edge in block.getInEdges():
                src = edge.getSrcNode()
                if isinstance(src, pysvf.FunExitICFGNode) and src in self.post_abs_trace:
                    callee_analyzed = True
                    break

        for edge in block.getInEdges():
            src = edge.getSrcNode()

            if is_ret_node and src == call_node and callee_analyzed:
                continue

            if src in self.post_abs_trace:
                src_alloc = self.node_to_alloc_state.get(src, {})
                for obj_id, addr in src_alloc.items():
                    merged_alloc_state[obj_id] = addr

                src_lifetime = self.post_lifetime_trace.get(src, {})
                src_alloc_count = self.post_alloc_count_trace.get(src, {})
                src_ptr_offsets = self.post_ptr_offset_trace.get(src, {})

                if isinstance(edge, pysvf.IntraCFGEdge):
                    if edge.getCondition():
                        tmp_es = self.post_abs_trace[src].clone()

                        if self.isBranchFeasible(edge, tmp_es):
                            abstract_state.joinWith(tmp_es)
                            self.joinPtrOffsetMaps(merged_ptr_offsets, src_ptr_offsets) 
                            in_edge_num += 1
                    else:
                        abstract_state.joinWith(self.post_abs_trace[src])
                        self.joinPtrOffsetMaps(merged_ptr_offsets, src_ptr_offsets)
                        in_edge_num += 1
                else:
                    abstract_state.joinWith(self.post_abs_trace[src])
                    self.joinPtrOffsetMaps(merged_ptr_offsets, src_ptr_offsets)
                    in_edge_num += 1

                self.joinLifetimeMaps(merged_lifetime, src_lifetime)
                self.joinAllocCountMaps(merged_alloc_count, src_alloc_count)
                
            elif edge.getSrcNode() not in self.infeasible_nodes:
                unanalysed_preds += 1
        # A call whose body was not walked acts as an extra predecessor of its ret node.
        if block in self.skipped_states:
            abstract_state.joinWith(self.skipped_states[block])
            self.joinLifetimeMaps(merged_lifetime, self.skipped_lifetime_states.get(block, {}))
            in_edge_num += 1
        if in_edge_num == 0:
            print(f"Error: No predecessors for block {block.getId()}")
            if unanalysed_preds:
                # Defer: a predecessor with no state may still be one every path into
                # which was pruned
                self.orphan_nodes.add(block)
            return (False, None)
        
        self.node_to_alloc_state[block] = merged_alloc_state
        self.pre_lifetime_trace[block] = merged_lifetime
        self.pre_alloc_count_trace[block] = merged_alloc_count
        self.pre_ptr_offset_trace[block] = merged_ptr_offsets

        return (True, abstract_state)


    def isBranchFeasible(self, intraEdge: pysvf.IntraCFGEdge, abstractState:  pysvf.AbstractState) -> bool :
        cmp_var = intraEdge.getCondition()
        condition = abstractState.getVar(cmp_var.getId())
        successor = intraEdge.getSuccessorCondValue()
        if condition.isInterval():
            feasible_values = condition.getInterval().clone()
            feasible_values.meet_with(IntervalValue(successor, successor))
            # meet_with yields an inverted interval, not bottom, for disjoint operands.
            if self.intervalIsEmpty(feasible_values):
                return False
        # Also narrow the cmp operands, not just the i1 result; False = dead branch.
        return self.refineOnBranch(cmp_var, successor, abstractState)


    # Floats absent deliberately: with NaN, !(a < b) is not (a >= b).
    NEGATED_ICMP = {
        Predicate.ICMP_SLT: Predicate.ICMP_SGE, Predicate.ICMP_SGE: Predicate.ICMP_SLT,
        Predicate.ICMP_SLE: Predicate.ICMP_SGT, Predicate.ICMP_SGT: Predicate.ICMP_SLE,
        Predicate.ICMP_ULT: Predicate.ICMP_UGE, Predicate.ICMP_UGE: Predicate.ICMP_ULT,
        Predicate.ICMP_ULE: Predicate.ICMP_UGT, Predicate.ICMP_UGT: Predicate.ICMP_ULE,
        Predicate.ICMP_EQ: Predicate.ICMP_NE, Predicate.ICMP_NE: Predicate.ICMP_EQ,
    }
    UNSIGNED_ICMP = {Predicate.ICMP_ULT, Predicate.ICMP_ULE,
                     Predicate.ICMP_UGT, Predicate.ICMP_UGE}

    @staticmethod
    def intervalIsEmpty(iv: pysvf.IntervalValue) -> bool:
        # IntervalValue(5, 4).isBottom() is False, so compare the bounds directly.
        return iv.isBottom() or iv.lb() > iv.ub()

    def refineOnBranch(self, cmp_var, successor: int, abstract_state) -> bool:
        """Narrow the cmp operands given this edge was taken; False if that makes it infeasible."""
        in_edges = cmp_var.getInEdges()
        if len(in_edges) == 0:
            return True
        cmp = in_edges[0]
        if not isinstance(cmp, pysvf.CmpStmt):
            return True
        try:
            predicate = Predicate(int(cmp.getPredicate()))
        except ValueError:
            return True
        if predicate not in self.NEGATED_ICMP:
            # float or unrecognised predicate: no refinement
            return True
        if successor == 0:
            predicate = self.NEGATED_ICMP[predicate]
        elif successor != 1:
            return True

        op0, op1 = cmp.getOpVar(0), cmp.getOpVar(1)
        id0, id1 = op0.getId(), op1.getId()
        v0, v1 = abstract_state.getVar(id0), abstract_state.getVar(id1)
        node = cmp.getICFGNode()
        
        # --- Pointer Refinement Logic ---
        if v0.isAddr() or v1.isAddr():
            addr_id = id0 if v0.isAddr() else id1
            other_v = v1 if v0.isAddr() else v0
            
            is_other_null = False
            if other_v.isAddr() and (0 in other_v.getAddrs() or pysvf.NullMemAddr in other_v.getAddrs()):
                is_other_null = True
            elif other_v.isInterval() and other_v.getInterval().is_zero():
                is_other_null = True
                
            if is_other_null:
                addr_val = abstract_state.getVar(addr_id)
                addrs = set(addr_val.getAddrs())
                
                if predicate == Predicate.ICMP_EQ:
                    if 0 in addrs or pysvf.NullMemAddr in addrs:
                        null_val = 0 if 0 in addrs else pysvf.NullMemAddr
                        abstract_state[addr_id] = pysvf.AbstractValue(pysvf.AddressValue(null_val))
                    else:
                        return False 
                elif predicate == Predicate.ICMP_NE:
                    addrs.discard(0)
                    addrs.discard(pysvf.NullMemAddr)
                    if len(addrs) == 0:
                        return False 
                    abstract_state[addr_id] = pysvf.AbstractValue(pysvf.AddressValue(addrs))
            
            # Pointer Offset Narrowing for Pointer Comparisons (e.g. ptr1 < ptr2) ---
            if node in self.post_ptr_offset_trace:
                ptr_offsets = self.post_ptr_offset_trace[node]
                off0 = ptr_offsets.get(id0)
                off1 = ptr_offsets.get(id1)
                
                if off0 and off1 and off0.isInterval() and off1.isInterval():
                    # Mathematically slice the offset intervals based on the comparison
                    r0, r1 = self.refineIntervalPair(predicate, off0.getInterval(), off1.getInterval())
                    if r0 is not None:
                        if self.intervalIsEmpty(r0) or self.intervalIsEmpty(r1):
                            return False # Mathematically dead branch
                            
                        ptr_offsets[id0] = pysvf.AbstractValue(r0)
                        ptr_offsets[id1] = pysvf.AbstractValue(r1)
                        
                        # Apply back to stack memory to ensure the loop doesn't re-explode next iteration
                        self.refineLoadedCellOffset(op0, cmp, r0, ptr_offsets, abstract_state)
                        self.refineLoadedCellOffset(op1, cmp, r1, ptr_offsets, abstract_state)
            
            return True

        # --- Original Interval Refinement Logic ---
        if not (v0.isInterval() and v1.isInterval()):
            return True
            
        i0, i1 = v0.getInterval(), v1.getInterval()
        if self.intervalIsEmpty(i0) or self.intervalIsEmpty(i1):
            return True

        # Unsigned order only agrees with signed order when both sides are non-negative.
        zero = pysvf.BoundedInt(0)
        if predicate in self.UNSIGNED_ICMP and not (i0.lb() >= zero and i1.lb() >= zero):
            return True

        r0, r1 = self.refineIntervalPair(predicate, i0, i1)
        if r0 is None:
            return True
        if self.intervalIsEmpty(r0) or self.intervalIsEmpty(r1):
            return False 

        for var, var_id, refined, original in ((op0, id0, r0, i0), (op1, id1, r1, i1)):
            if refined == original:
                continue
            abstract_state[var_id] = pysvf.AbstractValue(refined)
            self.refineLoadedCell(var, cmp, refined, abstract_state)
        return True


    def refineLoadedCellOffset(self, var, cmp, refined, ptr_offsets, abstract_state):
        """Helper to write the narrowed offset back to the stack pointer cell."""
        in_edges = var.getInEdges()
        if len(in_edges) == 0:
            return
        load = in_edges[0]
        if not isinstance(load, pysvf.LoadStmt):
            return
        if not self.loadReachesCmpUnmodified(load, cmp):
            return
            
        pointer = abstract_state.getVar(load.getRHSVarID())
        if not pointer.isAddr():
            return
            
        addrs = list(pointer.getAddrs())
        if len(addrs) != 1:
            return
            
        # Write the narrowed offset back to the memory key tracker
        mem_key = f"mem_{addrs[0]}"
        ptr_offsets[mem_key] = pysvf.AbstractValue(refined)

    def refineIntervalPair(self, predicate, i0, i1):
        """Given `i0 <predicate> i1` holds, return narrowed (i0, i1), or (None, None)."""
        one = pysvf.BoundedInt(1)
        lo0, hi0, lo1, hi1 = i0.lb(), i0.ub(), i1.lb(), i1.ub()

        if predicate in (Predicate.ICMP_SLT, Predicate.ICMP_ULT):      # i0 < i1
            return (IntervalValue(lo0, min(hi0, hi1 - one)),
                    IntervalValue(max(lo1, lo0 + one), hi1))
        if predicate in (Predicate.ICMP_SLE, Predicate.ICMP_ULE):      # i0 <= i1
            return (IntervalValue(lo0, min(hi0, hi1)),
                    IntervalValue(max(lo1, lo0), hi1))
        if predicate in (Predicate.ICMP_SGT, Predicate.ICMP_UGT):      # i0 > i1
            return (IntervalValue(max(lo0, lo1 + one), hi0),
                    IntervalValue(lo1, min(hi1, hi0 - one)))
        if predicate in (Predicate.ICMP_SGE, Predicate.ICMP_UGE):      # i0 >= i1
            return (IntervalValue(max(lo0, lo1), hi0),
                    IntervalValue(lo1, min(hi1, hi0)))
        if predicate == Predicate.ICMP_EQ:        # both sides collapse to the overlap
            meet = i0.clone()
            meet.meet_with(i1)
            return (meet, meet.clone())
        if predicate == Predicate.ICMP_NE:
            # An interval has no hole, so only trim a bound against a singleton.
            n0, n1 = i0.clone(), i1.clone()
            if lo1 == hi1:
                if lo0 == lo1:
                    n0 = IntervalValue(lo0 + one, hi0)
                elif hi0 == hi1:
                    n0 = IntervalValue(lo0, hi0 - one)
            if lo0 == hi0:
                if lo1 == lo0:
                    n1 = IntervalValue(lo1 + one, hi1)
                elif hi1 == hi0:
                    n1 = IntervalValue(lo1, hi1 - one)
            return (n0, n1)
        return (None, None)

    def loadReachesCmpUnmodified(self, load, cmp, max_steps: int = 8) -> bool:
        """True when `load` reaches `cmp` on one straight-line chain with no intervening store."""
        load_node, node = load.getICFGNode(), cmp.getICFGNode()
        stmts = list(node.getSVFStmts())
        try:
            upto = stmts.index(cmp)
        except ValueError:
            return False
        if any(isinstance(st, pysvf.StoreStmt) for st in stmts[:upto]):
            return False
        steps = 0
        while node != load_node:
            if steps >= max_steps:
                return False
            in_edges = list(node.getInEdges())
            # More than one predecessor is a merge: the loaded value may be stale.
            if len(in_edges) != 1 or not isinstance(in_edges[0], pysvf.IntraCFGEdge):
                return False
            node = in_edges[0].getSrcNode()
            if node != load_node and any(isinstance(st, pysvf.StoreStmt)
                                        for st in node.getSVFStmts()):
                return False
            steps += 1
        tail = list(load_node.getSVFStmts())
        try:
            after = tail.index(load) + 1
        except ValueError:
            return False
        return not any(isinstance(st, pysvf.StoreStmt) for st in tail[after:])

    def refineLoadedCell(self, var, cmp, refined, abstract_state):
        """Also narrow the memory cell the compared value was loaded from. At -O0 each use
        re-loads it, so narrowing only the loaded value would be lost."""
        in_edges = var.getInEdges()
        if len(in_edges) == 0:
            return
        load = in_edges[0]
        if not isinstance(load, pysvf.LoadStmt):
            return
        if not self.loadReachesCmpUnmodified(load, cmp):
            return
        pointer = abstract_state.getVar(load.getRHSVarID())
        if not pointer.isAddr():
            return
        addrs = list(pointer.getAddrs())
        if len(addrs) != 1:
            # may-alias: we do not know which cell was read, so narrow nothing
            return
        abstract_state.store(addrs[0], AbstractValue(refined))





    def ensureAllAssertsValidated(self):
        svf_assert_to_be_verified = 0
        overflow_assert_to_be_verified = 0

        for node in self.svfir.getICFG().getNodes():
            if isinstance(node, pysvf.CallICFGNode):
                called_function = node.getCalledFunction()
                if called_function:
                    function_name = called_function.getName()
                    if function_name in ["svf_assert", "OVERFLOW"]:
                        if function_name == "svf_assert":
                            svf_assert_to_be_verified += 1
                        elif function_name == "OVERFLOW":
                            overflow_assert_to_be_verified += 1
                        else:
                            pass

                        if node not in self.assert_points:
                            raise AssertionError(
                                f"The stub function callsite (svf_assert or OVERFLOW) has not been checked: {node}"
                            )
                        
        assert overflow_assert_to_be_verified <= len(self.buf_overflow_helper.node_to_bug_info), \
            "The number of stub asserts (ground truth) should <= the number of overflow reported"




    """
    Perform the main analysis of the program.

    This function initializes the Weak Topological Order (WTO) for all functions,
    processes the global ICFG node, and analyzes the main function if it exists.
    It ensures that the abstract states are properly initialized and updated
    throughout the analysis.

    Steps:
    1. Initialize the WTO for all functions in the program.
    2. Process the global ICFG node to initialize its abstract state.
    3. If the main function exists:
       - Initialize its arguments as top to represent all possible inputs.
       - Process its WTO components to analyze its control flow.
    """
    def analyse(self):
        print("Entering Debugging")
        self.initWto()
        self.handleGlobalNode()
        # Process the main function if it exists
        main_fun = self.svfir.getFunObjVar("main")
        if main_fun:
            # Arguments of main are initialized as top to represent all possible inputs
            for i in range(main_fun.arg_size()):
                as_state = self.pre_abs_trace[self.icfg.getGlobalICFGNode()]
                as_state[main_fun.getArg(i).getId()] = IntervalValue.top()

            self.handleFunction(self.icfg.getFunEntryICFGNode(main_fun))

            #Memory Leak Detection at Program Exit
            main_exit = None
            for node in self.icfg.getNodes():
                if node.isFunExit() and node.getFun() == main_fun:
                    main_exit = node
                    break
            
            if main_exit:
                final_alloc_state = self.node_to_alloc_state.get(main_exit, {})
                final_abstract_state = self.post_abs_trace.get(main_exit, pysvf.AbstractState())
                final_lifetime_state = self.post_lifetime_trace.get(main_exit,{})
                
                for obj_id, addr in final_alloc_state.items():
                    # Check if the allocated address was ever natively freed
                    lifetime = final_lifetime_state.get(obj_id, Lifetime.ALLOCATED)

                    if lifetime == Lifetime.ALLOCATED:
                        msg = (
                            f"Memory Leak detected: Object {obj_id} "
                            f"(Address {addr}) was never freed."
                        )
                        self.buf_overflow_helper.reportMemoryLeak(main_exit, msg)
                        self.results["memoryleak"].append(obj_id)
            else:
                print("Warning: Could not locate the exit node for the main function.")
        else:
            assert False, "Main function not found"
        self.finaliseGaps()
        self.ensureAllAssertsValidated()
        self.buf_overflow_helper.printReport()


    """
    Update the abstract state based on the given statement.
    This function updates the abstract state based on the given statement.
    """
    def updateAbsState(self, stmt:pysvf.SVFStmt):
        if isinstance(stmt, pysvf.AddrStmt):
            self.updateStateOnAddr(stmt)
        elif isinstance(stmt, pysvf.BinaryOPStmt):
            self.updateStateOnBinary(stmt)
        elif isinstance(stmt, pysvf.CmpStmt):
            self.updateStateOnCmp(stmt)
        elif isinstance(stmt, pysvf.LoadStmt):
            self.updateStateOnLoad(stmt)
        elif isinstance(stmt, pysvf.StoreStmt):
            self.updateStateOnStore(stmt)
        elif isinstance(stmt, pysvf.CopyStmt):
            self.updateStateOnCopy(stmt)
        elif isinstance(stmt, pysvf.GepStmt):
            self.updateStateOnGep(stmt)
        #phi
        elif isinstance(stmt, pysvf.PhiStmt):
            self.updateStateOnPhi(stmt)
        # callpe
        elif isinstance(stmt, pysvf.CallPE):
            self.updateStateOnCall(stmt)
        # retpe
        elif isinstance(stmt, pysvf.RetPE):
            self.updateStateOnRet(stmt)
        #select
        elif isinstance(stmt, pysvf.SelectStmt):
            self.updateStateOnSelect(stmt)
        elif isinstance(stmt, pysvf.UnaryOPStmt) or isinstance(stmt, pysvf.BranchStmt):
            pass
        else:
            assert False , "Unhandled statement type"

    """
    Initialize an object variable in the abstract state.

    This function determines the initial abstract value for a given object variable
    based on its type and properties. It handles various types of object variables,
    including constants, global variables, and complex structures, and assigns
    appropriate abstract values such as intervals or addresses.

    Steps:
    1. Retrieve the base object associated with the given object variable.
    2. Check the type of the object variable:
       - For constant integer or floating-point variables, return their exact value as an interval.
       - For null pointers, return an interval representing zero.
       - For global variables, return an address value based on a virtual memory address.
       - For constant arrays or structures, return a top interval to represent unknown values.
    3. For other types of object variables, return an address value based on a virtual memory address.

    :param obj_var: The object variable to initialize.
    :type obj_var: pysvf.ObjVar
    :return: The initialized abstract value for the object variable.
    :rtype: pysvf.AbstractValue
    """
    def initObjVar(self, objVar: pysvf.ObjVar):
        try:
            var_id = objVar.getId()
            obj = self.svfir.getBaseObject(var_id).asBaseObjVar()
            if obj.isConstDataObjVar() or obj.isConstantArray() or obj.isConstantStruct():
                if isinstance(objVar, pysvf.ConstIntObjVar):
                    numeral = objVar.getSExtValue()
                    # 1 bit int fix boolean
                    if numeral == -1 and objVar.getZExtValue() == 1:
                        numeral = 1
                    return IntervalValue(numeral, numeral)

                elif isinstance(objVar, pysvf.ConstFPObjVar):
                    raise UnknownException("ConstFPObjVar not implemented yet")

                elif isinstance(objVar, pysvf.ConstNullPtrObjVar):
                    return AddressValue(pysvf.NullMemAddr)

                elif isinstance(objVar, pysvf.GlobalObjVar):
                    return AddressValue(self.getVirtualMemAddress(var_id))

                elif obj.isConstantArray() or obj.isConstantStruct():
                    return IntervalValue.top()
                else:
                    return IntervalValue.top()
            else:
                return AddressValue(self.getVirtualMemAddress(var_id))
        except UnknownException as e:
            log(f"pysvf: Unsupported operation with {repr(e)}. SVF-SVC will fail.")
            log_exception(e)
            fail("Unknown", 0)


    def updateStateOnAddr(self, addr: pysvf.AddrStmt):
        node = addr.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        assert isinstance(abstract_state, AbstractState)
        abstract_state[addr.getRHSVarID()] = AbstractValue(self.initObjVar(addr.getRHSVar().asObjVar()))
        abstract_state[addr.getLHSVarID()] = abstract_state[addr.getRHSVarID()]
        
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        ptr_offsets[addr.getLHSVarID()] = AbstractValue(pysvf.IntervalValue(0, 0))


    def unsignedCompare(self, predicate, lhs, rhs):
        """Unsigned compare over signed intervals; only decidable when both sides are non-negative."""
        zero = pysvf.BoundedInt(0)
        if not (lhs.lb() >= zero and rhs.lb() >= zero):
            return IntervalValue(0, 1)
        if predicate == Predicate.ICMP_UGT:
            return (lhs > rhs)
        if predicate == Predicate.ICMP_UGE:
            return (lhs >= rhs)
        if predicate == Predicate.ICMP_ULT:
            return (lhs < rhs)
        return (lhs <= rhs)

    @staticmethod
    def valueKind(value) -> str:
        if value.isInterval():
            return "interval"
        if value.isAddr():
            return "address"
        return "unset"

    def unmodelledCompare(self, node, cmp, v0, v1):
        """A comparison we have no model for: an interval against an address, an operand
        that was never written, or a predicate missing from the chain.
        """
        key = (node.getId(), cmp.getResId())
        if key not in self.unmodelled_cmps:
            self.unmodelled_cmps.add(key)
            self.recordGap(f"unmodelled comparison at node {node.getId()}: "
                           f"{self.valueKind(v0)} vs {self.valueKind(v1)}")
        return IntervalValue(0, 1)

    def updateStateOnCmp(self, cmp: pysvf.CmpStmt):
        node = cmp.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        assert isinstance(abstract_state, AbstractState)
        op0 = cmp.getOpVar(0)
        op1 = cmp.getOpVar(1)
        res = cmp.getResId()

        # Both guards below require the two operands to be the *same* kind.
        v0 = abstract_state.getVar(op0.getId())
        v1 = abstract_state.getVar(op1.getId())
        if v0.isInterval() and v1.isInterval():
            ###SVF SV-COMP-ADDITION
            # Was IntervalValue(0) -- "definitely false"; [0,1] is the sound default.
            res_val = IntervalValue(0, 1)
        
        #Check both op0 and op1 instead of just op0
        is_op0_int = abstract_state.getVar(op0.getId()).isInterval()
        is_op1_int = abstract_state.getVar(op1.getId()).isInterval()
        is_op0_addr = abstract_state.getVar(op0.getId()).isAddr()
        is_op1_addr = abstract_state.getVar(op1.getId()).isAddr()

        if is_op0_int and is_op1_int:
            res_val = IntervalValue(0)
            lhs = abstract_state[op0.getId()].getInterval()
            rhs = abstract_state[op1.getId()].getInterval()
            predicate = cmp.getPredicate()
            if predicate == Predicate.ICMP_EQ or predicate == Predicate.FCMP_OEQ or predicate == Predicate.FCMP_UEQ:
                res_val = lhs.eq_interval(rhs)
            elif predicate == Predicate.ICMP_NE or predicate == Predicate.FCMP_ONE or predicate == Predicate.FCMP_UNE:
                res_val = lhs.ne_interval(rhs)
            elif predicate == Predicate.ICMP_SGT or predicate == Predicate.FCMP_OGT or predicate == Predicate.FCMP_UGT:
                res_val = (lhs  > rhs)
            elif predicate == Predicate.ICMP_SGE or predicate == Predicate.FCMP_OGE or predicate == Predicate.FCMP_UGE:
                res_val = (lhs >= rhs)
            elif predicate == Predicate.ICMP_SLT or predicate == Predicate.FCMP_OLT or predicate == Predicate.FCMP_ULT:
                res_val = (lhs < rhs)
            elif predicate == Predicate.ICMP_SLE or predicate == Predicate.FCMP_OLE or predicate == Predicate.FCMP_ULE:
                res_val = (lhs <= rhs)
            elif (predicate == Predicate.ICMP_UGT or predicate == Predicate.ICMP_UGE or
                  predicate == Predicate.ICMP_ULT or predicate == Predicate.ICMP_ULE):
                res_val = self.unsignedCompare(predicate, lhs, rhs)
            elif predicate == Predicate.FCMP_FALSE:
                res_val = IntervalValue(0,0)
            elif predicate == Predicate.FCMP_TRUE:
                res_val = IntervalValue(1,1)
            abstract_state[res] = AbstractValue(res_val)
        elif v0.isAddr() and v1.isAddr():
            res_val = None
            lhs = abstract_state[op0.getId()]
            rhs = abstract_state[op1.getId()]
            predicate = cmp.getPredicate()

            if predicate in [Predicate.ICMP_EQ, Predicate.FCMP_OEQ, Predicate.FCMP_UEQ]:
                if len(lhs.getAddrs()) == 1 and len(rhs.getAddrs()) == 1:
                    res_val = IntervalValue(lhs.equals(rhs))
                else:
                    if lhs.getAddrs().hasIntersect(rhs.getAddrs()):
                        res_val = IntervalValue.top()
                    else:
                        res_val = IntervalValue(0)

            elif predicate in [Predicate.ICMP_NE, Predicate.FCMP_ONE, Predicate.FCMP_UNE]:
                if len(lhs.getAddrs()) == 1 and len(rhs.getAddrs()) == 1:
                    res_val = IntervalValue(not lhs.equals(rhs))
                else:
                    if lhs.getAddrs().hasIntersect(rhs.getAddrs()):
                        res_val = IntervalValue.top()
                    else:
                        res_val = IntervalValue(1)

            elif predicate in [Predicate.ICMP_UGT, Predicate.ICMP_SGT, Predicate.FCMP_OGT, Predicate.FCMP_UGT]:
                if len(lhs.getAddrs()) == 1 and len(rhs.getAddrs()) == 1:
                    res_val = IntervalValue(next(iter(lhs.getAddrs())) > next(iter(rhs.getAddrs())))
                else:
                    res_val = IntervalValue.top()

            elif predicate in [Predicate.ICMP_UGE, Predicate.ICMP_SGE, Predicate.FCMP_OGE, Predicate.FCMP_UGE]:
                if len(lhs.getAddrs()) == 1 and len(rhs.getAddrs()) == 1:
                    res_val = IntervalValue(next(iter(lhs.getAddrs())) >= next(iter(rhs.getAddrs())))
                else:
                    res_val = IntervalValue.top()

            elif predicate in [Predicate.ICMP_ULT, Predicate.ICMP_SLT, Predicate.FCMP_OLT, Predicate.FCMP_ULT]:
                if len(lhs.getAddrs()) == 1 and len(rhs.getAddrs()) == 1:
                    res_val = IntervalValue(next(iter(lhs.getAddrs())) < next(iter(rhs.getAddrs())))
                else:
                    res_val = IntervalValue.top()

            elif predicate in [Predicate.ICMP_ULE, Predicate.ICMP_SLE, Predicate.FCMP_OLE, Predicate.FCMP_ULE]:
                if len(lhs.getAddrs()) == 1 and len(rhs.getAddrs()) == 1:
                    res_val = IntervalValue(next(iter(lhs.getAddrs())) <= next(iter(rhs.getAddrs())))
                else:
                    res_val = IntervalValue.top()

            elif predicate == Predicate.FCMP_FALSE:
                res_val = IntervalValue(0, 0)

            elif predicate == Predicate.FCMP_TRUE:
                res_val = IntervalValue(1, 1)

            # Mixed operand type compare, marked
            else:
                res_val = self.unmodelledCompare(node, cmp, v0, v1)

            abstract_state[res] = res_val
        else:
            # Mixed operand type compare, marked
            abstract_state[res] = AbstractValue(
                self.unmodelledCompare(node, cmp, v0, v1))



    def updateStateOnCall(self, call: pysvf.CallPE):
        node = call.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        result = None
        result_offset = None
        
        for index in range(call.getOpVarNum()):
            call_node = call.getOpCallICFGNode(index)
            if call_node in self.post_abs_trace:
                actual_id = call.getOpVarId(index)
                val = self.post_abs_trace[call_node].getVar(actual_id)
                
                if result is None:
                    result = val
                else:
                    if result is not val:
                        result = result.clone()
                        result.join_with(val)
                    
                if call_node in self.post_ptr_offset_trace:
                    off_val = self.post_ptr_offset_trace[call_node].get(actual_id)
                    if off_val is not None:
                        if result_offset is None:
                            result_offset = off_val
                        else:
                            if result_offset is not off_val:
                                result_offset = result_offset.clone()
                                result_offset.join_with(off_val)
                            
        abstract_state[call.getResId()] = result if result is not None else pysvf.AbstractValue(pysvf.IntervalValue.top())
        
        if result_offset is not None:
            ptr_offsets[call.getResId()] = result_offset


    def updateStateOnRet(self, ret: pysvf.RetPE):
        node = ret.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        rhs_id = ret.getRHSVarID()
        lhs_id = ret.getLHSVarID()
        
        # Propagate Return Value
        val = abstract_state.getVar(rhs_id)
        abstract_state[lhs_id] = val.clone()
        
        # Propagate Return Pointer Offsets
        if rhs_id in ptr_offsets:
            ptr_offsets[lhs_id] = ptr_offsets[rhs_id].clone()



    def updateStateOnSelect(self, select: pysvf.SelectStmt):
        node = select.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        res = select.getResId()
        tval = select.getTrueValue().getId()
        fval = select.getFalseValue().getId()
        cond = select.getCondition().getId()
        cond_value = abstract_state.getVar(cond)
        if cond_value.isInterval():
            condition = cond_value.getInterval()
            if condition.is_zero():
                abstract_state[res] = abstract_state.getVar(fval).clone()
                if fval in ptr_offsets:
                    ptr_offsets[res] = ptr_offsets[fval].clone()
                return
            if condition.is_numeral():
                abstract_state[res] = abstract_state.getVar(tval).clone()
                if tval in ptr_offsets:
                    ptr_offsets[res] = ptr_offsets[tval].clone()
                return
                
        # Merge both execution paths
        result = abstract_state.getVar(tval).clone()
        result.join_with(abstract_state.getVar(fval))
        abstract_state[res] = result
        
        t_off = ptr_offsets.get(tval)
        f_off = ptr_offsets.get(fval)
        
        res_off = None
        if t_off is not None:
            res_off = t_off.clone()
        if f_off is not None:
            if res_off is None:
                res_off = f_off.clone()
            else:
                res_off.join_with(f_off)
                
        if res_off is not None:
            ptr_offsets[res] = res_off



    """
    Calculate the access offset for a given object ID and GEP statement.

    This function determines the offset of a memory access relative to the base address
    of an object. It handles different types of objects, including base objects, sub-objects
    of aggregate objects, and dummy objects. The offset is calculated using the abstract
    state and helper functions.

    :param obj_id: The ID of the object being accessed.
    :type obj_id: int
    :param gep: The GEP (GetElementPtr) statement representing the memory access.
    :type gep: pysvf.GepStmt
    :return: The calculated access offset as an IntervalValue.
    :rtype: pysvf.IntervalValue
    """
    def getAccessOffset(self, objId: int, gep: pysvf.GepStmt) -> pysvf.IntervalValue:
        obj = self.svfir.getGNode(objId)
        abstract_state = self.post_abs_trace[gep.getICFGNode()]

        # Field-insensitive base object
        if isinstance(obj, pysvf.BaseObjVar):
            # Get base size
            self.ae_manager.updateAbsState(gep.getICFGNode(), abstract_state)
            access_offset = self.ae_manager.getGepByteOffset(gep)
            return access_offset

        # A sub-object of an aggregate object
        elif isinstance(obj, pysvf.GepObjVar):
            access_offset = (
                    self.buf_overflow_helper.getGepObjOffsetFromBase(obj)
                    + self.ae_manager.getGepByteOffset(gep)
            )
            return access_offset

        else:
            assert isinstance(obj, pysvf.DummyObjVar), "What other types of object?"
            return pysvf.IntervalValue.top()
        
    

    #TODO : Implement the state updates for Copy, Binary, Store, Load, Gep, Phi
    # TODO: your code starts from here
    def updateStateOnGep(self, gep: pysvf.GepStmt):
        node = gep.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        assert isinstance(abstract_state, AbstractState)

        lhs = gep.getLHSVarID()
        rhs = gep.getRHSVarID()
        rhs_var = abstract_state.getVar(rhs)

        # Deferred cloning pass-through
        if rhs_var.isAddr():
            abstract_state[lhs] = rhs_var 
        else:
            abstract_state[lhs] = pysvf.AbstractValue(pysvf.IntervalValue.top())

        offset_val = ptr_offsets.get(rhs)
        base_offset = offset_val.getInterval() if (offset_val and offset_val.isInterval()) else pysvf.IntervalValue(0, 0)

        if rhs_var.isAddr():
            # Alias Cutoff: Stop tracking bounds for pointers that alias massively
            if len(rhs_var.getAddrs()) > 50:
                ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue.top())
                return

            try:
                self.ae_manager.updateAbsState(node, abstract_state)
                pointer = gep.getRHSVar()
                index_iv = self.ae_manager.getGepElementIndex(gep)
                
                if index_iv is not None and index_iv.isInterval():
                    # Fast-path cache initialization
                    if not hasattr(self, '_type_size_cache'):
                        self._type_size_cache = {}
                    
                    ptr_type = pointer.getType()
                    type_id = ptr_type.getId() if ptr_type else None
                    
                    # Compute only on cache miss
                    if type_id not in self._type_size_cache:
                        elem_size = 1
                        if ptr_type and ptr_type.isPointerTy():
                            elem_type = self.ae_manager.getPointeeElement(pointer, node)
                            if elem_type:
                                elem_size = elem_type.getTypeOfElement().getByteSize() if elem_type.isArrayTy() else elem_type.getByteSize()
                        self._type_size_cache[type_id] = elem_size if elem_size > 0 else 1
                        
                    elem_size = self._type_size_cache[type_id]
                    gep_increment = index_iv * pysvf.IntervalValue(elem_size, elem_size)
                    ptr_offsets[lhs] = pysvf.AbstractValue(base_offset + gep_increment)
                else:
                    ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue.top())
            except Exception:
                ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue.top())
        else:
            ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue.top())

    #TODO: your code starts from here
    def updateStateOnStore(self, store: pysvf.StoreStmt):
        node = store.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        lhs = store.getLHSVarID() # Memory location
        rhs = store.getRHSVarID() # Value being stored

        self.checkMemorySafety(node, lhs)
        self.checkBufferOverflow(node, lhs)

        if abstract_state.getVar(lhs).isAddr():
            value = abstract_state[rhs]
            needs_weak = self.needsWeakUpdate(abstract_state, abstract_state[lhs].getAddrs())
            
            if needs_weak:
                value = value.clone()
                for addr in abstract_state[lhs].getAddrs():
                    if abstract_state.getIDFromAddr(addr) in abstract_state.getLocToVal():
                        value.join_with(abstract_state.load(addr))
                        
            self.ae_manager.updateAbsState(node, abstract_state)
            self.ae_manager.storeValue(store.getLHSVar(), value, node)
            self.post_abs_trace[node] = self.ae_manager.getAbsState(node).clone()
            
            # --- FIX: Pointer Offset Memory Tracking ---
            rhs_var = abstract_state.getVar(rhs)
            offset_val = ptr_offsets.get(rhs)
            
            if rhs_var.isAddr() and offset_val is not None:
                # Store the offset using the memory object ID as the key
                for addr in abstract_state.getVar(lhs).getAddrs():
                    mem_key = -addr
                    if needs_weak and mem_key in ptr_offsets:
                        merged = ptr_offsets[mem_key].clone()
                        merged.join_with(offset_val)
                        ptr_offsets[mem_key] = merged
                    else:
                        ptr_offsets[mem_key] = offset_val.clone()
            else:
                # Strong update: clear offset if storing a non-pointer
                if not needs_weak:
                    for addr in abstract_state.getVar(lhs).getAddrs():
                        mem_key = -addr
                        if mem_key in ptr_offsets:
                            del ptr_offsets[mem_key]

    def needsWeakUpdate(self, abstract_state, addrs) -> bool:
        """ Update when exact location is unknown: adds its value to what the 
        state already holds, instead of replacing it
            Example
            int a[10];      // one cell for the whole array
            a[0] = 7;
            a[i] = 0;       // strong: a is {0}, so a[0] == 7 looks impossible
                            // weak:   a is [0, 7], which is correct

        A weak update is needed when:
        - the pointer has several possible targets, so only one of them is written;
        - the object is on the heap: one object per malloc site stands for every block
          that site returns (e.g. every node of a list built in a loop);
        - the object is field-insensitive, so all its elements share one cell;
        - the object has no constant size (a VLA), so it is also kept as one cell.
        """
        if len(addrs) > 1:
            return True
        for addr in addrs:
            if abstract_state.isNullMem(addr) or abstract_state.isBlackHoleObjAddr(addr):
                continue
            base = self.svfir.getBaseObject(abstract_state.getIDFromAddr(addr))
            if base is not None and (base.isHeap() or base.isFieldInsensitive()
                                     or not base.isConstantByteSize()):
                return True
        return False

    #TODO: your code starts from here
    # Find the comparison predicates in "class BinaryOPStmt:OpCode" under SVF/svf/include/SVFIR/SVFStatements.h
    # You are required to handle predicates (The program is assumed to have signed ints and also interger-overflow-free),
    # including Add, FAdd, Sub, FSub, Mul, FMul, SDiv, FDiv, UDiv, SRem, FRem, URem, Xor, And, Or, AShr, Shl, LShr
    def updateStateOnBinary(self, binary: pysvf.BinaryOPStmt):
        try:
            node = binary.getICFGNode()
            abstract_state = self.post_abs_trace[node]
            lhs = binary.getResId()
            op1 = binary.getOpVar(0)
            op2 = binary.getOpVar(1)

            if (not abstract_state.getVar(op1.getId()).isInterval()
                    or not abstract_state.getVar(op2.getId()).isInterval()):
                raise UnknownException("Operands must be intervals")
            result = IntervalValue(0)
            val1 = abstract_state[op1.getId()].getInterval()
            val2 = abstract_state[op2.getId()].getInterval()
            if binary.getOpcode() == OpCode.Add or binary.getOpcode() == OpCode.FAdd:
                result = val1 + val2
            elif binary.getOpcode() == OpCode.Sub or binary.getOpcode() == OpCode.FSub:
                result = val1 - val2
            elif binary.getOpcode() == OpCode.Mul or binary.getOpcode() == OpCode.FMul:
                result = val1 * val2
            elif binary.getOpcode() == OpCode.UDiv or binary.getOpcode() == OpCode.SDiv or binary.getOpcode() == OpCode.FDiv:
                if int(val2.ub())>=0 and int(val2.lb()) <= 0:
                    result = IntervalValue.top()
                else:
                    result = val1 / val2
            elif binary.getOpcode() == OpCode.SRem or binary.getOpcode() == OpCode.FRem or binary.getOpcode() == OpCode.URem:
                if int(val2.ub())>=0 and int(val2.lb()) <= 0:
                    result = IntervalValue.top()
                else:
                    result = val1 % val2
            elif binary.getOpcode() == OpCode.Xor:
                result = val1 ^ val2
            elif binary.getOpcode() == OpCode.Or:
                result = val1 | val2
            elif binary.getOpcode() == OpCode.And:
                result = val1 & val2
            elif binary.getOpcode() == OpCode.Shl:
                result = val1 << val2
            elif binary.getOpcode() == OpCode.LShr or binary.getOpcode() == OpCode.AShr:
                result = val1 >> val2
            else:
                result = IntervalValue.top()
            abstract_state[lhs] = AbstractValue(result)
        except UnknownException as e:
            log(f"pysvf: Unsupported operation with {repr(e)}. SVF-SVC will fail.")
            log_exception(e)
            fail("Unknown", 0)


    #TODO: your code starts from here
    def updateStateOnLoad(self, load: pysvf.LoadStmt):
        node = load.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        lhs = load.getLHSVarID()
        rhs = load.getRHSVarID()

        self.checkMemorySafety(node, rhs)
        self.checkBufferOverflow(node, rhs)

        if abstract_state.getVar(rhs).isAddr():
            self.ae_manager.updateAbsState(node, abstract_state)
            loaded = self.ae_manager.loadValue(load.getRHSVar(), node)
            
            if not loaded.isAddr() and (not loaded.isInterval() or self.intervalIsEmpty(loaded.getInterval())):
                loaded = pysvf.AbstractValue(pysvf.IntervalValue.top())
            abstract_state[lhs] = loaded
            
            # --- FIX: Retrieve Pointer Offsets from Memory ---
            if loaded.isAddr():
                merged_offset = None
                for addr in abstract_state.getVar(rhs).getAddrs():
                    mem_key = -addr
                    off = ptr_offsets.get(mem_key)
                    if off is not None:
                        if merged_offset is None:
                            merged_offset = off.clone()
                        else:
                            merged_offset.join_with(off)
                            
                if merged_offset is not None:
                    ptr_offsets[lhs] = merged_offset
                else:
                    ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue(0, 0))
            else:
                ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue(0, 0))
        else:
            abstract_state[lhs] = pysvf.AbstractValue(pysvf.IntervalValue.top())
            ptr_offsets[lhs] = pysvf.AbstractValue(pysvf.IntervalValue(0, 0))

    #TODO: your code starts from here
    def updateStateOnCopy(self, copy: pysvf.CopyStmt):
        node = copy.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        lhs = copy.getLHSVarID()
        rhs = copy.getRHSVarID()
        
        abstract_state[lhs] = abstract_state.getVar(rhs)
        if rhs in ptr_offsets:
            ptr_offsets[lhs] = ptr_offsets[rhs]


    # TODO: your code starts from here
    def updateStateOnPhi(self, phi: pysvf.PhiStmt):
        node = phi.getICFGNode()
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.setdefault(node, {})
        
        lhs = phi.getResId()
        result = None
        result_offset = None
        
        for i in range(phi.getOpVarNum()):
            op_var = phi.getOpVar(i)
            def_node = op_var.getICFGNode()
            if def_node is not None and def_node in self.infeasible_nodes:
                continue
                
            op_id = op_var.getId()
            op_val = abstract_state.getVar(op_id)
            
            if op_val.isInterval() or op_val.isAddr():
                if result is None:
                    result = op_val
                else:
                    if result is not op_val:
                        result = result.clone()
                        result.join_with(op_val)
                    
                if op_id in ptr_offsets:
                    off_val = ptr_offsets[op_id]
                    if result_offset is None:
                        result_offset = off_val
                    else:
                        if result_offset is not off_val:
                            result_offset = result_offset.clone()
                            result_offset.join_with(off_val)
                        
        if result is not None:
            abstract_state[lhs] = result
        if result_offset is not None:
            ptr_offsets[lhs] = result_offset

    """
    Detect buffer overflows in the given statement.

    TODO: handle GepStmt `lhs = rhs + off` and detect buffer overflow
    Step 1: For each `obj in pts(rhs)`, get the size of allocated baseobj (entire mem object) via `obj_size = svfir->getBaseObj(objId)->getByteSizeOfObj();`
    There is a buffer overflow if `accessOffset.ub() >= obj_size`, where accessOffset is obtained via `getAccessOffset`
    Step 2: invoke `reportBufOverflow` with the current ICFGNode if an overflow is detected

    :param stmt: The statement to analyze for buffer overflows.
    :type stmt: pysvf.SVFStmt
    """
    def checkBufferOverflow(self, node: pysvf.ICFGNode, ptr_id: int):
        if node not in self.post_abs_trace:
            return
            
        abstract_state = self.post_abs_trace[node]
        ptr_offsets = self.post_ptr_offset_trace.get(node, {})
        ptr_val = abstract_state.getVar(ptr_id)
        
        if not ptr_val.isAddr():
            return
            
        offset_val = ptr_offsets.get(ptr_id)
        if offset_val and offset_val.isInterval():
            current_offset = offset_val.getInterval()
        else:
            current_offset = pysvf.IntervalValue(0, 0)
            
        for addr in ptr_val.getAddrs():
            if addr == 0 or abstract_state.isNullMem(addr):
                continue
                
            obj_id = abstract_state.getIDFromAddr(addr)
            
            try:
                base_obj = self.svfir.getBaseObject(obj_id)
                if not base_obj:
                    continue
                
                obj_size = base_obj.getByteSizeOfObj()
                
                # Dynamic array fallback check (VLA / mallocs with 0 static size)
                if obj_size == 0 and not base_obj.isConstantByteSize():
                    # For SV-COMP, if it widened to Top and wasn't narrowed, it's considered unbounded
                    if current_offset.isTop():
                        msg = "Buffer overflow detected. Unbounded access on dynamically sized object."
                        self.buf_overflow_helper.reportBufOverflow(node, msg)
                        self.results["bufferoverflow"].append(node)
                    continue 

                # Standard verification evaluation
                if obj_size > 0:
                    if current_offset.isTop() or int(current_offset.ub()) >= obj_size or int(current_offset.lb()) < 0:
                        msg = f"Buffer overflow detected. Object size: {obj_size}, accessing offset {current_offset}"
                        self.buf_overflow_helper.reportBufOverflow(node, msg)
                        self.results["bufferoverflow"].append(node)
            except RuntimeError:
                continue
    def bufOverflowDetection(self, stmt: pysvf.SVFStmt):
        if not isinstance(stmt.getICFGNode(), pysvf.CallICFGNode):
            if isinstance(stmt, pysvf.GepStmt):
                abstract_state = self.post_abs_trace[stmt.getICFGNode()]
                lhs = stmt.getLHSVarID()
                rhs = stmt.getRHSVarID()

                try:
                    self.ae_manager.updateAbsState(stmt.getICFGNode(), abstract_state)
                    offset = self.ae_manager.getGepByteOffset(stmt)
                    self.buf_overflow_helper.updateGepObjOffsetFromBase(
                        abstract_state, abstract_state[lhs].getAddrs(), abstract_state[rhs].getAddrs(), offset
                    )
                except Exception:
                    pass

                for addr in abstract_state[rhs].getAddrs():
                    if addr == 0 or abstract_state.isNullMem(addr):
                        continue
                    obj_id = abstract_state.getIDFromAddr(addr)
                    
                    try:
                        obj = self.svfir.getGNode(obj_id)

                        base_obj = self.svfir.getBaseObject(obj_id)
                        access_offset = self.getAccessOffset(obj_id, stmt)
                        obj_size = base_obj.getByteSizeOfObj()

                        if not base_obj:
                            continue

                        if isinstance(access_offset, pysvf.IntervalValue) and not access_offset.isBottom():
                            # Explicitly flag completely unconstrained offsets (`Top`) from elements like rand()
                            if access_offset.isTop() or int(access_offset.ub()) >= obj_size:
                                msg = "Buffer overflow detected. Objsize: {}, but try to access offset {}".format(obj_size, access_offset)
                                self.buf_overflow_helper.reportBufOverflow(stmt.getICFGNode(), msg)
                                self.results["bufferoverflow"].append(stmt)
                    except RuntimeError:
                        continue

    """
    Handle external function calls and update the abstract state.

    This function processes specific external function calls, such as `mem_insert` and `str_insert`,
    to ensure that buffer overflows are detected and prevented. It checks the constraints on the
    buffer size and access offsets based on the function arguments.

    TODO: Steps:
    1. For `mem_insert`:
       - Validate that the buffer size is greater than or equal to the sum of the position and data size.
    2. For `str_insert`:
       - Validate that the buffer size is greater than or equal to the sum of the position and the length of the string.

    :param ext_call_node: The call node representing the external function call.
    :type ext_call_node: pysvf.CallICFGNode
    """
    def updateStateOnExtCall(self, extCallNode: pysvf.CallICFGNode):
        # Get function name
        func_name = extCallNode.getCalledFunction().getName()
        
        # Initialize the alloc state for this node if not exists
        if extCallNode not in self.node_to_alloc_state:
            self.node_to_alloc_state[extCallNode] = {}

        # Handle external calls
        # TODO: handle external calls
        # void mem_insert(void *buffer, const void *data, size_t data_size, size_t position);
        if func_name == "mem_insert":
            # void mem_insert(void *buffer, const void *data, size_t data_size, size_t position);
            # Check sizeof(buffer) >= position + data_size
            abstract_state = self.post_abs_trace[extCallNode]
            assert isinstance(abstract_state, AbstractState)
            buffer_id = extCallNode.getArgument(0).getId()
            position_id = extCallNode.getArgument(3).getId()
            data_size_id = extCallNode.getArgument(2).getId()

            for addr in abstract_state[buffer_id].getAddrs():
                obj_id = abstract_state.getIDFromAddr(addr)
                obj_size = self.svfir.getBaseObject(obj_id).getByteSizeOfObj()
                access_offset = abstract_state[position_id].getInterval() + abstract_state[data_size_id].getInterval()

                if int(access_offset.ub()) > obj_size:
                    msg = "Buffer overflow detected. Objsize: {}, but try to access offset {}".format(obj_size, access_offset)
                    self.buf_overflow_helper.reportBufOverflow(extCallNode, msg)
                else:
                    self.buf_overflow_helper.handleMemcpy(abstract_state, extCallNode.getArgument(0), extCallNode.getArgument(1), abstract_state[data_size_id].getInterval(), abstract_state[position_id].getInterval().getIntNumeral(), extCallNode)
        # TODO: handle external calls
        # void str_insert(void *buffer, const void *data, size_t position);
        elif func_name == "str_insert":
            # void str_insert(void *buffer, const void *data, size_t position);
            # Check sizeof(buffer) >= position + strlen(data)
            abstract_state = self.post_abs_trace[extCallNode]
            buffer_id = extCallNode.getArgument(0).getId()
            position_id = extCallNode.getArgument(2).getId()
            strlen = self.buf_overflow_helper.getStrlen(abstract_state, extCallNode.getArgument(1), extCallNode)

            for addr in abstract_state[buffer_id].getAddrs():
                obj_id = abstract_state.getIDFromAddr(addr)
                obj_size = self.svfir.getBaseObject(obj_id).getByteSizeOfObj()
                access_offset = abstract_state[position_id].getInterval() + strlen

                if int(access_offset.ub()) > obj_size:
                    msg = f"Buffer overflow detected. Objsize: {obj_size}, but try to access offset {access_offset}"
                    self.buf_overflow_helper.reportBufOverflow(extCallNode, msg)
                else:
                    self.buf_overflow_helper.handleMemcpy(abstract_state, extCallNode.getArgument(0), extCallNode.getArgument(1), strlen, abstract_state[position_id].getInterval().getIntNumeral(), extCallNode)
    
        elif func_name in ["malloc", "calloc", "realloc"]:
            abstract_state = self.post_abs_trace[extCallNode]
            ptr_offsets = self.post_ptr_offset_trace.setdefault(extCallNode, {})
            lhs_id = extCallNode.getRetICFGNode().getActualRet().getId()
            
            ptr_offsets[lhs_id] = pysvf.AbstractValue(pysvf.IntervalValue(0, 0))
            
            heap_obj_id = None
            for var_id, var in self.svfir:
                if var.isObjVar() and var.asObjVar().isHeapObjVar():
                    if var.asObjVar().asHeapObjVar().getICFGNode().getId() == extCallNode.getId():
                        heap_obj_id = var_id
                        break
            
            if heap_obj_id is not None:
                # 3. Mint the address and assign it to the return variable
                alloc_addr = self.getVirtualMemAddress(heap_obj_id)
                abstract_state[lhs_id] = pysvf.AbstractValue(pysvf.AddressValue(alloc_addr))
                
                lifetime_state = self.post_lifetime_trace[extCallNode]

                if heap_obj_id not in lifetime_state:
                    lifetime_state[heap_obj_id] = Lifetime.ALLOCATED

                alloc_count_state = self.post_alloc_count_trace[extCallNode]

                old_count = alloc_count_state.get(heap_obj_id, AllocationCount.ZERO)

                if old_count == AllocationCount.ZERO:
                    alloc_count_state[heap_obj_id] = AllocationCount.ONE
                else:
                    alloc_count_state[heap_obj_id] = AllocationCount.MANY
                

                # 4. Register the allocation for memory leak tracking
                self.node_to_alloc_state[extCallNode][heap_obj_id] = alloc_addr
            
        elif func_name == "free":
            abstract_state = self.post_abs_trace[extCallNode]
            lifetime_state = self.post_lifetime_trace[extCallNode]
            alloc_count_state = self.post_alloc_count_trace[extCallNode]
            ptr_offsets = self.post_ptr_offset_trace.setdefault(extCallNode, {})

            arg_id = extCallNode.getArgument(0).getId()
            arg_val = abstract_state[arg_id]
            
            offset_val = ptr_offsets.get(arg_id)
            if offset_val and offset_val.isInterval():
                offset = offset_val.getInterval()
            else:
                offset = pysvf.IntervalValue(0, 0)
                
            if offset.isTop() or int(offset.lb()) != 0 or int(offset.ub()) != 0:
                msg = f"Bad Free detected: Attempting to free inner pointer at offset {offset}"
                self.buf_overflow_helper.reportBadFree(extCallNode, msg)
                self.results["badfree"].append(extCallNode)
                return 
            
            if arg_val.isAddr():
                for addr in arg_val.getAddrs():
                    #free(NULL) is fine
                    if addr == 0 or abstract_state.isNullMem(addr):
                        continue

                    obj_id = abstract_state.getIDFromAddr(addr)
                    base_obj = self.svfir.getBaseObject(obj_id)

                    if base_obj is None or not base_obj.isHeap():
                        msg = f"Free_Memory_Not_on_Heap: Attempting to free non-heap address {addr}"
                        self.buf_overflow_helper.reportBadFree(extCallNode, msg)
                        self.results["badfree"].append(extCallNode)
                        continue

                    base_id = base_obj.getId()

                    lifetime = lifetime_state.get(base_id, Lifetime.ALLOCATED)
                    alloc_count = alloc_count_state.get(base_id, AllocationCount.ONE)

                    if lifetime == Lifetime.FREED:
                        msg = f"Double free detected on address {addr}"
                        self.buf_overflow_helper.reportDoubleFree(extCallNode, msg)
                        self.results["doublefree"].append(extCallNode)
                        continue

                    if alloc_count == AllocationCount.ONE:
                        # Strong update
                        lifetime_state[base_id] = Lifetime.FREED

                    else:
                        # Weak update
                        lifetime_state[base_id] = Lifetime.MAY_FREED



    """
    Handle ICFG nodes in a cycle using widening and narrowing operators.
    
    This function implements abstract interpretation for cycles in the ICFG using widening and narrowing
    operators to ensure termination. It processes all ICFG nodes within a cycle and implements
    widening-narrowing iteration to reach fixed points twice: once for widening (to ensure termination)
    and once for narrowing (to improve precision).
    
    :param cycle: The WTO cycle containing ICFG nodes to be processed
    :type cycle: ICFGWTOCycle
    """
    def handleICFGCycle(self, cycle: ICFGWTOCycle):
        head = cycle.head.node
        increasing = True
        iteration = 0
        narrowing_iters = 0
        MAX_NARROWING = 10
        widen_delay = self.widen_delay 

        while True:
            # 1. Snapshot previous state
            pre_iteration_as = self.post_abs_trace[head] if head in self.post_abs_trace else None
            pre_iteration_lifetime = self.post_lifetime_trace.get(head, {}).copy()
            
            pre_iteration_ptr_offsets = {}
            if head in self.post_ptr_offset_trace:
                for k, v in self.post_ptr_offset_trace[head].items():
                    pre_iteration_ptr_offsets[k] = v.clone()

            # 2. Evaluate head node
            self.handleICFGNode(head) 
            
            if head not in self.post_abs_trace:
                if head not in self.infeasible_nodes:
                    self.recordGap(f"cycle head {head.getId()} had no feasible state")
                break
                
            cur_iteration_as = self.post_abs_trace[head]
            cur_iteration_lifetime = self.post_lifetime_trace.get(head, {}).copy()
            cur_iteration_ptr_offsets = self.post_ptr_offset_trace.get(head, {})

            # 3. Widening / Narrowing Logic
            if iteration >= widen_delay and pre_iteration_as is not None:
                if increasing:
                    # --- WIDENING PHASE ---
                    self.post_abs_trace[head] = pre_iteration_as.widening(cur_iteration_as)
                    
                    ptr_stable = True
                    # If sizes differ, new variables were tracked
                    if len(pre_iteration_ptr_offsets) != len(cur_iteration_ptr_offsets):
                        ptr_stable = False
                        
                    for vid, cur_val in cur_iteration_ptr_offsets.items():
                        pre_val = pre_iteration_ptr_offsets.get(vid)
                        
                        # If it was already widened to Top, it stays stable
                        if pre_val is not None and pre_val.getInterval().isTop():
                            self.post_ptr_offset_trace[head][vid] = pysvf.AbstractValue(pysvf.IntervalValue.top())
                        # If it differs or is new, widen to Top
                        elif pre_val is None or not cur_val.getInterval().equals(pre_val.getInterval()):
                            self.post_ptr_offset_trace[head][vid] = pysvf.AbstractValue(pysvf.IntervalValue.top())
                            ptr_stable = False

                    abs_stable = (self.post_abs_trace[head] == pre_iteration_as)
                    lifetime_stable = (cur_iteration_lifetime == pre_iteration_lifetime)

                    if abs_stable and lifetime_stable and ptr_stable:
                        increasing = False
                        narrowing_iters = 0
                  
                else:
                    # --- NARROWING PHASE ---
                    self.post_abs_trace[head] = pre_iteration_as.narrowing(cur_iteration_as)
                    
                    # Pointer offsets stay at widened Top state during narrowing
                    for k, v in pre_iteration_ptr_offsets.items():
                        self.post_ptr_offset_trace[head][k] = v.clone()
                    ptr_stable = True

                    abs_stable = (self.post_abs_trace[head] == pre_iteration_as)
                    lifetime_stable = (cur_iteration_lifetime == pre_iteration_lifetime)

                    if abs_stable and lifetime_stable and ptr_stable:
                        break
                    
                    narrowing_iters += 1
                    if narrowing_iters > MAX_NARROWING:
                        # Hard stop to prevent infinite narrowing oscillations
                        break
            
            # 4. Evaluate sub-components cleanly using the WTO structure
            self.handleWtoComponents(cycle.components)

            iteration += 1
    
    
    def checkMemorySafety(self, node: pysvf.ICFGNode, ptr_id: int):
        if node not in self.post_abs_trace:
            return
            
        abstract_state = self.post_abs_trace[node]
        lifetime_state = self.post_lifetime_trace.get(node, {})
        ptr_val = abstract_state.getVar(ptr_id)
        
        # Grab the underlying SVFVar directly from the IR
        ptr_var = self.svfir.getGNode(ptr_id)

        # 1. Catch Raw Constant Nulls directly from the IR
        # Check if it's a ValVar and specifically a ConstNullPtrValVar
        if ptr_var.isValVar() and ptr_var.asValVar().isConstNullPtrValVar():
            msg = "Null pointer dereference detected (Raw Constant)."
            self.buf_overflow_helper.reportNullDereference(node, msg)
            self.results["nulldereference"].append(node)
            return

        # 2. Null Pointer Dereference Check (Interval representation)
        if ptr_val.isInterval():
            interval = ptr_val.getInterval()
            if interval.is_zero():
                msg = "Null pointer dereference detected (Interval 0)."
                self.buf_overflow_helper.reportNullDereference(node, msg)
                self.results["nulldereference"].append(node)
                return

        # 3. Use After Free & Null Address Check
        if ptr_val.isAddr():
            addrs = ptr_val.getAddrs()
            if len(addrs) == 0:
                return
                
            # MUST-Alias Check: Are ALL possible addresses NULL?
            is_definitely_null = True
            for addr in addrs:
                if addr != 0 and not abstract_state.isNullMem(addr):
                    is_definitely_null = False
                    break
                    
            if is_definitely_null:
                msg = "Null pointer dereference detected (Must be Address 0)."
                self.buf_overflow_helper.reportNullDereference(node, msg)
                self.results["nulldereference"].append(node)
                return

            # MUST-Alias Check: Are ALL possible addresses FREED?
            is_definitely_freed = True
            has_heap_addr = False

            for addr in addrs:
                if addr == 0 or abstract_state.isNullMem(addr):
                    is_definitely_freed = False
                    continue

                obj_id = abstract_state.getIDFromAddr(addr)
                base_obj = self.svfir.getBaseObject(obj_id)

                if base_obj is None or not base_obj.isHeap():
                    is_definitely_freed = False
                    continue

                has_heap_addr = True

                lifetime = lifetime_state.get(base_obj.getId(), Lifetime.ALLOCATED)

                if lifetime != Lifetime.FREED:
                    is_definitely_freed = False

            if has_heap_addr and is_definitely_freed:
                msg = f"Use After Free detected. Must access freed addresses {addrs}."
                self.buf_overflow_helper.reportUseAfterFree(node, msg)
                self.results["useafterfree"].append(node)

