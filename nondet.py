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
    "u32": "u32",
    "uchar": "unsigned char",
    "uint": "unsigned int",
    "uint128": "unsigned __int128",
    "ulong": "unsigned long",
    "ulonglong": "unsigned long long",
    "unsigned": "unsigned",
    "ushort": "unsigned short",
}

def generate_nondet(c_code):
    # Create definitions for all the nondet functions if they are present.
    # Only add them if they are needed.
    # Add these definitions at the end of the C file to preserve line numbers.
    # TODO: Find out if this step can be removed.
    defs = [""]

    for svc_type, c_type in nondet_types.items():
        if f"__VERIFIER_nondet_{svc_type}" in c_code:
            defs.append(f"{c_type} __VERIFIER_nondet_{svc_type}() {{ {c_type} val; return val; }}")
            util.log(f"Added definition: {c_type} __VERIFIER_nondet_{svc_type}.")

    defs.append("")
    return "\n".join(defs)
