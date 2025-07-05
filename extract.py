import pysvf
from pysvf import *
import typing
import sys
import yaml


import json
import re
from typing import Optional, Dict, Any

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

# Initialize yaml
yaml_dict = {
}

# Read demo prp to get categories.property:
# prp is just one line file, "CHECK( init(main()), LTL(G ! call(reach_error())) )"
with open('demo.prp', 'r') as file:
    prp = file.read()
    property = prp.strip()
    print(property)
    yaml_dict['categories'] = {
        'property': property
    }

yaml_dict['externs'] = []
for node in icfg.getNodes():
    if isinstance(node, CallICFGNode):
        # main, __assert_fail, abort, __VERIFIER_nondet_uint
        source_loc = SourceLocation(node.getSourceLoc())
        if node.getCalledFunction().getName() == "__assert_fail":
            yaml_dict['externs'].append({
                'line': source_loc.getLnNo(),
                'column': source_loc.getColNo(),
                'function': node.getCalledFunction().getName(),
                'type': 'tainted_sink'
            })

            pass
        elif node.getCalledFunction().getName() == "abort":
            yaml_dict['externs'].append({
                'line': source_loc.getLnNo(),
                'column': source_loc.getColNo(),
                'function': node.getCalledFunction().getName(),
                'type': 'tainted_sink'
            })

            pass
        elif node.getCalledFunction().getName() == "__VERIFIER_nondet_uint":
            yaml_dict['externs'].append({                
                'line': source_loc.getLnNo(),
                'column': source_loc.getColNo(),
                'function': node.getCalledFunction().getName(),
                'type': 'nondet_uint'
            })
            pass
        elif node.getCalledFunction().getName() == "main":
            yaml_dict['externs'].append({                
                'line': source_loc.getLnNo(),
                'column': source_loc.getColNo(),
                'function': node.getCalledFunction().getName(),
                'type': 'source'
            })
            pass

with open('demo.yaml', 'w') as file:
    yaml.dump(yaml_dict, file, sort_keys=False)






