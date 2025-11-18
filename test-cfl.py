import os
import subprocess
import sys
import pysvf
from cfl_reachability import CFLreachability  

def compile_to_bc(src):
    if src.endswith(".c"):
        bc = src.replace(".c", ".bc")
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
