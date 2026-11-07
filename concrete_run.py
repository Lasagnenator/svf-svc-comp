import os
import re
import shutil
import subprocess
import tempfile

import util

# Exit codes the stubs use to tell the outcome apart from the program's own exit codes.
REACHED_ERROR = 97
NONDET_CALLED = 98

TIMEOUT_SECONDS = 10

# Linked into every run: definitions for the __VERIFIER_* functions the task only
# declares.
STUBS = util.get_real_path("concrete_stubs.c")

# gcc is preferred: it has ASan and, with gcc-multilib, 32-bit linking. clang-21 in our
# image has neither, so it can only build 64-bit reach tasks.
COMPILERS = ["gcc", "clang-21"]

# Maps each ASan / LSan report kind to the memory-safety subproperty it violates.
# Any other report gives no verdict.
SANITIZER_KINDS = [
    (re.compile(r"LeakSanitizer: detected memory leaks"), "valid-memtrack"),
    (re.compile(r"AddressSanitizer: (attempting double-free|attempting free on address"
                r"|bad-free)"), "valid-free"),
    (re.compile(r"AddressSanitizer: (heap-use-after-free|heap-buffer-overflow"
                r"|stack-buffer-overflow|global-buffer-overflow|dynamic-stack-buffer-overflow"
                r"|stack-buffer-underflow|stack-use-after-return|stack-use-after-scope"
                r"|SEGV)"), "valid-deref"),
]

def find_compiler():
    for compiler in COMPILERS:
        if shutil.which(compiler):
            return compiler
    return None

def get_details(run, reach, source, executable, site_file):
    """
    Return the violation the finished run shows, or None if it shows none.
    For reach, the line is the reach_error call site, found from the return address
    the stubs wrote to site_file.
    For memory, the subproperty comes from the sanitizer report, and the line and
    function from its innermost frame inside the task file.
    """
    if reach:
        if run.returncode != REACHED_ERROR:
            util.log(f"Concrete run: exited with {run.returncode} without reaching reach_error.",
                     category=util.Log.SETUP)
            return None

        line = None
        if os.path.exists(site_file):
            with open(site_file) as f:
                address = int(f.read().strip(), 16)
            # The return address points just past the call, so step back one byte.
            try:
                result = subprocess.run(["addr2line", "-e", executable, hex(address - 1)],
                                        capture_output=True, text=True)
                match = re.search(r":(\d+)", result.stdout)
                if match:
                    line = int(match.group(1))
            except OSError:
                pass
        if line is None:
            util.log("Concrete run: reached reach_error, but could not find the line of the call.",
                     category=util.Log.SETUP)
        return {"subproperty": "unreach-call", "line": line, "function": None}

    subproperty = None
    for pattern, kind in SANITIZER_KINDS:
        if pattern.search(run.stderr):
            subproperty = kind
            break
    if subproperty is None:
        util.log(f"Concrete run: exited with {run.returncode}, no memory violation seen.",
                 category=util.Log.SETUP)
        return None

    line = None
    function = None
    frame = re.compile(r"#\d+ 0x[0-9a-f]+ in (\S+) " + re.escape(source) + r":(\d+)")
    match = frame.search(run.stderr)
    if match:
        function = match.group(1)
        line = int(match.group(2))
    elif subproperty != "valid-memtrack":
        util.log(f"Concrete run: {subproperty} seen, but no frame in the task file gives its line.",
                 category=util.Log.SETUP)
    return {"subproperty": subproperty, "line": line, "function": function}

# TODO Add modeling for nondet values
# TODO Add further value guidance from AE
def find_violation(source, prop_file_name, bits="64"):
    """
    Compile and run the task at source once. 
    Returns None when the run shows no violation.
    """
    source = os.path.abspath(source)
    reach = prop_file_name == "unreach-call.prp"
    memory = prop_file_name in ["valid-memsafety.prp", "valid-memcleanup.prp"]
    if not reach and not memory:
        return None

    compiler = find_compiler()
    if compiler is None:
        util.log("Concrete run: no C compiler found.", category=util.Log.SETUP)
        return None

    with tempfile.TemporaryDirectory(prefix="svf-concrete-") as work:
        executable = os.path.join(work, "task")
        site_file = os.path.join(work, "site")

        # -no-pie keeps addresses equal to those addr2line reads from the binary.
        command = [compiler, f"-m{bits}", "-w", "-std=gnu99", "-fcommon", "-O0", "-g", "-no-pie",
                   "-msse2", "-mfpmath=sse",
                   "-finstrument-functions",
                   f"-DREACHED_ERROR={REACHED_ERROR}",
                   f"-DNONDET_CALLED={NONDET_CALLED}"]
        if memory:
            command.extend(["-fsanitize=address", "-fno-omit-frame-pointer"])
        command.extend([source, STUBS, "-lm", "-o", executable])

        try:
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            util.log(f"Concrete run: could not compile ({repr(e)}).", category=util.Log.SETUP)
            return None
        if built.returncode != 0:
            util.log(f"Concrete run: compile failed: {built.stderr[-500:]}", category=util.Log.SETUP)
            return None

        environment = os.environ.copy()
        environment["CONCRETE_SITE"] = site_file
        environment["ASAN_OPTIONS"] = "detect_leaks=1:detect_stack_use_after_return=1"
        try:
            run = subprocess.run([executable], capture_output=True, text=True, errors="replace",
                                 timeout=TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
                                 env=environment, cwd=work)
        except subprocess.TimeoutExpired:
            util.log("Concrete run: timed out, no verdict.", category=util.Log.SETUP)
            return None

        if run.returncode == NONDET_CALLED:
            util.log("Concrete run: called a nondet function, no verdict.", category=util.Log.SETUP)
            return None

        details = get_details(run, reach, source, executable, site_file)

    if details is not None and prop_file_name == "valid-memcleanup.prp":
        if details["subproperty"] != "valid-memtrack":
            return None
    return details
