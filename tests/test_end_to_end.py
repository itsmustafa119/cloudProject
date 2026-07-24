"""Deterministic end-to-end and edge-case verification for Phase 1."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify_local_e2e.py"
FIXTURES = ROOT / "tests" / "fixtures" / "e2e"
MAPREDUCE = ROOT / "mapreduce"


def load_verifier():
    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location("phase1_e2e_verifier", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verifier = load_verifier()

    def test_fixture_matches_hand_calculated_results(self):
        raw_input = (FIXTURES / "raw_logs.jsonl").read_text(encoding="utf-8")
        expected = json.loads(
            (FIXTURES / "expected_results.json").read_text(encoding="utf-8")
        )
        results = self.verifier.execute_pipeline(raw_input)
        self.verifier.validate_expected(results, expected)

    def test_documented_verifier_command_succeeds(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("END-TO-END VERIFICATION PASSED", result.stdout)

    def test_materialization_is_identical_on_rerun(self):
        raw_input = (FIXTURES / "raw_logs.jsonl").read_text(encoding="utf-8")
        results = self.verifier.execute_pipeline(raw_input)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            first_paths = self.verifier.materialize(results, output_root)
            first = {
                path.relative_to(output_root): path.read_bytes()
                for path in first_paths
            }
            second_paths = self.verifier.materialize(results, output_root)
            second = {
                path.relative_to(output_root): path.read_bytes()
                for path in second_paths
            }
        self.assertEqual(first, second)
        self.assertEqual(13, len(second))

    def test_streaming_stages_accept_empty_input(self):
        for job in (
            "job1_parse_clean",
            "job2_nginx_aggregation",
            "job3_country_entity",
            "job4_popular_entity",
            "job5_final_report",
        ):
            for program in ("mapper.py", "reducer.py"):
                with self.subTest(job=job, program=program):
                    output = self.verifier.run_program(f"{job}/{program}", "")
                    if job == "job5_final_report" and program == "reducer.py":
                        summary = json.loads(output)
                        self.assertEqual(0, summary["total_requests"])
                        self.assertIsNone(summary["most_requested_service"])
                        self.assertEqual({}, summary["popular_team_by_country"])
                    else:
                        self.assertEqual("", output)

    def test_downstream_mappers_skip_malformed_rows(self):
        malformed_inputs = {
            "job2_nginx_aggregation/mapper.py": "NGINX\ttoo,few,columns\n",
            "job3_country_entity/mapper.py": "SERVICE\ttoo,few,columns\n",
            "job4_popular_entity/mapper.py": "COUNTRY_TEAM\tIran,Argentina,nope\n",
            "job5_final_report/mapper.py": "UNKNOWN\tignored\n",
        }
        for program, malformed_input in malformed_inputs.items():
            with self.subTest(program=program):
                output = self.verifier.run_program(program, malformed_input)
                self.assertEqual("", output)


if __name__ == "__main__":
    unittest.main()
