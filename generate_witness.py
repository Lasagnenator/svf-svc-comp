"""
Output YAML witnesses (format 2.0 by default): an invariant_set entry for a
correctness witness and a violation_sequence entry for a violation witness.
"""

import datetime
import hashlib
import uuid
import yaml
from util import VERSION

"""
Sample correctness witness
- entry_type: invariant_set
  metadata:
    format_version: '2.0'
    uuid: dc8eb57e-7eb3-4c34-9422-460d710e73f5
    creation_time: '2025-07-02T17:34:34+10:00'
    producer:
      name: svf-svc
      version: '2.0'
    task:
      input_files:
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
        column: 3
        function: main
      value: ( y == x )
      format: c_expression

Sample violation witness (same metadata, entry_type violation_sequence)
  content:
  - segment:
    - waypoint:
        type: assumption
        action: follow
        constraint:
          value: v == 0
          format: c_expression
        location:
          file_name: program.c
          line: 15
          column: 3
          function: main
  - segment:
    - waypoint:
        type: target
        action: follow
        location:
          file_name: program.c
          line: 23
          column: 5
          function: main
"""

WAYPOINT_TYPES = ('assumption', 'branching', 'target', 'function_enter', 'function_return')


def _metadata(input_files: list, specification: str, format_version: str, data_model: str) -> dict:
    """Build the metadata block, which correctness and violation witnesses share."""
    hashes = {}
    for file in input_files:
        hash = hashlib.sha256()
        with open(file, 'rb') as f:
            block = f.read(hash.block_size)
            while block:
                hash.update(block)
                block = f.read(hash.block_size)
        hashes[file] = hash.hexdigest()

    return {
        'format_version': format_version,
        'uuid': str(uuid.uuid4()),
        'creation_time': datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        'producer': {
            'name': 'svf-svc',
            'version': VERSION  # Update based on svc-svf version
            #'configuration': '(Optional)', The configuration in which the tool ran.
            #'command_line': '(Optional)', The command line with which the tool ran;
            #'description': '(Optional)' Any information not fitting in the previous items.
        },
        'task': {
            'input_files': input_files,
            'input_file_hashes': hashes,
            'specification': specification,
            'data_model': data_model,
            'language': 'C'
        },
    }


def _write(entries: list, output_path: str) -> None:
    with open(output_path, 'w') as file:
        yaml.dump(entries, file, default_style=None, sort_keys=False)


def write_witness(invariants: list, input_files: list, specification: str, output_path: str, format_version: str = '2.0', data_model: str = 'LP64') -> None:

    yaml_list = []
    yaml_list.append(dict())
    yaml_list[-1]['entry_type'] = 'invariant_set'
    yaml_list[-1]['metadata'] = _metadata(input_files, specification, format_version, data_model)
    yaml_list[-1]['content'] = []
    for invariant in invariants:
      if (
          not isinstance(invariant, dict)
          or invariant.get('type') not in ('loop_invariant', 'location_invariant')
          or invariant.get('file_name') not in input_files
          or any(type(invariant.get(key)) is not int or invariant[key] < 1
                 for key in ('line', 'column'))
          or any(not isinstance(invariant.get(key), str) or not invariant[key].strip()
                 for key in ('function', 'value'))
      ):
        continue
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

    _write(yaml_list, output_path)


def _waypoint(point: dict, input_files: list) -> dict:
    """Render one waypoint, rejecting anything the format 2.0 schema would not accept."""
    if not isinstance(point, dict):
        raise ValueError(f'waypoint must be a dict: {point!r}')
    kind = point.get('type')
    if kind not in WAYPOINT_TYPES:
        raise ValueError(f'unknown waypoint type: {kind!r}')
    action = point.get('action', 'follow')
    if action not in ('follow', 'avoid'):
        raise ValueError(f'waypoint action must be follow or avoid: {action!r}')
    if point.get('file_name') not in input_files:
        raise ValueError(f'waypoint file is not an input file: {point.get("file_name")!r}')
    line, column, function = point.get('line'), point.get('column'), point.get('function')
    if type(line) is not int or line < 1:
        raise ValueError(f'waypoint line must be an integer of at least 1: {line!r}')
    if column is not None and (type(column) is not int or column < 1):
        raise ValueError(f'waypoint column must be an integer of at least 1: {column!r}')
    if function is not None and (not isinstance(function, str) or not function.strip()):
        raise ValueError(f'waypoint function must be a non-empty string: {function!r}')

    rendered = {'type': kind, 'action': action}
    constraint = point.get('constraint')
    if kind in ('target', 'function_enter'):
        if constraint is not None:
            raise ValueError(f'{kind} waypoints take no constraint')
    elif kind == 'branching':
        # true/false for if, while and ?:; for switch, the case value or 'default'.
        if isinstance(constraint, bool):
            rendered['constraint'] = {'value': 'true' if constraint else 'false'}
        elif type(constraint) is int or constraint == 'default':
            rendered['constraint'] = {'value': constraint}
        else:
            raise ValueError(f'branching constraint must be a bool, an int or "default": {constraint!r}')
    else:
        if not isinstance(constraint, str) or not constraint.strip():
            raise ValueError(f'{kind} waypoints need a non-empty constraint')
        # function_return only accepts ACSL of the form "\\result <op> <constant>".
        language = 'c_expression' if kind == 'assumption' else 'acsl_expression'
        rendered['constraint'] = {'value': constraint, 'format': language}

    location = {'file_name': point['file_name'], 'line': line}
    if column is not None:
        location['column'] = column
    if function is not None:
        location['function'] = function
    rendered['location'] = location
    return {'waypoint': rendered}


def write_violation_witness(segments: list, input_files: list, specification: str, output_path: str, format_version: str = '2.0', data_model: str = 'LP64') -> None:
    """Write a violation witness describing a path to the property violation.

    `segments` is a list of segments in execution order. Each segment is a list of
    waypoint dicts with the keys type (one of WAYPOINT_TYPES), file_name and line,
    and optionally action ('follow' by default, or 'avoid'), column, function and
    constraint. The constraint is a C expression for assumption, a bool (or a switch
    case value) for branching, ACSL for function_return, and absent for target and
    function_enter.

    A segment is zero or more avoid waypoints followed by exactly one follow
    waypoint, and the follow waypoint of the last segment, and only that one, is the
    target. Unlike an invariant, a bad waypoint cannot simply be dropped, since the
    remaining segments would describe a different path, so anything malformed
    raises ValueError and nothing is written.
    """
    if not segments:
        raise ValueError('a violation witness needs at least one segment')
    content = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, list) or not segment:
            raise ValueError(f'segment {index} must be a non-empty list of waypoints')
        *avoided, followed = segment
        if any(not isinstance(point, dict) or point.get('action', 'follow') != 'avoid'
               or point.get('type') == 'target' for point in avoided):
            raise ValueError(f'segment {index}: only its last waypoint may be followed, '
                             'and a target cannot be avoided')
        if not isinstance(followed, dict) or followed.get('action', 'follow') != 'follow':
            raise ValueError(f'segment {index} must end with a follow waypoint')
        if (followed.get('type') == 'target') != (index == len(segments) - 1):
            raise ValueError(f'segment {index}: the target must end the last segment, and only it')
        content.append({'segment': [_waypoint(point, input_files) for point in segment]})

    entry = {
        'entry_type': 'violation_sequence',
        'metadata': _metadata(input_files, specification, format_version, data_model),
        'content': content,
    }
    _write([entry], output_path)


# Sample usage
if __name__ == "__main__":
  invariants = [{
      'type': 'loop_invariant',
      'file_name': 'multivar_1-1.c',
      'line': 22,
      'column': None, # Set to None if not provided, accept integer geq 1 and None
      'function': 'main', # Set to None if not provided
      'value': '( y == x )',
    }]

  input_files = ['multivar_1-1.c']
  specification = 'CHECK( init(main()), LTL(G ! call(reach_error())) )'
  write_witness(invariants, input_files, specification, 'witness.yml', '2.0')
