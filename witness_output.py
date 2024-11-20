
import hashlib
import os
import time
from uuid import uuid4
import yaml

from util import *

def generate_metadata(file, file_hash, spec, data_model):
    format_version = 0.1
    uuid = str(uuid4())
    creation_time = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    producer = {
        "name": "SVF-SVC",
        "version": VERSION
    }
    task = {
        "input_files": [file],
        "input_file_hashes": {file: file_hash},
        "specification": spec,
        "data_model": data_model,
        "language": "C"
    }

    return {
        "format_version": format_version,
        "uuid": uuid,
        "creation_time": creation_time,
        "producer": producer,
        "task": task
    }

def generate_witness(svf_output, args, output):
    file = os.path.basename(args.c_file)
    with open(args.c_file, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    with open(args.prop, "r") as f:
        spec = f.read().strip()

    data_model = "ILP32" if args.bits == "32" else "LP64"

    metadata = generate_metadata(file, file_hash, spec, data_model)

    # Not correct. TODO: interpret SVF's internal graph.
    entry_type = "loop_invariant"
    location = {
        "file_name": file,
        "file_hash": file_hash,
        "line": 4,
        "column": 2,
        "function": "main"
    }
    loop_invariant = {
        "string": "(x >= 0U) && (x <= 4294967295U)",
        "type": "assertion",
        "format": "C"
    }

    data = {
        "entry_type": entry_type,
        "metadata": metadata,
        "location": location,
        "loop_invariant": loop_invariant
    }

    if args.verbose:
        log(data)

    with open(output, "w") as f:
        yaml.dump([data], f)
