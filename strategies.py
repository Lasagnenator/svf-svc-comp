import re
import subprocess
import util
from typing import Tuple

strategy_type = Tuple[str, str, list[str], int]

# Hide the original reach_error function.
svc_reach_code = r"void reach_error *?\("
svc_reach_replace = "void svc_reach_error("

svc_reach_preamble = """
extern void svf_assert(_Bool);
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

svc_main = r"int main *?\("
svc_main_replace = "int svf_main("

def reach_inject(text: str) -> str:
    # SVF cannot handle loops. If there's a "for" or "while", exit
    if "for" in text or "while" in text:
        util.fail("Unknown")

    # Hide original reach_error
    replaced = re.sub(svc_reach_code, svc_reach_replace, text)
    # Replace the main function
    replaced = re.sub(svc_main, svc_main_replace, replaced)
    return svc_reach_preamble + replaced + svc_reach_post

def reach_safety(text) -> strategy_type:
    util.log("apply_strategy: Category 1 - Reach Safety")
    return reach_inject(text), "ae", ["-output", "/dev/nul"], 1

def mem_safety(text) -> strategy_type:
    util.log("apply_strategy: Category 2 - Memory Safety")
    return text, "saber", ["-dfree", "-leak"], 2

def overflow(text) -> strategy_type:
    # This currently only does buffer overflow detection.
    util.log("apply_strategy: Category 4 - Overflow Detection")
    return text, "ae", ["-overflow", "-output", "/dev/nul"], 4

def apply_strategy(text: str, prop_file: str = "") -> strategy_type:
    # Interpret the given property file and call the required function.
    # Returns modified code, SVF tool, extra options and category.

    if not prop_file:
        return reach_safety(text)

    with open(prop_file, "r") as f:
        prop_text = f.read()

    if "LTL(G ! call(reach_error()))" in prop_text:
        # Category 1: Reach Safety
        return reach_safety(text)

    if any(x in prop_text for x in ["LTL(G valid-memcleanup)", "LTL(G valid-free)", "LTL(G valid-deref)", "LTL(G valid-memtrack)"]):
        # Category 2: Memory Safety
        # - valid free
        # - valid deref
        # - valid memtrack
        # - valid memcleanup
        return mem_safety(text)

    if "LTL(G ! overflow)" in prop_text:
        # Category 4: Overflow Detection
        return overflow(text)

    # Catch all.
    util.log(f"apply_strategy: Unknown property {prop_text}")
    util.fail("Unknown", 0)

def interpret_output(process: subprocess.CompletedProcess, strategy: strategy_type):
    replaced, exe, svf_options, category = strategy

    SVF_stdout = process.stdout
    SVF_stderr = process.stderr

    util.log(f"SVF stdout:\n{SVF_stdout}")
    util.log(f"SVF stderr:\n{SVF_stderr}")

    if category == 1:
        # AE with asserts to determine reachability.
        if b"svf_assert Fail." in SVF_stderr:
            return "REACH Incorrect"
        elif b"The assertion is successfully verified!!" in SVF_stderr:
            return "REACH Correct"

    elif category == 2:
        # SABER with memory checking.
        if b"NeverFree" in SVF_stderr:
            return "MEMORY Incorrect"
        elif SVF_stderr == b"":
            return "MEMORY Correct"

    elif category == 4:
        # AE with overflow detection
        if b"Buffer overflow" in SVF_stderr:
            return "OVERFLOW Incorrect"
        elif b"(0 found)" in SVF_stderr:
            return "OVERFLOW Correct"

    # Unknown.
    return "Unknown"
