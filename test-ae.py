from AbstractInterpretation import *

if __name__ == "__main__":
    # check sys.argv and print friendly error message if not enough arguments
    if len(sys.argv) < 2:
        print("Usage: python3 test-ae.py <path-to-bc-file>")
        sys.exit(1)
    pysvf.buildSVFModule(sys.argv[1:])  # Build Program Assignment Graph (SVFIR)
    pag = pysvf.getPAG()
    ass3 = AbstractExecution(pag)
    ass3.analyse()
    pysvf.releasePAG()