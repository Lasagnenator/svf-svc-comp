import pysvf
from pysvf import *
import typing
import sys
import yaml


import json
import re
from typing import Optional, Dict, Any

# Add any new features to be extracted in here.
FEATURES = {
    'main':                      'source',
    '__assert_fail':             'tainted_sink',
    'abort':                     'tainted_sink',
    'stdin':                     'tainted_source',
    'stdout':                    'tainted_sink',
    'stderr':                    'tainted_sink',
    '__VERIFIER_assert':         'assert',
    '__VERIFIER_error':          'tainted_sink',
    '__VERIFIER_atomic_begin':   'atomic_begin',
    '__VERIFIER_atomic_end':     'atomic_end',
    '__VERIFIER_nondet_int':     'nondet_int',
    '__VERIFIER_nondet_uint':    'nondet_uint',
    '__VERIFIER_nondet_long':    'nondet_long',
    '__VERIFIER_nondet_ulong':   'nondet_ulong',
    '__VERIFIER_nondet_double':  'nondet_double',
    '__VERIFIER_nondet_bool':    'nondet_bool',
    '__VERIFIER_nondet_char':    'nondet_char',
    '__VERIFIER_nondet_charp':   'nondet_charp',
    '__VERIFIER_nondet_pchar':   'nondet_pchar',
    '__VERIFIER_nondet_float':   'nondet_float',
    '__VERIFIER_nondet_loff_t':  'nondet_loff_t',
    '__VERIFIER_nondet_longlong':'nondet_longlong',
    '__VERIFIER_nondet_msg_t':   'nondet_msg_t',
    '__VERIFIER_nondet_sector_t':'nondet_sector_t',
    '__VERIFIER_nondet_short':   'nondet_short',
    '__VERIFIER_nondet_size_t':  'nondet_size_t',
    '__VERIFIER_nondet_u16':     'nondet_u16',
    '__VERIFIER_nondet_u32':     'nondet_u32',
    '__VERIFIER_nondet_u8':      'nondet_u8',
    '__VERIFIER_nondet_uint128': 'nondet_uint128',
    '__VERIFIER_nondet_uchar':   'nondet_uchar',
    '__VERIFIER_nondet_unsigned':'nondet_unsigned',
    '__VERIFIER_nondet_ulonglong':'nondet_ulonglong',
    '__VERIFIER_base_pointer':   'base_pointer',
}

class SourceLocation:
    """
    Parse the JSON string returned by SVF's getSourceLoc() method
    Format: { "ln": 11, "cl": 1, "fl": "input.c" }
    """
    
    def __init__(self, source_loc_str: str):
        """
        Initialize SourceLocation object
        
        Args:
            source_loc_str: String returned by getSourceLoc() method
        """
        self.source_loc_str = source_loc_str
        self.parsed_data = self._parse_source_loc()
    
    def _parse_source_loc(self) -> Dict[str, Any]:
        """
        Parse source location string
        
        Returns:
            Parsed dictionary data
        """
        try:
            # Try to parse JSON directly
            return json.loads(self.source_loc_str)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract using regex
            return self._parse_with_regex()
    
    def _parse_with_regex(self) -> Dict[str, Any]:
        """
        Parse source location string using regex
        
        Returns:
            Parsed dictionary data
        """
        result = {}
        
        # Extract line number
        ln_match = re.search(r'"ln":\s*(\d+)', self.source_loc_str)
        if ln_match:
            result['ln'] = int(ln_match.group(1))
        
        # Extract column number
        cl_match = re.search(r'"cl":\s*(\d+)', self.source_loc_str)
        if cl_match:
            result['cl'] = int(cl_match.group(1))
        
        # Extract filename
        fl_match = re.search(r'"fl":\s*"([^"]+)"', self.source_loc_str)
        if fl_match:
            result['fl'] = fl_match.group(1)
        
        return result
    
    def getLnNo(self) -> Optional[int]:
        """
        Get line number
        
        Returns:
            Line number, returns None if not exists
        """
        return self.parsed_data.get('ln')
    
    def getColNo(self) -> Optional[int]:
        """
        Get column number
        
        Returns:
            Column number, returns None if not exists
        """
        return self.parsed_data.get('cl')
    
    def getSourceFilename(self) -> Optional[str]:
        """
        Get source filename
        
        Returns:
            Source filename, returns None if not exists
        """
        return self.parsed_data.get('fl')
    
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary
        
        Returns:
            Dictionary containing all information
        """
        return self.parsed_data.copy()
    
    def __str__(self) -> str:
        """
        String representation
        
        Returns:
            Formatted string
        """
        parts = []
        if self.getLnNo() is not None:
            parts.append(f"line {self.getLnNo()}")
        if self.getColNo() is not None:
            parts.append(f"column {self.getColNo()}")
        if self.getSourceFilename() is not None:
            parts.append(f"file '{self.getSourceFilename()}'")
        
        if parts:
            return f"SourceLocation({', '.join(parts)})"
        else:
            return f"SourceLocation({self.source_loc_str})"
    
    def __repr__(self) -> str:
        return self.__str__()


def parse_source_location(source_loc_str: str) -> SourceLocation:
    """
    Convenience function: parse source location string
    
    Args:
        source_loc_str: String returned by getSourceLoc() method
    
    Returns:
        SourceLocation object
    """
    return SourceLocation(source_loc_str)


# Add convenience method for ICFGNode
def get_source_location_info(node) -> SourceLocation:
    """
    Get source location information for a node
    
    Args:
        node: ICFGNode object
    
    Returns:
        SourceLocation object
    """
    source_loc_str = node.getSourceLoc()
    return SourceLocation(source_loc_str)




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
icfg = pag.getICFG()


'''
target yaml
categories:
  property: CHECK( init(main()), LTL(G ! call(reach_error())) )
features:
- line: 3
  column: 22
  function: __assert_fail
  type: tainted_sink
- line: 8
  column: 27
  function: abort
  type: tainted_sink
- line: 14
  column: 20
  function: __VERIFIER_nondet_uint
  type: nondet_uint
'''

# Initialize yaml
yaml_dict = {
}

# Read demo prp to get categories.property:
# prp is just one line file, "CHECK( init(main()), LTL(G ! call(reach_error())) )"
with open('demo.prp', 'r') as file:
    prp = file.read()
    property = prp.strip()
    yaml_dict['categories'] = {
        'property': property
    }



yaml_dict['features'] = []
for node in icfg.getNodes():
    if isinstance(node, CallICFGNode):
        # main, __assert_fail, abort, __VERIFIER_nondet_uint
        source_loc = SourceLocation(node.getSourceLoc())
        func_name = node.getCalledFunction().getName()
        if func_name in FEATURES:
            yaml_dict['features'].append({
                'line': source_loc.getLnNo(),
                'column': source_loc.getColNo(),
                'function': func_name,
                'type': FEATURES[func_name]
            })

with open('demo.yaml', 'w') as file:
    yaml.dump(yaml_dict, file, sort_keys=False)






