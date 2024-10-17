
# Inject SVF's reachability code into the SVC reach code.
svc_reach_code = "void reach_error()"
# Hide the original reach_error function.
svc_reach_replace = "void svc_reach_error()"
# TODO: change svf_reach into the actual reachability function.
svc_reach_preamble = """
extern void svf_assert(bool);
void svf_reach() {svf_assert(false);}
#define reach_error svf_reach
"""

def reach_inject(text: str):
    # Inject SVF's reachability into the reach_error function.
    # This prevents the #define from making a duplicate.
    replaced = text.replace(svc_reach_code, svc_reach_replace)
    return svc_reach_preamble + replaced

def apply_strategy(text: str, prop_file: str = "") -> (str, str, list):
    # Interpret the given property file and call the required function.
    # Also returns the required tool to use and additional args.

    if not prop_file:
        # DEBUG: default to reach safety.
        return reach_inject(text), "ae", []

    with open(prop_file, "r") as f:
        prop_text = f.read()

    # Remove all spaces then check for what we are dealing with.
    prop_text = prop_text.replace(" ", "")

    if "LTL(G!call(reach_error()))" in prop_text:
        # Category 1: Reach Safety
        return reach_inject(text), "ae", []

    if any(x in prop_text for x in ["LTL(Gvalid-memcleanup)", "LTL(Gvalid-free)", "LTL(Gvalid-deref)", "LTL(Gvalid-memtrack)"]):
        # Category 2: Memory Safety
        # - valid free
        # - valid deref
        # - valid memtrack
        # - valid memcleanup

        # saber, -dfree, -leak
        return "Not Implemented - Memory Safety", "saber", ["-dfree", "-leak"]

    if "LTL(G!overflow)" in prop_text:
        # Category 4: Overflow Detection
        # This currently only does buffer overflow detection.
        # ae, -overflow
        return text, "ae", ["-overflow"]

    if "Non-existant" in prop_text:
        # Category 6: Software Systems
        # This category is just real use cases of the other three categories.
        # This if statement should never be hit.
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
