"""
Run unit tests with:
python -m unittest tests.test_tester -v
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from tests import tester


ROOT = Path(__file__).resolve().parents[1]
TESTER_PATH = ROOT / "tests" / "tester.py"


class TesterUnitTests(unittest.TestCase):
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
        self.assertTrue(tester.score_eligible(safety))
        self.assertTrue(tester.score_eligible(cleanup))
        self.assertFalse(tester.score_eligible(overflow))
        unsupported = tester.unsupported_reason(overflow)
        self.assertIsNotNone(unsupported)
        assert unsupported is not None
        self.assertIn("signed-integer overflow", unsupported[1])


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
        process = subprocess.run(
            [sys.executable, str(TESTER_PATH), str(self.corpus), str(self.tool),
             "--reach", "--results-dir", str(self.results)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        summary = json.loads((self.results / "summary.json").read_text())
        records = [json.loads(line) for line in (self.results / "results.jsonl").read_text().splitlines()]
        self.assertEqual(summary["score"], -45)
        self.assertEqual(summary["maximum_selected_score"], 8)
        self.assertEqual(summary["counts"], {"correct": 2, "wrong": 2, "tool_error": 1})
        self.assertEqual(len(records), 5)
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


if __name__ == "__main__":
    unittest.main()
