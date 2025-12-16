"""
Output a format 2.1 witness.
"""

import datetime
import hashlib
import uuid
import yaml


"""
Sample witness
- entry_type: invariant_set
  metadata:
    format_version: 2.0
    uuid: dc8eb57e-7eb3-4c34-9422-460d710e73f5
    creation_time: '2025-07-02T17:34:34.967309'
    producer:
      name: svf-svc
      version: 2.0
    task:
      input_file:
      - multivar_1-1.c
      input_file_hashes:
        multivar_1-1.c: b3aae87953f96aa404e5e15573a1dcacf4cae28eb9871ce3f841ded6190a7177
      specification: CHECK( init(main()), LTL(G ! call(reach_error())) )
      data_model: ILP32
      language: C
  content:
  - invariant:
      type: loop_invariant
      location:
        file_name: multivar_1-1.c
        line: 22
        column: 0
        function: main
      value: ( y == x )
      format: c_expression

"""

def write_witness(invariants: list, input_files: list, specification: str, output_path: str) -> None:

    hashes = {}
    for file in input_files:
        hash = hashlib.sha256()
        with open(file, 'rb') as f:
            block = f.read(hash.block_size)
            while block:
                hash.update(block)
                block = f.read(hash.block_size)
        hashes[file] = hash.hexdigest()

    yaml_list = []
    yaml_list.append(dict())
    yaml_list[-1]['entry_type'] = 'invariant_set'
    yaml_list[-1]['metadata'] = {
        'format_version': 2.0,
        'uuid': str(uuid.uuid4()),
        'creation_time': datetime.datetime.now().isoformat()
    }

    yaml_list[-1]['metadata']['producer'] = {
        'name': 'svf-svc',
        'version': 2.0  # Update based on svc-svf version
        #'configuration': '(Optional)', The configuration in which the tool ran.
        #'command_line': '(Optional)', The command line with which the tool ran;
        #'description': '(Optional)' Any information not fitting in the previous items.

    }

    yaml_list[-1]['metadata']['task'] = {
        'input_file': input_files,
        'input_file_hashes': hashes,
        'specification': specification,
        'data_model': 'ILP32', # can be ILP32 or LP64
        'language': 'C'
    }
    yaml_list[-1]['content'] = []
    for invariant in invariants:

      yaml_list[-1]['content'].append(dict())
      yaml_list[-1]['content'][-1] = {'invariant': {
          'type': invariant['type'],  # can be loop_invariant or location_invariant
          'location' : {
            'file_name': invariant['file_name'],
            'line': invariant['line']
          },
          'value': invariant['value'],
          'format': 'c_expression'
        }
      }

      if invariant['column'] != None:
        yaml_list[-1]['content'][-1]['invariant']['location']['column'] = invariant['column'] # optional
      if invariant['function'] != None:
        yaml_list[-1]['content'][-1]['invariant']['location']['function'] = invariant['function'] # optional


    with open(output_path, 'w') as file:
        yaml.dump(yaml_list, file, default_style=None, sort_keys=False)

# Sample usage
if __name__ == "__main__":
  invariants = [{
      'type': 'loop_invariant',
      'file_name': 'multivar_1-1.c',
      'line': 22,
      'column': 0, # Set to None if not provided
      'function': 'main', # Set to None if not provided
      'value': '( y == x )',
    }]

  input_files = ['multivar_1-1.c']
  specification = 'CHECK( init(main()), LTL(G ! call(reach_error())) )'
  write_witness(invariants, input_files, specification, 'multivar_1-1.c.invariant_witness.yaml')
