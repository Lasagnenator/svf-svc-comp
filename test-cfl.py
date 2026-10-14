import os
import subprocess
import sys
import pysvf
from cfl_reachability import CFLreachability  

def compile_to_bc(src):
    if src.endswith(".c"):
        bc = "/tmp/" + os.path.basename(src).replace(".c", ".bc")
        cmd = ["clang", "-S", "-c", "-emit-llvm", "-O0", "-g", "-o", bc, src]
        subprocess.check_call(cmd)
        return bc
    return src

if __name__ == "__main__":
    # check sys.argv
    if len(sys.argv) < 2:
        print("Usage: python3 test-cfl.py <path-to-c-file-or-bc-file>")
        sys.exit(1)

    input_file = sys.argv[1]

    bcfile = compile_to_bc(input_file)

    print("Building SVF module...")
    pysvf.buildSVFModule(bcfile)

    # Get the Program Assignment Graph
    pag = pysvf.getPAG()

        # ===== ICFG DEBUG =====
    icfg = pag.getICFG()

    print("\n====== ICFG DEBUG ======")

    for node in icfg.getNodes():
        fun = node.getFun()
        fun_name = fun.getName() if fun else "None"

        print(
            f"\nNODE id={node.getId()} "
            f"type={type(node).__name__} "
            f"fun={fun_name}"
        )

        if isinstance(node, pysvf.CallICFGNode):
            callee = node.getCalledFunction()
            print(
                f"  CALLS: "
                f"{callee.getName() if callee else 'None'}"
            )

            ret = node.getRetICFGNode()
            if ret:
                print(
                    f"  MATCHED RET: "
                    f"id={ret.getId()} "
                    f"type={type(ret).__name__}"
                )

        for edge in node.getOutEdges():
            dst = edge.getDstNode()

            dst_fun = dst.getFun()
            dst_fun_name = dst_fun.getName() if dst_fun else "None"

            print(
                f"  OUT -> "
                f"id={dst.getId()} "
                f"type={type(dst).__name__} "
                f"fun={dst_fun_name}"
            )

    print("\n====== END ICFG DEBUG ======\n")

    print("Running CFL reachability analysis...")
    cfl = CFLreachability(pag)
    results = cfl.analyze()

    print("\n====== CFL Reachability Results ======")
    if results["reach"]:
        print("Reachable reach_error(): YES")
        for feasible, node in results["reach"]:
            print(f"  - Feasible: {feasible}, at node: {node}")
    else:
        print("Reachable reach_error(): NO")

    pysvf.releasePAG()
