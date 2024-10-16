
# Convert SVC's assert usage into SVF's asserts by a simple #define.
# The original function definition is renamed with Python.
svc_assert = "__VERIFIER_assert(int"
svc_assert_replace = f"__SVC_assert(int"
svc_assert_preamble = """
#define __VERIFIER_assert svf_assert
"""

def assert_replace(text: str):
    # Replace asserts with fake assert function name.
    # This prevents the #define from making a duplicate.
    replaced = text.replace(svc_assert, svc_assert_replace)
    return svc_assert_preamble + replaced

def apply_strategy(text: str, prop_file: str):
    # Interpret the given property file and call the required function.
    # Also returns the required tool to use.
    with open(prop_file, "r") as f:
        prop_text = f.read()

    # Remove all spaces then check for what we are dealing with.
    prop_text = prop_text.replace(" ", "")

    if "LTL(G!call(reach_error()))" in prop_text:
        # Category 1: Reach Safety
        return assert_replace(text)

    if any(x in prop_text for x in ["LTL(Gvalid-memcleanup)", "LTL(Gvalid-free)"]):
        # Category 2: Memory Safety
        return "Not Implemented"

    if "LTL(G!overflow)" in prop_text:
        # Category 4: Overflow Detection
        return "Not Implemented"

    if "Non-existant" in prop_text:
        # Category 6: Software Systems
        # This category is just real use cases of the other three categories.
        # This should never be hit.
        return "Not Implemented"
    return "UNKOWN PROPERTY"
