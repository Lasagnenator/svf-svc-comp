import os
import sys
import traceback
from typing import NoReturn

VERSION = "1.8"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relative))

def log(string, file=sys.stderr):
    # Print to stderr by default
    file.write(str(string))
    file.write("\n")
    file.flush()

def log_exception(exception: Exception):
    # Log an exception's traceback
    log("".join(traceback.format_exception(exception)))

def fail(error, code=1) -> NoReturn:
    # error must be of the form ERROR(<word>)
    print(error)
    exit(code)

# Generic preprocessor fix.
INCLUDE_REPLACE = get_real_path("include_replace.c")
