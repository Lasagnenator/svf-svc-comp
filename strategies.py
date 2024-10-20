import subprocess

# Hide the original reach_error function.
svc_reach_code = "void reach_error("
svc_reach_replace = "void svc_reach_error("

svc_reach_preamble = """
extern void svf_assert(bool);
int svf_svc_reach_test = 0;
void reach_error() {svf_svc_reach_test = 1;}
void svf_abort() {} // Do nothing.
#define abort svf_abort
"""

svc_reach_post = """
int main(void) {
    int ret = svf_main();
    svf_assert(svf_svc_reach_test == 0);
    return ret;
}
"""

svc_main = "int main("
svc_main_replace = "int svf_main("

def reach_inject(text: str):
    # Hide original reach_error
    replaced = text.replace(svc_reach_code, svc_reach_replace)
    # Replace the main function
    replaced = replaced.replace(svc_main, svc_main_replace)
    return svc_reach_preamble + replaced + svc_reach_post

def apply_strategy(text: str, prop_file: str = "") -> (str, str, list, int):
    # Interpret the given property file and call the required function.
    # Returns modified code, SVF tool, extra options and category.

    if not prop_file:
        print("DEBUG: no property file chosen, default to reachability.")
        return reach_inject(text), "ae", ["-output", "/dev/nul"], 1

    with open(prop_file, "r") as f:
        prop_text = f.read()

    # Remove all spaces then check for what we are dealing with.
    prop_text = prop_text.replace(" ", "")

    if "LTL(G!call(reach_error()))" in prop_text:
        # Category 1: Reach Safety
        return reach_inject(text), "ae", ["-output", "/dev/nul"], 1

    if any(x in prop_text for x in ["LTL(Gvalid-memcleanup)", "LTL(Gvalid-free)", "LTL(Gvalid-deref)", "LTL(Gvalid-memtrack)"]):
        # Category 2: Memory Safety
        # - valid free
        # - valid deref
        # - valid memtrack
        # - valid memcleanup
        return text, "saber", ["-dfree", "-leak"], 2

    if "LTL(G!overflow)" in prop_text:
        # Category 4: Overflow Detection
        # This currently only does buffer overflow detection.
        return text, "ae", ["-overflow", "-output", "/dev/nul"], 4

    if "Non-existant" in prop_text:
        # Category 6: Software Systems
        # This category is just real use cases of the other three categories.
        # This if statement should never be hit.
        return "Not Implemented - Software Systems", "nul", 6

    return "UNKOWN PROPERTY", "nul"

def interpret_output(process: subprocess.CompletedProcess, strategy):
    replaced, exe, svf_options, category = strategy

    SVF_stdout = process.stdout
    SVF_stderr = process.stderr

    if category == 1:
        # AE with asserts to determine reachability.
        if b"svf_assert Fail." in SVF_stderr:
            return "Incorrect"
        elif b"The assertion is successfully verified!!" in SVF_stderr:
            return "Correct"

    elif category == 2:
        # SABER with memory checking.
        if b"NeverFree" in SVF_stderr:
            return "Incorrect"
        elif SVF_stderr == b"":
            return "Correct"

    elif category == 4:
        # AE with overflow detection
        if b"Buffer overflow" in SVF_stderr:
            return "Incorrect"
        elif b"(0 found)" in SVF_stderr:
            return "Correct"

    # Unknown.
    print(f"Category: {category}")
    print(SVF_stdout)
    print(SVF_stderr)
    return "Unknown"
