import pysvf
class CFLreachability:
    def __init__(self, pag: pysvf.SVFIR):
        self.svfir = pag
        self.icfg = pag.getICFG()
        # worklist structure: (current ICFG node, current call context)
        self.worklist = []
        self.visited = set()
        self.results = {"reach": []}
    def analyze(self):
        # main function
        main_fun = self.svfir.getFunObjVar("main")
        entry = self.icfg.getFunEntryICFGNode(main_fun)
        self.worklist.append((entry, (), ("main",)))
        # remain codes
        self.run()
        return self.results
        
    def run(self):
        # repeat until worklist is empty (all functions processed)
        while self.worklist:
            # get the first function from worklist
            node, stack, function_stack = self.worklist.pop(0)
            state_key = (node.getId(), stack, function_stack)
            # skip if already visited
            if state_key in self.visited:
                continue
            self.visited.add(state_key)
            # check if Call node is not exists
            if isinstance(node, pysvf.CallICFGNode):
                # get the next called function
                callee = node.getCalledFunction()
                if callee is None:
                    found_target = False
                    for edge in node.getOutEdges():
                        if not edge.isIntraCFGEdge():
                            target_entry = edge.getDstNode()
                            target_func = target_entry.getFun()
                            if target_func is None:
                                continue
                            found_target = True
                            callsite_id = node.getId()
                            new_stack = stack + (callsite_id,)
                            target_name = target_func.getName()
                            if target_name in ("reach_error", "__VERIFIER_error"):
                                self.results["reach"].append((True, node))
                                continue

                            if target_name in function_stack:
                                self.results.setdefault("incomplete", []).append(
                                    f"Recursive indirect call at node {node.getId()}"
                                )

                            if pysvf.isExtCall(target_func) or target_name in function_stack:
                                ret_node = node.getRetICFGNode()
                                for e in ret_node.getOutEdges():
                                    self.worklist.append(
                                        (e.getDstNode(), stack, function_stack)
                                    )
                                continue

                            new_function_stack = function_stack + (target_name,)
                            self.worklist.append((target_entry, new_stack, new_function_stack))

                    if not found_target:
                        self.results.setdefault("incomplete", []).append(
                            f"Unresolved indirect call at node {node.getId()}"
                        )

                        ret_node = node.getRetICFGNode()
                        for e in ret_node.getOutEdges():
                            self.worklist.append(
                                (e.getDstNode(), stack, function_stack)
                            )

                    continue


                if callee and callee.getName() in ("reach_error", "__VERIFIER_error"):
                    self.results["reach"].append((True, node))
                    continue
                # -------------------------------------------------
                # handle Call node
                # handle internal calls
                # we don't need to handle external calls
                if callee and not pysvf.isExtCall(callee):
                    callee_name = callee.getName()
                    if callee_name in function_stack:
                        self.results.setdefault("incomplete", []).append(
                            f"Recursive direct call at node {node.getId()}"
                        )

                        ret_node = node.getRetICFGNode()
                        for e in ret_node.getOutEdges():
                            self.worklist.append((e.getDstNode(), stack, function_stack))
                        continue

                    # push stack
                    callsite_id = node.getId()
                    new_stack = stack + (callsite_id,)

                    # jump to callee entry
                    entry = self.icfg.getFunEntryICFGNode(callee)
                    new_function_stack = function_stack + (callee_name,)
                    self.worklist.append((entry, new_stack, new_function_stack))
                else:
                    # skip external call, continue after it
                    ret_node = node.getRetICFGNode()
                    for e in ret_node.getOutEdges():
                        self.worklist.append((e.getDstNode(), stack, function_stack))
                continue
            # -------------------------------------------------
            # handle Ret node
            elif isinstance(node, pysvf.RetICFGNode):
                # don't handle external returns
                callnode = node.getCallICFGNode()
                if callnode:
                    called_func = callnode.getCalledFunction()
                    if called_func is not None and pysvf.isExtCall(called_func):
                        continue
                # pop stack
                if stack:
                    top = stack[-1]   
                else:
                    continue # empty stack, skip
                if not callnode or top != callnode.getId():
                    continue # mismatched stack, skip
                new_stack = stack[:-1]
                new_function_stack = function_stack[:-1]
                # handle the nodes after return the current function
                for e in node.getOutEdges():
                    dst = e.getDstNode()
                    self.worklist.append((dst, new_stack, new_function_stack))

            # -------------------------------------------------
            # handle normal node
            else:
                for e in node.getOutEdges():
                    dst = e.getDstNode()
                    self.worklist.append((dst, stack, function_stack))
