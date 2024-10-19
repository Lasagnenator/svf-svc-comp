import os

VERSION = "1.0 using SVF 3.0"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relative))

# Generic preprocessor fix.
INCLUDE_REPLACE = get_real_path("include_replace.c")

# TODO: Does this need to be relative to the script or the working directory?
WITNESS_FILE = get_real_path("witness.yml")
