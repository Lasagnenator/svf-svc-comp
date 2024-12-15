import os
import sys

VERSION = "1.5 using SVF 3.0"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relative))

def log(string, file=sys.stderr):
    # Print to stderr by default
    file.write(str(string))
    file.write("\n")
    file.flush()

def fail(error, code=1):
    # error must be of the form ERROR(<word>)
    print(error)
    exit(code)

# Generic preprocessor fix.
INCLUDE_REPLACE = get_real_path("include_replace.c")
