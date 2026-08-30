#!/usr/bin/env python3
"""Run svf-svc against a local SV-COMP benchmark corpus.

This is a lightweight local progress runner, not a replacement for BenchExec or
witness validation. It deliberately never downloads benchmarks.

Example usage from the svf-svc repository root:
    python tests/tester.py /mnt/sv-benchmarks "$PWD" \
        --reach --set Arrays --sample-count 10 --seed 0
    python tests/tester.py /mnt/sv-benchmarks "$PWD" \
        --reach --safety --cleanup --sample-count 100 --dry-run
"""

import argparse
import csv
from dataclasses import asdict, dataclass
import datetime
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shlex
import signal
import subprocess
import sys
import time

import yaml


PROPERTY_NAMES = {
    "unreach-call.prp": "reach",
    "no-overflow.prp": "overflow",
    "valid-memsafety.prp": "safety",
    "valid-memcleanup.prp": "cleanup",
}
SUPPORTED_PROPERTIES = {"reach", "safety", "cleanup"}
RESULT_RE = re.compile(r"^(?:REACH|MEMORY|CLEANUP|OVERFLOW) (Correct|Incorrect)$")
ERROR_RE = re.compile(r"^ERROR(?:\([^)]+\))?$")
SCORE = {
    (True, "true"): 2,
    (False, "false"): 1,
    (True, "false"): -16,
    (False, "true"): -32,
}


@dataclass(frozen=True)
class Task:
    run_id: str
    yaml_path: Path
    yaml_relative: str
    input_files: tuple[str, ...]
    property_file: str
    property_name: str
    expected: bool
    data_model: str
    subproperty: str | None = None

    @property
    def stratum(self):
        return (self.property_name, self.data_model, str(self.expected).lower())


@dataclass
class Result:
    run_id: str
    task_file: str
    input_files: list[str]
    property: str
    property_file: str
    expected: bool
    data_model: str
    subproperty: str | None
    answer: str
    classification: str
    score: int
    return_code: int | None
    termination_reason: str
    signal: str | None
    wall_seconds: float
    error_code: str | None
    error_message: str | None
    log_path: str
    rerun_command: str


def parse_sample(value):
    text = value.strip()
    if text.endswith("%"):
        text = text[:-1]
    try:
        percent = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("sample must be a percentage, such as 1%") from error
    if not 0 < percent <= 100:
        raise argparse.ArgumentTypeError("sample must be greater than 0 and at most 100%")
    return percent


def parse_sample_count(value):
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("sample count must be a positive integer") from error
    if count <= 0:
        raise argparse.ArgumentTypeError("sample count must be a positive integer")
    return count


def canonical_property(path):
    return PROPERTY_NAMES.get(Path(path).name)


def normalize_inputs(value):
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ValueError("input_files must be a path or a list of paths")


def resolve_set_files(corpus_root, selectors):
    set_root = (corpus_root / "c").resolve()
    resolved = set()
    for selector in selectors:
        pattern = selector if selector.endswith(".set") else f"{selector}.set"
        if any(character in pattern for character in "*?["):
            matches = [Path(path) for path in glob.glob(str(set_root / pattern))]
        else:
            matches = [set_root / pattern]
        valid = []
        for path in matches:
            path = path.resolve()
            try:
                path.relative_to(set_root)
            except ValueError:
                continue
            if path.is_file() and path.suffix == ".set":
                valid.append(path)
        if not valid:
            raise ValueError(f"set selector matches no .set files: {selector}")
        resolved.update(valid)
    return sorted(resolved, key=lambda path: path.relative_to(corpus_root).as_posix())


def expand_set_files(corpus_root, set_files):
    set_root = (corpus_root / "c").resolve()
    memberships = {}
    metadata = []
    raw_match_count = 0

    for set_path in set_files:
        if set_path.name in {"CorrectnessWitnesses.set", "ViolationWitnesses.set"}:
            raise ValueError(
                f"witness-validation set is not supported by svf_run.py: {set_path.name}"
            )
        entries = 0
        set_matches = set()
        try:
            lines = set_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise ValueError(f"cannot read set file {set_path}: {error}") from error
        for line_number, raw_line in enumerate(lines, 1):
            pattern = raw_line.strip()
            if not pattern or pattern.startswith("#"):
                continue
            entries += 1
            pattern_path = Path(pattern)
            if pattern_path.is_absolute() or ".." in pattern_path.parts or pattern.endswith(".set"):
                raise ValueError(f"{set_path}:{line_number}: invalid set entry: {pattern}")
            matches = sorted(Path(path).resolve() for path in glob.glob(str(set_path.parent / pattern)))
            if not matches:
                raise ValueError(f"{set_path}:{line_number}: pattern matches nothing: {pattern}")
            for path in matches:
                try:
                    path.relative_to(set_root)
                except ValueError as error:
                    raise ValueError(
                        f"{set_path}:{line_number}: match escapes corpus c/: {path}"
                    ) from error
                if not path.is_file() or path.suffix != ".yml":
                    raise ValueError(f"{set_path}:{line_number}: match is not a YAML task: {path}")
                raw_match_count += 1
                set_matches.add(path)
                memberships.setdefault(path, set()).add(set_path.name)
        if not entries or not set_matches:
            raise ValueError(f"set file selects no YAML tasks: {set_path}")
        metadata.append({
            "path": set_path.relative_to(corpus_root).as_posix(),
            "sha256": hashlib.sha256(set_path.read_bytes()).hexdigest(),
            "entry_count": entries,
            "matched_yaml_count": len(set_matches),
        })

    yaml_paths = sorted(memberships, key=lambda path: path.relative_to(corpus_root).as_posix())
    return yaml_paths, metadata, {
        "raw_match_count": raw_match_count,
        "unique_yaml_count": len(yaml_paths),
        "duplicate_count": raw_match_count - len(yaml_paths),
    }


def load_tasks(yaml_path, corpus_root, enabled):
    relative = yaml_path.relative_to(corpus_root).as_posix()
    try:
        with yaml_path.open() as stream:
            definition = yaml.safe_load(stream)
    except Exception as error:
        raise ValueError(f"cannot parse YAML: {error}") from error
    if not isinstance(definition, dict):
        raise ValueError("top-level YAML value is not a mapping")
    if "format_version" not in definition:
        return []
    inputs = normalize_inputs(definition.get("input_files"))
    options = definition.get("options") or {}
    data_model = options.get("data_model", "unknown") if isinstance(options, dict) else "unknown"
    properties = definition.get("properties")
    if not isinstance(properties, list):
        raise ValueError("properties is not a list")

    tasks = []
    for index, prop in enumerate(properties):
        if not isinstance(prop, dict) or not isinstance(prop.get("property_file"), str):
            continue
        property_file = prop["property_file"]
        property_name = canonical_property(property_file)
        if property_name not in enabled or property_name is None:
            continue
        expected = prop.get("expected_verdict")
        if not isinstance(expected, bool):
            continue
        identity = f"{relative}\0{index}\0{property_file}"
        run_id = hashlib.sha256(identity.encode()).hexdigest()[:16]
        tasks.append(Task(run_id, yaml_path, relative, inputs, property_file,
                          property_name, expected, str(data_model), prop.get("subproperty")))
    return tasks


def discover_tasks(args, yaml_paths=None):
    corpus_root = args.bench_root
    enabled = {name for name in PROPERTY_NAMES.values() if getattr(args, name)}
    tasks = []
    discovery_errors = []
    candidates = yaml_paths if yaml_paths is not None else sorted((corpus_root / "c").rglob("*.yml"))
    for yaml_path in candidates:
        relative = yaml_path.relative_to(corpus_root).as_posix()
        if "witness" in relative:
            continue
        if args.specific and args.specific not in relative:
            continue
        if any(skip in relative for skip in args.skip):
            continue
        try:
            tasks.extend(load_tasks(yaml_path, corpus_root, enabled))
        except ValueError as error:
            discovery_errors.append((relative, str(error)))
    return tasks, discovery_errors


def stable_rank(task, seed):
    return hashlib.sha256(f"{seed}\0{task.run_id}".encode()).digest()


def sample_tasks(tasks, percent, seed, count=None):
    if not tasks:
        return []
    if count is not None:
        if count > len(tasks):
            raise ValueError(f"sample count {count} exceeds population {len(tasks)}")
        wanted = count
    elif percent is None or percent == 100:
        return sorted(tasks, key=lambda task: task.run_id)
    else:
        wanted = max(1, math.ceil(len(tasks) * percent / 100))

    properties = {}
    for task in tasks:
        properties.setdefault(task.property_name, []).append(task)
    property_order = sorted(
        properties,
        key=lambda name: hashlib.sha256(f"{seed}\0property\0{name}".encode()).digest(),
    )

    selected = []
    for property_name in property_order[:min(wanted, len(property_order))]:
        selected.append(min(
            properties[property_name],
            key=lambda task: stable_rank(task, seed),
        ))
    if len(selected) == wanted:
        return sorted(selected, key=lambda task: stable_rank(task, seed))

    selected_ids = {task.run_id for task in selected}
    remaining_tasks = [task for task in tasks if task.run_id not in selected_ids]
    remaining_wanted = wanted - len(selected)
    strata = {}
    for task in remaining_tasks:
        strata.setdefault(task.stratum, []).append(task)

    quotas = []
    assigned = 0
    for key, members in strata.items():
        exact = remaining_wanted * len(members) / len(remaining_tasks)
        base = math.floor(exact)
        tie_breaker = hashlib.sha256(f"{seed}\0{key}".encode()).digest()
        quotas.append([key, base, exact - base, tie_breaker])
        assigned += base
    quotas.sort(key=lambda item: (-item[2], item[3]))
    for index in range(remaining_wanted - assigned):
        quotas[index][1] += 1

    for key, count, _, _ in quotas:
        ranked = sorted(strata[key], key=lambda task: stable_rank(task, seed))
        selected.extend(ranked[:count])
    return sorted(selected, key=lambda task: stable_rank(task, seed))


def limit_resources(cpu_seconds, memory_bytes):
    os.setsid()
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def classify(stdout, stderr, return_code, timed_out):
    if timed_out:
        return "unknown", "timeout", None, "wall-time limit exceeded", "wall_timeout", None
    combined_lines = (stdout + "\n" + stderr).splitlines()
    result_lines = [match.group(1) for line in combined_lines
                    if (match := RESULT_RE.fullmatch(line.strip()))]
    error_codes = [line.strip() for line in combined_lines
                   if ERROR_RE.fullmatch(line.strip())]
    if return_code != 0:
        signal_name = None
        if return_code is not None and return_code < 0:
            try:
                signal_name = signal.Signals(-return_code).name
            except ValueError:
                signal_name = f"SIG{-return_code}"
        reason = "signal" if signal_name else ("start_failure" if return_code is None else "nonzero_exit")
        message = diagnostic_tail(stderr or stdout)
        if not message:
            message = f"tool terminated with {signal_name or f'exit code {return_code}'}"
        return ("unknown", "tool_error", error_codes[-1] if error_codes else None,
                message, reason, signal_name)
    if len(set(result_lines)) > 1:
        return "unknown", "tool_error", None, "conflicting verdicts in tool output", "invalid_output", None
    if result_lines:
        answer = "true" if result_lines[-1] == "Correct" else "false"
        return answer, "result", None, None, "completed", None
    if any(line.strip() == "Unknown" for line in combined_lines):
        return "unknown", "unknown", None, diagnostic_tail(stderr), "completed", None
    return ("unknown", "tool_error", error_codes[-1] if error_codes else None,
            diagnostic_tail(stderr or stdout) or "tool produced no recognized verdict",
            "invalid_output", None)


def diagnostic_tail(text, lines=12):
    nonempty = [line for line in text.splitlines() if line.strip()]
    return "\n".join(nonempty[-lines:]) or None


def safe_log_name(task):
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", task.yaml_relative)
    return f"{stem}.{task.property_name}.{task.run_id}.log"


def unsupported_reason(task):
    if task.property_name == "overflow":
        return ("UNSUPPORTED_PROPERTY",
                "svf_run.py currently checks buffer bounds for no-overflow.prp, not signed-integer overflow")
    if task.property_name not in SUPPORTED_PROPERTIES:
        return ("UNSUPPORTED_PROPERTY",
                f"svf_run.py does not implement the {task.property_name} property")
    if task.property_name in {"safety", "cleanup"} and task.data_model == "unknown":
        return ("UNSUPPORTED_DATA_MODEL", "memory properties require an ILP32 or LP64 data model")
    if task.data_model not in {"ILP32", "LP64", "unknown"}:
        return ("UNSUPPORTED_DATA_MODEL", f"unsupported data model: {task.data_model}")
    if len(task.input_files) != 1:
        return ("MULTIPLE_INPUTS",
                f"svf_run.py accepts one input file, but task declares {len(task.input_files)}")
    return None


def score_eligible(task):
    return unsupported_reason(task) is None


def run_task(task, args, logs_dir):
    yaml_dir = task.yaml_path.parent
    input_paths = [str((yaml_dir / item).resolve()) for item in task.input_files]
    property_path = str((yaml_dir / task.property_file).resolve())
    command = [sys.executable, str(args.svf_root / "svf_run.py")]
    command.extend(input_paths)
    command.extend(["--prop", property_path, "--witness", "", "--time-limit", str(args.cpu_limit)])
    if task.data_model == "ILP32":
        command.extend(["--bits", "32"])
    elif task.data_model == "LP64":
        command.extend(["--bits", "64"])
    rerun = shlex.join(command)

    log_path = logs_dir / safe_log_name(task)
    unsupported = unsupported_reason(task)
    if unsupported:
        error_code, message = unsupported
        log_path.write_text(message + "\n")
        return Result(
            run_id=task.run_id, task_file=task.yaml_relative, input_files=input_paths,
            property=task.property_name, property_file=property_path,
            expected=task.expected, data_model=task.data_model,
            subproperty=task.subproperty, answer="unknown",
            classification="unsupported", score=0, return_code=None,
            termination_reason="unsupported", signal=None, wall_seconds=0.0,
            error_code=error_code, error_message=message,
            log_path=str(log_path), rerun_command=rerun,
        )
    started = time.monotonic()
    timed_out = False
    return_code = None
    process = None
    try:
        process = subprocess.Popen(
            command, cwd=yaml_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace",
            preexec_fn=lambda: limit_resources(args.cpu_limit, args.memory_limit_mib * 1024 * 1024),
        )
        try:
            stdout, stderr = process.communicate(timeout=args.wall_limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        return_code = process.returncode
    except KeyboardInterrupt:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        raise
    except Exception as error:
        stdout, stderr = "", f"runner failed to start tool: {error!r}"
    wall_seconds = time.monotonic() - started
    answer, classification, error_code, error_message, termination_reason, signal_name = classify(
        stdout, stderr, return_code, timed_out)
    score = SCORE.get((task.expected, answer), 0)
    log_path.write_text(
        f"command: {rerun}\ncwd: {yaml_dir}\nreturn_code: {return_code}\n"
        f"wall_seconds: {wall_seconds:.6f}\n\n===== STDOUT =====\n{stdout}"
        f"\n===== STDERR =====\n{stderr}", errors="replace")
    return Result(
        run_id=task.run_id, task_file=task.yaml_relative, input_files=input_paths,
        property=task.property_name, property_file=property_path,
        expected=task.expected, data_model=task.data_model,
        subproperty=task.subproperty, answer=answer,
        classification=classification, score=score, return_code=return_code,
        termination_reason=termination_reason, signal=signal_name,
        wall_seconds=wall_seconds, error_code=error_code,
        error_message=error_message, log_path=str(log_path), rerun_command=rerun,
    )


def summarize(results, population, selected, elapsed, interrupted=False):
    counts = {}
    for result in results:
        key = result.classification if result.answer == "unknown" else (
            "correct" if result.answer == str(result.expected).lower() else "wrong")
        counts[key] = counts.get(key, 0) + 1
    eligible = [task for task in selected if score_eligible(task)]
    maximum = sum(2 if task.expected else 1 for task in eligible)
    return {
        "schema_version": 1,
        "provisional": True,
        "note": "Raw SV-COMP-style score; witnesses are not validated by this local runner.",
        "population": population,
        "selected": len(selected),
        "completed": len(results),
        "score_eligible": len(eligible),
        "score": sum(result.score for result in results),
        "maximum_selected_score": maximum,
        "counts": counts,
        "wall_seconds": elapsed,
        "interrupted": interrupted,
    }


def write_csv(path, results):
    with path.open("w", newline="") as stream:
        fields = list(Result.__dataclass_fields__)
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run svf-svc on an existing local SV-COMP corpus and compute a provisional score.")
    parser.add_argument("bench_root", type=Path, help="existing benchmark root containing c/")
    parser.add_argument("svf_root", type=Path, help="svf-svc repository root")
    parser.add_argument("--reach", action="store_true", help="test unreach-call properties")
    parser.add_argument("--safety", action="store_true", help="test valid-memsafety properties")
    parser.add_argument("--cleanup", action="store_true", help="test valid-memcleanup properties")
    parser.add_argument("--overflow", action="store_true", help="test no-overflow properties")
    parser.add_argument("--specific", help="only task paths containing this text")
    parser.add_argument("--skip", action="append", default=[], help="skip task paths containing this text")
    parser.add_argument("--set", dest="sets", action="append", default=[], metavar="SET",
                        help="restrict discovery to an SV-COMP .set file; repeat to union sets")
    sample_group = parser.add_mutually_exclusive_group()
    sample_group.add_argument("--sample", type=parse_sample,
                              help="deterministic percentage, e.g. 1%%")
    sample_group.add_argument("--sample-count", type=parse_sample_count,
                              help="deterministic exact number of property runs")
    parser.add_argument("--seed", default="0", help="sampling seed (default: 0)")
    parser.add_argument("--dry-run", action="store_true", help="select tasks without running svf-svc")
    parser.add_argument("--profile", choices=("quick", "competition"), default="quick",
                        help="resource profile (default: quick)")
    parser.add_argument("--cpu-limit", type=int, help="override CPU seconds per run")
    parser.add_argument("--wall-limit", type=int, help="override wall seconds per run")
    parser.add_argument("--memory-limit-mib", type=int, help="override memory MiB per run")
    parser.add_argument("--results-dir", type=Path, help="output directory (default: test-results/<timestamp>)")
    parser.add_argument("--output", type=Path, help="also write flattened CSV to this path")
    parser.add_argument("--verbose", "-v", action="count", default=0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.bench_root = args.bench_root.resolve()
    args.svf_root = args.svf_root.resolve()
    profile_limits = {
        "quick": (30, 45, 5120),
        "competition": (960, 1020, 15360),
    }
    defaults = profile_limits[args.profile]
    args.cpu_limit = args.cpu_limit or defaults[0]
    args.wall_limit = args.wall_limit or defaults[1]
    args.memory_limit_mib = args.memory_limit_mib or defaults[2]
    if not any((args.reach, args.safety, args.cleanup, args.overflow)):
        build_parser().error("select at least one property flag")
    if not (args.bench_root / "c").is_dir():
        build_parser().error(f"benchmark root has no c/ directory: {args.bench_root}")
    if not (args.svf_root / "svf_run.py").is_file():
        build_parser().error(f"svf_run.py not found under: {args.svf_root}")
    if min(args.cpu_limit, args.wall_limit, args.memory_limit_mib) <= 0:
        build_parser().error("resource limits must be positive")

    try:
        set_files = resolve_set_files(args.bench_root, args.sets)
        if set_files:
            yaml_paths, set_metadata, set_counts = expand_set_files(args.bench_root, set_files)
        else:
            yaml_paths, set_metadata = None, []
            set_counts = {"raw_match_count": 0, "unique_yaml_count": 0, "duplicate_count": 0}
    except ValueError as error:
        build_parser().error(str(error))

    tasks, discovery_errors = discover_tasks(args, yaml_paths)
    if not tasks:
        build_parser().error("no benchmark-property runs matched the requested filters")
    try:
        selected = sample_tasks(tasks, args.sample, args.seed, args.sample_count)
    except ValueError as error:
        build_parser().error(str(error))
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    results_dir = (args.results_dir or args.svf_root / "test-results" / timestamp).resolve()
    if results_dir.exists() and any(results_dir.iterdir()):
        build_parser().error(f"results directory is not empty: {results_dir}")
    logs_dir = results_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "corpus": str(args.bench_root),
        "tool": str(args.svf_root / "svf_run.py"),
        "set_selectors": args.sets,
        "set_files": set_metadata,
        "set_yaml_count_before_deduplication": set_counts["raw_match_count"],
        "set_yaml_count": set_counts["unique_yaml_count"],
        "set_duplicate_count": set_counts["duplicate_count"],
        "sample_percent": args.sample,
        "sample_count": args.sample_count,
        "seed": args.seed,
        "profile": args.profile,
        "limits": {
            "cpu_seconds": args.cpu_limit,
            "wall_seconds": args.wall_limit,
            "memory_mib": args.memory_limit_mib,
        },
        "resource_backend": "POSIX process group with per-process rlimits and a runner wall timeout",
        "population": len(tasks),
        "score_eligible_population": sum(score_eligible(task) for task in tasks),
        "score_eligible_selected": sum(score_eligible(task) for task in selected),
        "selected_by_property": {
            property_name: sum(task.property_name == property_name for task in selected)
            for property_name in sorted({task.property_name for task in selected})
        },
        "selected": [asdict(task) | {"yaml_path": str(task.yaml_path)} for task in selected],
        "discovery_errors": [{"task_file": path, "error": error} for path, error in discovery_errors],
    }
    (results_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    eligible_selected = sum(score_eligible(task) for task in selected)
    eligible_population = sum(score_eligible(task) for task in tasks)
    print(f"Selected {len(selected)} of {len(tasks)} property runs "
          f"({eligible_selected} of {eligible_population} score-eligible); results: {results_dir}")
    if args.verbose:
        for task in selected:
            print(f"  {task.run_id} {task.yaml_relative}::{task.property_name} "
                  f"expected={str(task.expected).lower()} model={task.data_model}")
    if discovery_errors:
        print(f"Warning: {len(discovery_errors)} task definitions could not be read; see manifest.json", file=sys.stderr)
    if args.dry_run:
        print("Dry run complete; svf-svc was not executed.")
        return 0

    results = []
    started = time.monotonic()
    interrupted = False
    jsonl_path = results_dir / "results.jsonl"
    try:
        with jsonl_path.open("w") as stream:
            for index, task in enumerate(selected, 1):
                result = run_task(task, args, logs_dir)
                results.append(result)
                stream.write(json.dumps(asdict(result)) + "\n")
                stream.flush()
                status = "OK" if result.answer == str(result.expected).lower() else result.classification.upper()
                print(f"[{index}/{len(selected)}] {status:<10} {result.score:+3d} "
                      f"score={sum(item.score for item in results):+d} "
                      f"{result.wall_seconds:.2f}s {task.yaml_relative}::{task.property_name}")
                if result.classification in {"tool_error", "timeout", "unsupported"}:
                    print(f"  log: {result.log_path}", file=sys.stderr)
                    print(f"  rerun: {result.rerun_command}", file=sys.stderr)
                    if result.error_message:
                        print("  " + result.error_message.replace("\n", "\n  "), file=sys.stderr)
    except KeyboardInterrupt:
        interrupted = True
        print("Interrupted; writing partial summary.", file=sys.stderr)

    summary = summarize(results, len(tasks), selected, time.monotonic() - started, interrupted)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_csv(args.output, results)
    print(f"Provisional score: {summary['score']:+d}/{summary['maximum_selected_score']} "
          f"from {summary['completed']}/{summary['selected']} runs")
    print("Counts: " + ", ".join(f"{key}={value}" for key, value in sorted(summary["counts"].items())))
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
