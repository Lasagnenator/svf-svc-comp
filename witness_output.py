import hashlib
import os
import datetime

from util import *

BASE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <key attr.name="isEntryNode" attr.type="boolean" for="node" id="entry">
  <default>false</default>
 </key>
 <key attr.name="isViolationNode" attr.type="boolean" for="node" id="violation">
  <default>false</default>
 </key>
 <key attr.name="witness-type" attr.type="string" for="graph" id="witness-type"/>
 <key attr.name="sourcecodelang" attr.type="string" for="graph" id="sourcecodelang"/>
 <key attr.name="producer" attr.type="string" for="graph" id="producer"/>
 <key attr.name="specification" attr.type="string" for="graph" id="specification"/>
 <key attr.name="programfile" attr.type="string" for="graph" id="programfile"/>
 <key attr.name="programhash" attr.type="string" for="graph" id="programhash"/>
 <key attr.name="architecture" attr.type="string" for="graph" id="architecture"/>
 <key attr.name="creationtime" attr.type="string" for="graph" id="creationtime"/>
 <graph edgedefault="directed">
  <data key="witness-type">{witness_type}</data>
  <data key="sourcecodelang">C</data>
  <data key="producer">SVF-SVC {version}</data>
  <data key="specification">{spec}</data>
  <data key="programfile">{file}</data>
  <data key="programhash">{hash}</data>
  <data key="architecture">{bits}</data>
  <data key="creationtime">{creation_time}</data>
  <node id="node0">
   <data key="entry">true</data>
   {violation}
  </node>
 </graph>
</graphml>
"""

VIOLATION_KEY = '<data key="violation">true</data>'

def generate_witness(result, args, output):
    if "Correct" in result:
        witness_type = "correctness_witness"
        violation = ""
    elif "Incorrect" in result:
        witness_type = "violation_witness"
        violation = VIOLATION_KEY
    else:
        # Unknown, do not produce a witness file.
        return

    with open(args.c_file, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    with open(args.prop, "r") as f:
        spec = f.read().strip()

    bits = "32bit" if args.bits == "32" else "64bit"

    data = {
        "witness_type": witness_type,
        "file": args.c_file,
        "hash": file_hash,
        "spec": spec,
        "version": VERSION,
        "bits": bits,
        "creation_time": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "violation": violation
    }

    if output == "":
        log("No witness output requested.")
        return

    log(f"Witness output path: {output}")
    log("Witness output data:")
    log(data)

    with open(output, "w") as f:
        f.write(BASE_TEMPLATE.format(**data))

# i didnt want to remove the old one so i copy pasted
def generate_witness_v2(result, source_file_path, prop_file_path, output):
    if "Correct" in result:
        witness_type = "correctness_witness"
        violation = ""
    elif "Incorrect" in result:
        witness_type = "violation_witness"
        violation = VIOLATION_KEY
    else:
        # Unknown, do not produce a witness file.
        return

    with open(source_file_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    with open(prop_file_path, "r") as f:
        spec = f.read().strip()

    bits = "32bit"

    data = {
        "witness_type": witness_type,
        "file": source_file_path,
        "hash": file_hash,
        "spec": spec,
        "version": VERSION,
        "bits": bits,
        "creation_time": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "violation": violation
    }

    if output == "":
        log("No witness output requested.")
        return

    log(f"Witness output path: {output}")
    log("Witness output data:")
    log(data)

    with open(output, "w") as f:
        f.write(BASE_TEMPLATE.format(**data))

