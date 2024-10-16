
# Convert SVC's assert usage into SVF's asserts by a simple #define.
# The original function definition is renamed with Python.
svc_assert = "__VERIFIER_assert(int"
svc_assert_replace = f"__SVC_assert(int"
svc_assert_preamble = """
#define __VERIFIER_assert svf_assert
extern void svf_assert(bool);
"""[0]

def assert_replace(text: str):
    # Replace asserts with fake assert function name.
    # This prevents the #define from making a duplicate.
    replaced = text.replace(svc_assert, svc_assert_replace)
    return svc_assert_preamble + replaced

def apply_strategy(text: str, prop_file: str) -> (str, str):
    # Interpret the given property file and call the required function.
    # Also returns the required tool to use.

    if not prop_file:
        # DEBUG: default to reach safety.
        return assert_replace(text), "ae"

    with open(prop_file, "r") as f:
        prop_text = f.read()

    # Remove all spaces then check for what we are dealing with.
    prop_text = prop_text.replace(" ", "")

    if "LTL(G!call(reach_error()))" in prop_text:
        # Category 1: Reach Safety
        return assert_replace(text), "ae"

    if any(x in prop_text for x in ["LTL(Gvalid-memcleanup)", "LTL(Gvalid-free)"]):
        # Category 2: Memory Safety
        # - valid free
        # - valid deref
        # - valid memtrack
        # - valid memcleanup
        return "Not Implemented - Memory Safety", "saber"

    if "LTL(G!overflow)" in prop_text:
        # Category 4: Overflow Detection
        return "Not Implemented - Overflow Detection", "nul"

    if "Non-existant" in prop_text:
        # Category 6: Software Systems
        # This category is just real use cases of the other three categories.
        # This should never be hit.
        return "Not Implemented - Software Systems", "nul"

    return "UNKOWN PROPERTY", "nul"

"""
TODO: Get a list of SVF compatible functions and which executables to use.
For all of these, we need to know how to interpret the output of SVF.
If they need sub-categories for optimisation/whatever, then we probably need
to run SVF multiple times to get the right output/check.

Reachability:
- Which function to inject and what executable to use.

Mem safety:
- What executable to use.

Overflow:
- What executable to use.
- This one is signed integer overflow and it seems also buffer overflows.
"""
