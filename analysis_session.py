"""Compile an input and manage the native resources for one analysis run."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
from typing import Generator, Any

import pysvf

import nondet
from AbstractInterpretation import AbstractExecution
from util import Log, log


@dataclass(frozen=True)
class AnalysisSession:
    """Resources borrowed for the duration of the analysis_session block."""

    pag: pysvf.SVFIR
    ae: AbstractExecution
    input_line_count: int


class ClangError(RuntimeError):
    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode


class SVFSetupError(RuntimeError):
    """PySVF could not build or expose the PAG."""


class AESetupError(RuntimeError):
    """The abstract execution engine could not be initialized."""


def _compile_input(input_path: str | Path, llvm_path: str, bits: str) -> int:
    with open(input_path) as source:
        c_code = source.read()
    generated_code = c_code + nondet.generate_nondet(c_code)

    with tempfile.NamedTemporaryFile("w", suffix=".c") as working_source:
        working_source.write(generated_code)
        working_source.flush()
        log("Generated file:", category=Log.SETUP)
        log(generated_code, category=Log.SETUP)

        # Older SV-COMP tasks need these diagnostics demoted and a higher bracket limit.
        command = [
            "clang-21", f"-m{bits}", "-S", "-O0", "-fno-discard-value-names",
            "-g", "-emit-llvm", "-Wno-error=int-conversion",
            "-Wno-error=implicit-function-declaration",
            "-Wno-error=incompatible-function-pointer-types", "-fbracket-depth=1024",
            "-o", llvm_path, working_source.name,
        ]
        log(f"Running clang with command: {' '.join(command)}", category=Log.SETUP)
        try:
            returncode = subprocess.run(command).returncode
        except OSError as exc:
            raise ClangError(f"Could not run clang-21: {exc}") from exc

        log(f"Clang exited with code {returncode}.", category=Log.SETUP)
        if returncode != 0:
            raise ClangError(f"Clang failed to output {llvm_path}.", returncode)

    # Witnesses must not point into the appended nondet definitions.
    return len(c_code.splitlines())


@contextmanager
def analysis_session(
    input_path: str | Path,
    bits: str,
    threshold_widening: bool = False,
    stop_on_gap: bool = False,
) -> Generator[AnalysisSession, Any, None]:
    """Prepare AE without running it; keep the PAG live through witness export.

    PySVF owns process-global native state, so sessions must not overlap.
    Do not use the PAG, AE, or native-backed results after leaving the block.
    """
    with ExitStack() as stack:
        llvm_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".ll"))
        input_line_count = _compile_input(input_path, llvm_file.name, bits)

        try:
            pysvf.buildSVFModule([llvm_file.name])
            # A successful build owns native state even if getPAG() fails.
            stack.callback(pysvf.releasePAG)
            pag = pysvf.getPAG()
        except Exception as exc:
            raise SVFSetupError("Could not load the PySVF module.") from exc

        try:
            ae = AbstractExecution(pag)
            ae.threshold_widening = threshold_widening
            ae.stop_on_gap = stop_on_gap
        except Exception as exc:
            raise AESetupError("Could not initialize abstract execution.") from exc

        yield AnalysisSession(pag, ae, input_line_count)
