import pysvf
class CFLreachability:
    def __init__(self, pag: pysvf.SVFIR):
        self.svfir = pag
        self.icfg = pag.getICFG()
        self.worklist = []
        self.visited = set()
        self.call_stack = []
        self.results = {"reach": []}
    def analyze(self):
        # main function
        main_fun = self.svfir.getFunObjVar("main")
        entry = self.icfg.getFunEntryICFGNode(main_fun)
        self.worklist.append((entry, ()))
        # remain codes
        self.run()
        return self.results
        
    def run(self):
        # repeat until worklist is empty (all functions processed)
        while self.worklist:
            # get the first function from worklist
            node, stack = self.worklist.pop(0)
            if len(stack) >= 2:
                ctx = (stack[-2], stack[-1])
            elif len(stack) == 1:
                ctx = (None, stack[-1])
            else:
                ctx = (None, None)
            state_key = (node.getId(), ctx)
            # skip if already visited
            if state_key in self.visited:
                continue
            self.visited.add(state_key)
            # check if Call node is not exists
            if isinstance(node, pysvf.CallICFGNode):
                # get the next called function
                callee = node.getCalledFunction()
                if callee and callee.getName() == "reach_error":
                    self.results["reach"].append((True, node))
                # -------------------------------------------------
                # handle Call node
                callee = node.getCalledFunction()
                # handle internal calls
                # we don't need to handle external calls
                if callee and not pysvf.isExtCall(callee):
                    # push stack
                    callee_name = callee.getName()
                    new_stack = (stack + (callee_name,))[-2:]

                    # jump to callee entry
                    entry = self.icfg.getFunEntryICFGNode(callee)
                    self.worklist.append((entry, new_stack))

                # also follow normal CFG to ret node
                ret_node = node.getRetICFGNode()
                self.worklist.append((ret_node, stack))  # will pop when handle ret
                continue
            # -------------------------------------------------
            # handle Ret node
            elif isinstance(node, pysvf.RetICFGNode):
                callnode = node.getCallICFGNode()
                callee = callnode.getCalledFunction() if callnode else None
                if callee is None or pysvf.isExtCall(callee):
                    # External and unknown-target calls pushed no frame, so there is
                    # nothing to pop. Execution still continues past them, so keep
                    # following the path.
                    for e in node.getOutEdges():
                        self.worklist.append((e.getDstNode(), stack))
                    continue
                # pop stack
                if stack:
                    top = stack[-1]   
                else:
                    continue # empty stack, skip

                callee_name = callee.getName()
                if top != callee_name:
                    continue # mismatched stack, skip
                new_stack = stack[:-1]

                # handle the nodes after return the current function
                for e in node.getOutEdges():
                    dst = e.getDstNode()
                    self.worklist.append((dst, new_stack))

            # -------------------------------------------------
            # handle normal node
            else:
                for e in node.getOutEdges():
                    dst = e.getDstNode()
                    self.worklist.append((dst, stack))