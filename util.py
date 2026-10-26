import os
import sys
import traceback
from enum import Enum as _Enum
from typing import NoReturn

VERSION = "2.4"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relative))

class Log(str, _Enum):
    SETUP = "setup"
    SVF = "svf"
    REACH = "reach"
    MEMORY = "memory"
    TRACE = "trace"

def log(string, file=sys.stderr, category=None):
    text = str(string)
    if category is not None:
        text = "\n".join(f"[{category.value}] {line}" for line in text.split("\n"))

    file.write(text)
    file.write("\n")
    file.flush()

def log_exception(exception: Exception):
    # Log an exception's traceback
    log("".join(traceback.format_exception(exception)))

def fail(error, code=1) -> NoReturn:
    # error must be of the form ERROR(<word>)
    print(error)
    exit(code)
