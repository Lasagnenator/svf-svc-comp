import pysvf
from pysvf import *
import typing
import sys
import yaml

if len(sys.argv) < 2:
    print("Usage: python SVFIR.py [options] <bitcode_file>")
    sys.exit(1)

# Get the pag(SVFIR) from the bitcode file
sys.argv.extend([
    "-model-arrays=true",
    "-pre-field-sensitive=false",
    "-model-consts=true",
    "-stat=false"
])

# Skip the python script name and use the rest of the arguments
svf_arguments = sys.argv[1:]
pysvf.buildSVFModule(svf_arguments)
pag = pysvf.getPAG()
callgraph = pag.getCallGraph()

'''
target yaml
categories:
  - property: CHECK( init(main()), LTL(G ! call(reach_error())) )
externs:
  - name: main
    line: 13
    column: 0
    type: source
  - name: __assert_fail
    line: 3
    column: 22
    type: tainted_sink
  - name: abort
    line: 8
    column: 27
    type: tainted_sink
  - name: __VERIFIER_nondet_uint
    line: 14
    column: 20
    type: nondet_uint
'''

# init yaml
yaml_dict = {
}

# read demo prp to get categories.property:
# prp is just one line file, "CHECK( init(main()), LTL(G ! call(reach_error())) )"
with open('demo.prp', 'r') as file:
    prp = file.read()
    property = prp.strip()
    print(property)
    yaml_dict['categories'] = {
        'property': property
    }

yaml_dict['externs'] = []
for node in callgraph.getNodes():
    # main, __assert_fail, abort, __VERIFIER_nondet_uint
    if node.getFunction().getName() == "__assert_fail":
        yaml_dict['externs'].append({
            'name': node.getFunction().getName(),
            'line': 0, # TODO: get line number
            'column': 0, # TODO: get column number
            'type': 'tainted_sink'
        })

        pass
    elif node.getFunction().getName() == "abort":
        yaml_dict['externs'].append({
            'name': node.getFunction().getName(),
            'line': 0, # TODO: get line number
            'column': 0, # TODO: get column number
            'type': 'tainted_sink'
        })

        pass
    elif node.getFunction().getName() == "__VERIFIER_nondet_uint":
        yaml_dict['externs'].append({
            'name': node.getFunction().getName(),
            'line': 0, # TODO: get line number
            'column': 0, # TODO: get column number
            'type': 'nondet_uint'
        })
        pass
    elif node.getFunction().getName() == "main":
        yaml_dict['externs'].append({
            'name': node.getFunction().getName(),
            'line': 0, # TODO: get line number
            'column': 0, # TODO: get column number
            'type': 'source'
        })
        pass

with open('demo.yaml', 'w') as file:
    yaml.dump(yaml_dict, file)






