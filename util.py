import os
import sys
import traceback
from enum import Enum, auto
from typing import NoReturn

VERSION = "3.0-dev"

def get_real_path(relative):
    # Find the real path given a path relative to the current file
    return os.path.normpath(os.path.join(os.path.dirname(__file__), relative))

class Log(str, Enum):
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

def report_unknown(exception: Exception):
    # Log the exception and report Unknown
    log_exception(exception)
    print("Unknown")

class Property(Enum):
    REACH_SAFETY = auto()
    MEM_SAFETY = auto()
    MEM_CLEANUP = auto()
    UNSUPPORTED = auto()

def get_property(property_path: str) -> Property:
    prop = property_path.split('/')[-1]
    if "reach" in prop:
        return Property.REACH_SAFETY
    elif "memsafety" in prop:
        return Property.MEM_SAFETY
    elif "memcleanup" in prop:
        return Property.MEM_CLEANUP
    else:
        return Property.UNSUPPORTED
