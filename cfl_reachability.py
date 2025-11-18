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
            state_key = (node.getId(), stack)
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
            if isinstance(node, pysvf.CallICFGNode):
                callee = node.getCalledFunction()

                # we don't need to handle external calls
                if pysvf.isExtCall(callee):
                    pass
                # handle internal calls
                else:
                    # push stack
                    new_stack = stack + (callee,)

                    # jump to callee entry
                    entry = self.icfg.getFunEntryICFGNode(callee)
                    self.worklist.append((entry, new_stack))

                # also follow normal CFG to ret node
                ret_node = node.getRetICFGNode()
                self.worklist.append((ret_node, stack))  # will pop when handle ret

            # -------------------------------------------------
            # handle Ret node
            elif isinstance(node, pysvf.RetICFGNode):
                # pop stack
                if stack:
                    new_stack = stack[:-1]   
                else:
                    new_stack = stack

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