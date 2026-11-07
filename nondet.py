"""
Add nondet function implementations when they are declared.
"""

import util

nondet_types = {
    "bool": "_Bool",
    "char": "char",
    "int": "int",
    "int128": "__int128",
    "float": "float",
    "double": "double",
    "loff_t": "loff_t",
    "long": "long",
    "longlong": "long long",
    "pchar": "char*",
    "short": "short",
    "size_t": "size_t",
    "u32": "unsigned int",
    "uchar": "unsigned char",
    "uint": "unsigned int",
    "uint128": "unsigned __int128",
    "ulong": "unsigned long",
    "ulonglong": "unsigned long long",
    "unsigned": "unsigned",
    "ushort": "unsigned short",
}

nondet_memory = """void __VERIFIER_nondet_memory(void *mem, size_t size) {
    unsigned char *p = mem;
    for (size_t i = 0; i < size; i++) {
        p[i] = __VERIFIER_nondet_uchar();
    }
}"""

def add_nondet(defs: list, svc_type, c_type):
    defs.append(f"{c_type} __VERIFIER_nondet_{svc_type}() {{ {c_type} val; return val; }}")
    util.log(f"Added definition: {c_type} __VERIFIER_nondet_{svc_type}.")

def generate_nondet(c_code):
    # Create definitions for all the nondet functions if they are present.
    # Only add them if they are needed.
    # Add these definitions at the end of the C file to preserve line numbers.
    defs = [""]
    types_added = []

    for svc_type, c_type in nondet_types.items():
        if f"__VERIFIER_nondet_{svc_type}" in c_code:
            add_nondet(defs, svc_type, c_type)
            types_added.append(svc_type)

    if "__VERIFIER_nondet_memory" in c_code:
        if "uchar" not in types_added:
            # Memory depends on uchar.
            util.log("Adding uchar definition due to dependency.")
            add_nondet(defs, "uchar", nondet_types["uchar"])
        defs.append(nondet_memory)
        util.log(f"Added definition: void __VERIFIER_nondet_memory.")

    defs.append("")
    return "\n".join(defs)
