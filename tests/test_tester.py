"""
Run unit tests with:
python -m unittest tests.test_tester -v
"""

import csv
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import generate_witness
import invariants
import yaml

from tests import tester


ROOT = Path(__file__).resolve().parents[1]
TESTER_PATH = ROOT / "tests" / "tester.py"


class WitnessExportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('clang-21'), 'clang-21 is not installed')
    def test_ast_uses_physical_positions_and_operator_kinds(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'program.c'
            source.write_text(
                '#line 400 "logical.c"\nint main(void) {\n'
                '  int x = 0, y = 0; volatile int value = 0;\n'
                ' \twhile (1) { x += 1; }\n  do { y--; } while (1);\n}\n')
            loops = invariants._source_loops(source)
            self.assertEqual([(loop['line'], loop['column']) for loop in loops], [(4, 3), (5, 3)])
            self.assertEqual([loop['allowed_names'] for loop in loops], [{'y'}, {'x'}])

    @mock.patch.object(invariants.subprocess, 'run')
    def test_failed_ast_dump_is_skipped(self, run):
        for failure in (FileNotFoundError('clang-21'),
                        SimpleNamespace(returncode=1, stdout=''),
                        SimpleNamespace(returncode=0, stdout='not JSON')):
            run.side_effect = failure if isinstance(failure, Exception) else None
            run.return_value = failure
            self.assertEqual(invariants._source_loops('program.c'), [])

    @unittest.skipUnless(shutil.which('clang-21'), 'clang-21 is not installed')
    def test_loop_coordinates_and_stable_variables(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.c"
            source.write_text(
                "void escape(int *);\nint main(void) {\n"
                "  int i = 0, x = 0, y = 0;\n  escape(&y);\n"
                "  for (i = 0; 1; i++) {\n    x;\n  }\n}\n")
            loop, = invariants._source_loops(source)
            self.assertEqual((loop['line'], loop['column']), (5, 3))
            self.assertEqual(loop['allowed_names'], {'x'})
            head = mock.Mock()
            head.getSourceLoc.return_value = '{"ln": 6, "cl": 5, "fl": "temporary.c"}'
            head.getFun.return_value.getName.return_value = 'main'
            state = object()
            analysis = SimpleNamespace(cycle_head_to_cycle={head: None}, pre_abs_trace={head: state})
            with mock.patch.object(invariants, 'invariant_at', return_value='(x == 0)') as render:
                entry, = invariants.extract_loop_invariants(analysis, None, str(source))
            self.assertEqual((entry['line'], entry['column']), (5, 3))
            render.assert_called_once_with(head, state, None, None, {'x'}, 5)

    def test_missing_locations_and_unparsed_source_are_skipped(self):
        head = mock.Mock()
        analysis = SimpleNamespace(cycle_head_to_cycle={head: None}, pre_abs_trace={})
        with mock.patch.object(invariants, '_source_loops', return_value=[]):
            for location in ('', '{"ln": 0}', '{"ln": 1}', '{"ln": 1, "cl": 0}'):
                head.getSourceLoc.return_value = location
                self.assertEqual(invariants.extract_loop_invariants(analysis, None, 'missing.c'), [])
        self.assertEqual(invariants._source_loops('/nonexistent/witness-source.c'), [])

    def test_incomplete_invariant_records_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'program.c'
            source.write_text('int main(void) { while (1) {} }\n')
            witness = Path(directory) / 'witness.yml'
            record = {'type': 'loop_invariant', 'file_name': str(source), 'line': 1,
                      'column': 18, 'function': 'main', 'value': '1'}
            incomplete = [None] + [record | {key: None} for key in ('line', 'column', 'function', 'value')]
            generate_witness.write_witness(
                incomplete + [record], [str(source)], 'G ! call(reach_error())', str(witness))
            entry, = yaml.safe_load(witness.read_text())
            self.assertEqual(entry['metadata']['format_version'], '2.0')
            self.assertEqual(len(entry['content']), 1)
            location = entry['content'][0]['invariant']['location']
            self.assertEqual(location, {'file_name': str(source), 'line': 1, 'column': 18, 'function': 'main'})

    def test_wrapper_reports_missing_columns_without_starting_cpachecker(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / 'witness.yml'
            witness.write_text(yaml.safe_dump([{'entry_type': 'invariant_set', 'content': [
                {'invariant': {'location': {'file_name': 'program.c', 'line': 1}}}]}]))
            with mock.patch.dict('os.environ', {'CPACHECKER_HOME': directory}):
                home = Path(directory)
                (home / 'bin').mkdir()
                (home / 'bin' / 'cpachecker').symlink_to('/bin/false')
                result = subprocess.run(
                    [str(ROOT / 'tests' / 'validate_witness.sh'), str(witness), 'program.c', 'prop.prp', '64'],
                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('explicit positive invariant line and column', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            witness.write_text(yaml.safe_dump([{'entry_type': 'invariant_set', 'content': [
                {'invariant': {'location': {'file_name': 'program.c', 'line': 1, 'column': 1}}}]}]))
            with mock.patch.dict('os.environ', {'CPACHECKER_HOME': directory}):
                result = subprocess.run(
                    [str(ROOT / 'tests' / 'validate_witness.sh'), str(witness), 'program.c', 'prop.prp', '64'],
                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('explicit invariant function name', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


class TesterUnitTests(unittest.TestCase):
    def test_peak_memory_is_per_run_and_captured_by_poll(self):
        peaks = []
        for allocation in (96 * 1024 * 1024, 0):
            with tester.MeasuredPopen(
                    [sys.executable, "-c", f"data = bytearray({allocation})"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
                process.communicate(timeout=10)
                self.assertEqual(process.poll(), 0)
                self.assertIsNotNone(process.peak_memory_mib)
                peaks.append(process.peak_memory_mib)
        self.assertGreater(peaks[0], peaks[1] + 32)

        with tester.MeasuredPopen([sys.executable, "-c", "pass"]) as process:
            with mock.patch.object(tester.os, "wait4", wraps=tester.os.wait4) as wait:
                process._internal_poll()
                wait.assert_called_once_with(process.pid, tester.os.WNOHANG)
            process.wait(timeout=10)
            self.assertGreater(process.peak_memory_mib, 0)

    def make_task(self, identity, property_name="reach", data_model="LP64", expected=True):
        return tester.Task(
            identity, Path(f"/corpus/c/group/{identity}.yml"),
            f"c/group/{identity}.yml", (f"{identity}.c",),
            "../properties/unreach-call.prp", property_name, expected, data_model, None,
        )

    def test_score_matrix(self):
        self.assertEqual(tester.SCORE[(True, "true")], 2)
        self.assertEqual(tester.SCORE[(False, "false")], 1)
        self.assertEqual(tester.SCORE[(True, "false")], -16)
        self.assertEqual(tester.SCORE[(False, "true")], -32)

    def test_sampling_is_exact_deterministic_and_order_independent(self):
        tasks = [
            self.make_task(f"task-{index}", data_model="ILP32" if index % 2 else "LP64",
                           expected=index % 3 != 0)
            for index in range(101)
        ]
        first = tester.sample_tasks(tasks, 1, "seed")
        second = tester.sample_tasks(list(reversed(tasks)), 1, "seed")
        other_seed = tester.sample_tasks(tasks, 1, "other")
        self.assertEqual(len(first), 2)
        self.assertEqual([task.run_id for task in first], [task.run_id for task in second])
        self.assertNotEqual([task.run_id for task in first], [task.run_id for task in other_seed])

    def test_seed_affects_tied_stratum_allocation(self):
        tasks = [
            self.make_task("lp64-true", data_model="LP64", expected=True),
            self.make_task("lp64-false", data_model="LP64", expected=False),
            self.make_task("ilp32-true", data_model="ILP32", expected=True),
            self.make_task("ilp32-false", data_model="ILP32", expected=False),
        ]
        choices = {
            tester.sample_tasks(tasks, 1, str(seed))[0].stratum
            for seed in range(20)
        }
        self.assertGreater(len(choices), 1)

    def test_sample_count_is_exact_and_represents_every_property(self):
        tasks = [
            self.make_task(f"reach-{index}", "reach") for index in range(20)
        ] + [
            self.make_task(f"safety-{index}", "safety") for index in range(5)
        ] + [
            self.make_task(f"cleanup-{index}", "cleanup") for index in range(2)
        ]
        selected = tester.sample_tasks(tasks, None, "seed", count=7)
        self.assertEqual(len(selected), 7)
        self.assertEqual({task.property_name for task in selected}, {"reach", "safety", "cleanup"})

    def test_small_sample_count_selects_deterministic_property_subset(self):
        tasks = [
            self.make_task("reach", "reach"),
            self.make_task("safety", "safety"),
            self.make_task("cleanup", "cleanup"),
        ]
        first = tester.sample_tasks(tasks, None, "seed", count=2)
        second = tester.sample_tasks(list(reversed(tasks)), None, "seed", count=2)
        self.assertEqual([task.run_id for task in first], [task.run_id for task in second])
        self.assertEqual(len({task.property_name for task in first}), 2)

    def test_sample_count_larger_than_population_is_rejected(self):
        tasks = [self.make_task("only")]
        with self.assertRaisesRegex(ValueError, "exceeds population"):
            tester.sample_tasks(tasks, None, "seed", count=2)

    def test_sample_and_sample_count_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            tester.build_parser().parse_args([
                "/corpus", "/tool", "--reach", "--sample", "1%", "--sample-count", "5"
            ])

    def test_output_classification_requires_clean_exit(self):
        clean = tester.classify("REACH Correct\n", "", 0, False)
        crashed = tester.classify("REACH Correct\n", "traceback", 1, False)
        conflicting = tester.classify("REACH Correct\nREACH Incorrect\n", "", 0, False)
        self.assertEqual(clean[:2], ("true", "result"))
        self.assertEqual(crashed[:2], ("unknown", "tool_error"))
        self.assertEqual(crashed[4], "nonzero_exit")
        self.assertEqual(conflicting[4], "invalid_output")

    def test_sample_validation(self):
        self.assertEqual(tester.parse_sample("1%"), 1)
        self.assertEqual(tester.parse_sample("0.5"), 0.5)
        with self.assertRaises(Exception):
            tester.parse_sample("0%")

    def test_multi_input_task_is_reported_as_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            yaml_path = root / "task.yml"
            yaml_path.write_text("")
            task = tester.Task(
                "multi", yaml_path, "c/group/task.yml", ("one.c", "two.c"),
                "property.prp", "reach", True, "LP64", None)
            args = SimpleNamespace(svf_root=root, cpu_limit=1, wall_limit=1,
                                   memory_limit_mib=64)
            result = tester.run_task(task, args, root)
            self.assertEqual(result.classification, "unsupported")
            self.assertIsNone(result.peak_memory_mib)
            self.assertEqual(result.error_code, "MULTIPLE_INPUTS")
            self.assertIsNotNone(result.error_message)
            assert result.error_message is not None
            self.assertIn("declares 2", result.error_message)
            self.assertIn("svf_run.py", result.rerun_command)
            self.assertIn("one.c", result.rerun_command)

    def test_supported_properties_and_data_models_are_score_eligible(self):
        ilp32 = self.make_task("ilp32", data_model="ILP32")
        safety = self.make_task("safety", property_name="safety")
        cleanup = self.make_task("cleanup", property_name="cleanup")
        overflow = self.make_task("overflow", property_name="overflow")
        self.assertTrue(tester.score_eligible(ilp32))
        self.assertFalse(tester.score_eligible(safety))
        self.assertFalse(tester.score_eligible(cleanup))
        self.assertFalse(tester.score_eligible(overflow))
        unsupported = tester.unsupported_reason(overflow)
        self.assertIsNotNone(unsupported)
        assert unsupported is not None
        self.assertIn("signed-integer overflow", unsupported[1])

    def categorised(self, task, category):
        return tester.Task(
            task.run_id, task.yaml_path, task.yaml_relative, task.input_files,
            task.property_file, task.property_name, task.expected, task.data_model,
            task.subproperty, category)

    def test_category_sampling_represents_each_leaf_when_possible(self):
        tasks = [
            self.categorised(self.make_task(f"a-{index}"), "C.unreach-call.A")
            for index in range(10)
        ] + [
            self.categorised(self.make_task(f"b-{index}"), "C.unreach-call.B")
            for index in range(10)
        ]
        selected = tester.sample_tasks(tasks, None, "seed", count=2)
        self.assertEqual({task.category for task in selected},
                         {"C.unreach-call.A", "C.unreach-call.B"})

    def test_classify_extracts_reported_subproperty(self):
        plain = tester.classify("REACH Correct\n", "", 0, False)
        tagged = tester.classify("MEMORY Incorrect(valid-deref)\n", "", 0, False)
        self.assertEqual(plain[0], "true")
        self.assertEqual(plain[6], "unreach-call")
        self.assertEqual(tagged[0], "false")
        self.assertEqual(tagged[6], "valid-deref")

    @mock.patch("tests.tester.subprocess.Popen")
    def test_false_answer_runs_configured_validator(self, run):
        task = self.categorised(self.make_task("arrays"), "C.unreach-call.Arrays")
        run.return_value.returncode = 0
        run.return_value.communicate.return_value = ("witness confirmed", "")
        args = SimpleNamespace(validation_results={},
                               validator_command="validate {witness} {input}",
                               validation_wall_limit=5)
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / "witness.graphml"
            witness.write_text("<graphml/>")
            validation = tester.validate_witness(
                task, "false", args, witness, ["input.c"], "property.prp")
        self.assertEqual(validation, "correct")
        run.assert_called_once()

    @mock.patch("tests.tester.subprocess.Popen")
    def test_true_answer_without_witness_requirement_skips_validator(self, run):
        task = self.categorised(self.make_task("arrays"), "C.unreach-call.Arrays")
        args = SimpleNamespace(validation_results={},
                               validator_command="validate {witness}",
                               validation_wall_limit=5)
        validation = tester.validate_witness(
            task, "true", args, Path("missing.graphml"), ["input.c"], "property.prp")
        self.assertEqual(validation, "not-required")
        run.assert_not_called()

    def test_normalized_score_weights_leaf_categories_equally(self):
        first = self.categorised(self.make_task("first"), "A")
        second = self.categorised(self.make_task("second", expected=False), "B")
        results = [
            SimpleNamespace(category="A", score=2, answer="true",
                            expected=True, classification="result"),
            SimpleNamespace(category="B", score=1, answer="false",
                            expected=False, classification="result"),
        ]
        summary = tester.summarize(results, 2, [first, second], 0)
        self.assertEqual(summary["normalized_score"], 3)

    @mock.patch("tests.tester.subprocess.Popen")
    def test_validator_checks_optional_witnesses_and_preserves_spaces(self, run):
        run.return_value.returncode = 0
        run.return_value.communicate.return_value = ("confirmed", "")
        args = SimpleNamespace(validator_command="validate {witness} {input} {property} {bits}")
        for category in (None, "C.unreach-call.Arrays"):
            task = self.categorised(self.make_task("safe"), category)
            with self.subTest(category=category), tempfile.TemporaryDirectory() as directory:
                witness = Path(directory) / "witness with spaces.yml"
                witness.write_text("[]")
                self.assertEqual(tester.validate_witness(
                    task, "true", args, witness, ["input with spaces.c"], "property.prp"), "correct")
                self.assertEqual(run.call_args.args[0], [
                    "validate", str(witness), "input with spaces.c", "property.prp", "64"])
                run.return_value.communicate.assert_called_with(timeout=300)
                self.assertIn("confirmed", witness.with_suffix(".validation.log").read_text())

    @mock.patch("tests.tester.os.killpg")
    @mock.patch("tests.tester.subprocess.Popen")
    def test_validator_timeout_kills_process_group(self, run, killpg):
        run.return_value.pid = 123
        run.return_value.returncode = 0
        run.return_value.communicate.side_effect = [
            subprocess.TimeoutExpired("validate", 90), ("", "")]
        args = SimpleNamespace(validator_command="validate {witness}")
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / "witness.yml"
            witness.write_text("[]")
            validation = tester.validate_witness(
                self.make_task("unsafe"), "false", args, witness, ["input.c"], "property.prp")
            self.assertEqual(validation, "unconfirmed")
            self.assertIn("timeout after 90s", witness.with_suffix(".validation.log").read_text())
        killpg.assert_called_once_with(123, tester.signal.SIGKILL)
        self.assertEqual(run.return_value.communicate.call_args_list[0], mock.call(timeout=90))

    def test_summary_reports_fraction_of_generated_witnesses(self):
        task = self.make_task("safe")
        results = [SimpleNamespace(
            category=None, score=2, answer="true", expected=True, classification="result",
            witness_path=path, witness_validation=status)
            for path, status in (("one.yml", "correct"), ("two.yml", "unconfirmed"),
                                 (None, "not-required"))]
        summary = tester.summarize(results, 3, [task] * 3, 0)
        self.assertEqual(summary["witness_validation"], {
            "generated": 2, "confirmed": 1, "confirmation_fraction": 0.5,
        })


class TesterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.corpus = self.base / "corpus"
        self.group = self.corpus / "c" / "group"
        self.properties = self.corpus / "c" / "properties"
        self.tool = self.base / "tool"
        self.results = self.base / "results"
        self.group.mkdir(parents=True)
        self.properties.mkdir(parents=True)
        self.tool.mkdir()
        (self.properties / "unreach-call.prp").write_text(
            "CHECK( init(main()), LTL(G ! call(reach_error())) )\n")
        (self.tool / "svf_run.py").write_text(
            """import pathlib
import sys
import time

name = pathlib.Path(sys.argv[-1] if sys.argv[-1].endswith('.c') else sys.argv[1]).stem
if name == 'error':
    print('ERROR(AE)')
    print("AttributeError: AbstractState has no attribute 'getElementIndex'", file=sys.stderr)
    raise SystemExit(1)
if name == 'timeout':
    time.sleep(10)
answers = {
    'correct_true': 'REACH Correct',
    'correct_false': 'REACH Incorrect',
    'wrong_false': 'REACH Incorrect',
    'wrong_true': 'REACH Correct',
}
print(answers[name])
""")
        cases = [
            ("correct_true", True),
            ("correct_false", False),
            ("wrong_false", True),
            ("wrong_true", False),
            ("error", True),
        ]
        for name, expected in cases:
            (self.group / f"{name}.c").write_text("int main(void) { return 0; }\n")
            (self.group / f"{name}.yml").write_text(
                "format_version: '2.0'\n"
                f"input_files: '{name}.c'\n"
                "properties:\n"
                "  - property_file: ../properties/unreach-call.prp\n"
                f"    expected_verdict: {str(expected).lower()}\n"
                "options:\n"
                "  data_model: LP64\n")
        (self.corpus / "c" / "Alpha.set").write_text(
            "# exact and glob entries\n\n"
            "group/correct_*.yml\n"
            "group/correct_true.yml\n")
        (self.corpus / "c" / "Beta.set").write_text(
            "group/wrong_false.yml\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_end_to_end_score_and_error_artifacts(self):
        csv_path = self.base / "results.csv"
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--results-dir", str(self.results), "--output", str(csv_path)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        summary = json.loads((self.results / "summary.json").read_text())
        records = [json.loads(line) for line in (self.results / "results.jsonl").read_text().splitlines()]
        self.assertEqual(summary["score"], -45)
        self.assertEqual(summary["maximum_selected_score"], 8)
        self.assertEqual(summary["counts"], {"correct": 2, "wrong": 2, "tool_error": 1})
        self.assertEqual(len(records), 5)
        for record in records:
            self.assertGreater(record["peak_memory_mib"], 0)
            self.assertIn("peak_memory_mib:", Path(record["log_path"]).read_text())
        self.assertIn("MiB peak RSS", process.stdout)
        with csv_path.open() as stream:
            csv_records = list(csv.DictReader(stream))
        self.assertEqual([float(record["peak_memory_mib"]) for record in csv_records],
                         [record["peak_memory_mib"] for record in records])
        error = next(record for record in records if record["classification"] == "tool_error")
        self.assertEqual(error["error_code"], "ERROR(AE)")
        self.assertIn("getElementIndex", error["error_message"])
        self.assertIn("getElementIndex", Path(error["log_path"]).read_text())
        self.assertIn("rerun:", process.stderr)

    def test_dry_run_sampling_writes_replayable_manifest(self):
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--sample", "1%", "--seed", "stable", "--dry-run",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        manifest = json.loads((self.results / "manifest.json").read_text())
        self.assertEqual(manifest["population"], 5)
        self.assertEqual(len(manifest["selected"]), 1)
        self.assertFalse((self.results / "results.jsonl").exists())

    def test_nonempty_results_directory_is_rejected(self):
        self.results.mkdir()
        (self.results / "old.jsonl").write_text("stale\n")
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--dry-run", "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("results directory is not empty", process.stderr)

    def test_nested_tasks_are_discovered(self):
        nested = self.group / "nested"
        nested.mkdir()
        (nested / "nested.c").write_text("int main(void) { return 0; }\n")
        (nested / "nested.yml").write_text(
            "format_version: '2.0'\n"
            "input_files: 'nested.c'\n"
            "properties:\n"
            "  - property_file: ../../properties/unreach-call.prp\n"
            "    expected_verdict: true\n"
            "options:\n"
            "  data_model: LP64\n")
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--specific", "nested.yml", "--dry-run",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        manifest = json.loads((self.results / "manifest.json").read_text())
        self.assertEqual(manifest["population"], 1)
        self.assertEqual(manifest["selected"][0]["yaml_relative"], "c/group/nested/nested.yml")

    def test_auxiliary_yaml_without_task_schema_is_ignored(self):
        nested = self.group / "original" / "config"
        nested.mkdir(parents=True)
        (nested / "generator.yml").write_text("name: generator\ntasks: []\n")
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--dry-run", "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        manifest = json.loads((self.results / "manifest.json").read_text())
        self.assertEqual(manifest["population"], 5)
        self.assertEqual(manifest["discovery_errors"], [])

    def test_set_files_select_union_and_deduplicate_tasks(self):
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--set", "Alpha", "--set", "Beta.set", "--dry-run",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        manifest = json.loads((self.results / "manifest.json").read_text())
        self.assertEqual(manifest["population"], 3)
        self.assertEqual(manifest["set_selectors"], ["Alpha", "Beta.set"])
        self.assertEqual(manifest["set_yaml_count_before_deduplication"], 4)
        self.assertEqual(manifest["set_yaml_count"], 3)
        self.assertEqual(manifest["set_duplicate_count"], 1)
        self.assertEqual(
            [entry["path"] for entry in manifest["set_files"]],
            ["c/Alpha.set", "c/Beta.set"],
        )

    def test_set_selector_glob_resolves_multiple_sets(self):
        resolved = tester.resolve_set_files(self.corpus, ["*.set"])
        self.assertEqual([path.name for path in resolved], ["Alpha.set", "Beta.set"])

    def test_unmatched_set_entry_is_rejected_before_results_creation(self):
        (self.corpus / "c" / "Broken.set").write_text("group/missing-*.yml\n")
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--set", "Broken", "--dry-run",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("pattern matches nothing", process.stderr)
        self.assertFalse(self.results.exists())

    def test_witness_validation_set_is_explicitly_rejected(self):
        witness_set = self.corpus / "c" / "CorrectnessWitnesses.set"
        witness_set.write_text("group/correct_true.yml\n")
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--set", "CorrectnessWitnesses", "--dry-run",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("witness-validation set is not supported", process.stderr)
        self.assertFalse(self.results.exists())

    def test_set_selection_precedes_specific_filter(self):
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--set", "Alpha", "--specific", "correct_false", "--dry-run",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        manifest = json.loads((self.results / "manifest.json").read_text())
        self.assertEqual(manifest["population"], 1)
        self.assertEqual(manifest["selected"][0]["yaml_relative"], "c/group/correct_false.yml")

    def test_wall_timeout_is_classified_and_logged(self):
        (self.group / "timeout.c").write_text("int main(void) { return 0; }\n")
        (self.group / "timeout.yml").write_text(
            "format_version: '2.0'\n"
            "input_files: 'timeout.c'\n"
            "properties:\n"
            "  - property_file: ../properties/unreach-call.prp\n"
            "    expected_verdict: true\n")
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--specific", "timeout.yml", "--wall-limit", "1",
             "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        record = json.loads((self.results / "results.jsonl").read_text())
        self.assertEqual(record["classification"], "timeout")
        self.assertEqual(record["termination_reason"], "wall_timeout")
        self.assertEqual(record["score"], 0)
        self.assertGreater(record["peak_memory_mib"], 0)


if __name__ == "__main__":
    unittest.main()
