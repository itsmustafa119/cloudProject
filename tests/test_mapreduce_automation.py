"""Contract tests for Hadoop orchestration and output materialization."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "run_mapreduce.sh"
MATERIALIZER_PATH = ROOT / "scripts" / "materialize_mapreduce_outputs.py"


def _load_materializer():
    spec = importlib.util.spec_from_file_location(
        "phase1_materializer_contract", MATERIALIZER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MapReduceAutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")
        cls.materializer = _load_materializer()

    def test_pipeline_fails_fast_and_uses_an_isolated_hdfs_namespace(self):
        self.assertTrue(self.script.startswith("#!/usr/bin/env bash\nset -euo pipefail"))
        self.assertIn('HDFS_ROOT="${HDFS_ROOT:-/phase1}"', self.script)
        self.assertNotIn("hdfs dfs -rm -r -f / ", self.script)
        self.assertIn('hdfs dfs -rm -r -f "$HDFS_INPUT"', self.script)

    def test_pipeline_uploads_all_four_source_logs(self):
        required_logs = (
            "data/nginx/nginx_access.log",
            "data/service_logs/match_service.log",
            "data/service_logs/team_service.log",
            "data/service_logs/stadium_service.log",
        )
        for log_path in required_logs:
            with self.subTest(log_path=log_path):
                self.assertIn(log_path, self.script)
        self.assertGreaterEqual(self.script.count("hdfs dfs -put -f"), 4)

    def test_pipeline_runs_all_five_jobs_with_one_reducer(self):
        job_names = (
            "phase1-job1-parse-clean",
            "phase1-job2-nginx-aggregation",
            "phase1-job3-country-entity",
            "phase1-job4-popular-entity",
            "phase1-job5-final-report",
        )
        for job_name in job_names:
            with self.subTest(job_name=job_name):
                self.assertIn(job_name, self.script)
        self.assertEqual(4, self.script.count("run_streaming \\\n"))
        self.assertIn("mapreduce.job.reduces=1", self.script)
        self.assertIn(
            "mapreduce.input.fileinputformat.input.dir.recursive=true", self.script
        )

    def test_job5_consumes_jobs_two_three_and_four(self):
        for job_number in (2, 3, 4):
            with self.subTest(job_number=job_number):
                self.assertIn(
                    f'-input "${{HDFS_OUTPUT}}/job{job_number}"', self.script
                )
        self.assertIn("predictions.json", self.script)

    def test_pipeline_retrieves_every_job_and_invokes_materializer(self):
        self.assertIn("hdfs dfs -getmerge", self.script)
        self.assertIn("for job_number in 1 2 3 4 5", self.script)
        self.assertIn("materialize_mapreduce_outputs.py", self.script)
        self.assertIn("--output-root \"$LOCAL_OUTPUT\"", self.script)

    def test_materializer_rejects_missing_required_tags_and_bad_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw = root / "job2.txt"
            raw.write_text(
                "SERVICE_STATS\tteam-service,1,1,0,0,0,0.000000,1.000\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                self.materializer.materialize_tagged_job("job2", raw, root / "out")

            bad_summary = root / "job5.txt"
            bad_summary.write_text(json.dumps({"total_requests": 1}) + "\n")
            with self.assertRaises(ValueError):
                self.materializer.materialize_summary(bad_summary, root / "out")


if __name__ == "__main__":
    unittest.main()
