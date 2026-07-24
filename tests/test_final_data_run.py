"""Tests for guarded final-run automation and artifact consistency checks."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
RUN_SCRIPT = SCRIPTS / "run_final_data.sh"


def load_script(module_name, path):
    scripts_path = str(SCRIPTS)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FinalDataRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = RUN_SCRIPT.read_text(encoding="utf-8")
        cls.e2e = load_script("phase1_e2e_for_final", SCRIPTS / "verify_local_e2e.py")
        cls.verifier = load_script(
            "phase1_final_artifact_verifier",
            SCRIPTS / "verify_final_artifacts.py",
        )

    def test_final_run_requires_confirmation_and_at_least_100000_requests(self):
        self.assertIn('--confirm-final-run', self.shell)
        self.assertIn('REQUEST_COUNT="${REQUEST_COUNT:-100000}"', self.shell)
        self.assertIn('REQUEST_COUNT < 100000', self.shell)
        self.assertIn("set -euo pipefail", self.shell)

    def test_final_run_uses_only_documented_gateway_and_pipeline_commands(self):
        required_commands = (
            "docker compose down",
            "python scripts/prepare_clean_run.py --confirm-stack-stopped",
            "docker compose up --build -d --wait",
            "docker compose exec -T nginx nginx -t",
            "python traffic-generator/generate.py",
            'python scripts/validate_logs.py --expected-min-requests "$REQUEST_COUNT"',
            "docker compose -f hadoop/docker-compose.yml up -d",
            "bash /project/scripts/run_mapreduce.sh",
            "python scripts/verify_final_artifacts.py",
        )
        for command in required_commands:
            with self.subTest(command=command):
                self.assertIn(command, self.shell)

    def test_final_run_preserves_logs_and_outputs(self):
        self.assertNotIn("rm -rf", self.shell)
        self.assertNotIn("docker compose down -v", self.shell)
        self.assertIn("preserved in data/ and outputs/", self.shell)

    def test_artifact_verifier_accepts_consistent_materialized_fixture(self):
        fixture_root = ROOT / "tests" / "fixtures" / "e2e"
        raw_input = (fixture_root / "raw_logs.jsonl").read_text(encoding="utf-8")
        results = self.e2e.execute_pipeline(raw_input)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            self.e2e.materialize(results, output_root)
            report = self.verifier.verify_artifacts(
                output_root,
                ROOT / "mapreduce" / "job5_final_report" / "predictions.json",
                expected_min_requests=6,
            )
        self.assertEqual(6, report["total_requests"])
        self.assertEqual(1, report["invalid_rows"])

    def test_artifact_verifier_rejects_inconsistent_summary(self):
        fixture_root = ROOT / "tests" / "fixtures" / "e2e"
        raw_input = (fixture_root / "raw_logs.jsonl").read_text(encoding="utf-8")
        results = self.e2e.execute_pipeline(raw_input)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs"
            self.e2e.materialize(results, output_root)
            summary_path = output_root / "final" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["total_requests"] = 999
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "final summary differs"):
                self.verifier.verify_artifacts(
                    output_root,
                    ROOT / "mapreduce" / "job5_final_report" / "predictions.json",
                    expected_min_requests=6,
                )


if __name__ == "__main__":
    unittest.main()
