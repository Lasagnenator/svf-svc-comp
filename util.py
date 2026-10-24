import os
import sys
import traceback
from enum import Enum as _Enum  # underscore: not re-exported by `from util import *`
from typing import NoReturn

VERSION = "2.4"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relative))

# Categories enabled via --verbose; set once at startup with set_verbose().
class Log(str, _Enum):
    SETUP = "setup"
    SVF = "svf"
    REACH = "reach"
    MEMORY = "memory"
    TRACE = "trace"

LOG_STATE = set()

def set_verbose(categories):
    LOG_STATE.clear()
    LOG_STATE.update(Log(c) for c in categories)

def log(string, file=sys.stderr, category=None):
    # Print to stderr by default. With a category, only print if it was enabled by --verbose.
    if category is not None and category not in LOG_STATE:
        return
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
