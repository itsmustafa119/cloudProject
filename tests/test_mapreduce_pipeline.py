"""Local shuffle simulation for all five Hadoop Streaming jobs."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parent.parent
MAPREDUCE = ROOT / "mapreduce"


class MapReducePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        materializer_path = ROOT / "scripts" / "materialize_mapreduce_outputs.py"
        spec = importlib.util.spec_from_file_location(
            "phase1_output_materializer", materializer_path
        )
        cls.materializer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.materializer)

    def _run(self, relative_script, input_text):
        script = MAPREDUCE / relative_script
        environment = dict(os.environ)
        environment["PYTHONUTF8"] = "1"
        result = subprocess.run(
            [sys.executable, str(script)],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=str(script.parent),
            env=environment,
            check=False,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"{relative_script} failed:\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        return result.stdout

    def _shuffle_reduce(self, job_directory, mapper_input):
        mapper_output = self._run(f"{job_directory}/mapper.py", mapper_input)
        sorted_lines = sorted(line for line in mapper_output.splitlines() if line)
        reducer_input = "\n".join(sorted_lines) + ("\n" if sorted_lines else "")
        return self._run(f"{job_directory}/reducer.py", reducer_input)

    def _raw_records(self):
        definitions = (
            ("req-01", "Iran", "normal", "team-service", "team", "Argentina", 200, 0.03),
            ("req-02", "Iran", "normal", "team-service", "team", "Argentina", 200, 0.04),
            ("req-03", "Germany", "normal", "team-service", "team", "Germany", 200, 0.05),
            ("req-04", "Germany", "normal", "team-service", "team", "Argentina", 404, 0.02),
            ("req-05", "Brazil", "normal", "match-service", "match_day", "2026-06-25", 200, 0.06),
            ("req-06", "Iran", "slow", "match-service", "match_day", "2026-06-25", 200, 0.50),
            ("req-07", "Germany", "normal", "match-service", "match_day", "2026-06-13", 200, 0.05),
            ("req-08", "Brazil", "normal", "stadium-service", "stadium", "New York New Jersey Stadium", 200, 0.08),
            ("req-09", "Iran", "slow", "stadium-service", "stadium", "New York New Jersey Stadium", 200, 0.60),
            ("req-10", "Canada", "normal", "stadium-service", "city", "Vancouver", 200, 0.04),
            ("req-11", "Canada", "server_error", "team-service", "team", "Argentina", 500, 0.01),
            ("req-12", "Mexico", "normal", "stadium-service", "stadium", "Dallas Stadium", 404, 0.02),
        )
        rules = {
            "team-service": ("/api/teams", "team_lookup", "name"),
            "match-service": ("/api/matches", "match_lookup", "date"),
            "stadium-service": ("/api/stadiums", "stadium_lookup", None),
        }
        records = []
        for (
            request_id,
            country,
            scenario,
            service,
            entity_type,
            entity_value,
            status,
            seconds,
        ) in definitions:
            endpoint, event_type, query_name = rules[service]
            if service == "stadium-service":
                query_name = "city" if entity_type == "city" else "name"
            path = f"{endpoint}?{urlencode({query_name: entity_value})}"
            records.append(
                {
                    "timestamp": "2026-07-24T10:00:00+03:30",
                    "request_id": request_id,
                    "client_ip": "172.18.0.1",
                    "client_country": country,
                    "scenario": scenario,
                    "method": "GET",
                    "path": path,
                    "service": service,
                    "status_code": status,
                    "request_time_sec": f"{seconds:.3f}",
                    "user_agent": "phase1-traffic-generator/1.0",
                }
            )
            records.append(
                {
                    "timestamp": "2026-07-24T06:30:00Z",
                    "request_id": request_id,
                    "client_country": country,
                    "scenario": scenario,
                    "service": service,
                    "endpoint": endpoint,
                    "entity_type": entity_type,
                    "entity_value": entity_value,
                    "status_code": status,
                    "processing_time_ms": max(0, int(seconds * 1000) - 5),
                    "event_type": event_type,
                }
            )
        return "\n".join(json.dumps(record) for record in records) + "\n{bad json\n"

    def test_all_five_jobs_produce_required_intermediate_and_final_results(self):
        job1 = self._shuffle_reduce("job1_parse_clean", self._raw_records())
        job1_tags = [line.split("\t", 1)[0] for line in job1.splitlines()]
        self.assertEqual(12, job1_tags.count("NGINX"))
        self.assertEqual(12, job1_tags.count("SERVICE"))
        self.assertEqual(1, job1_tags.count("INVALID"))

        job2 = self._shuffle_reduce("job2_nginx_aggregation", job1)
        job2_tags = {line.split("\t", 1)[0] for line in job2.splitlines()}
        self.assertEqual(
            {"SERVICE_STATS", "ENDPOINT_STATS", "SCENARIO_STATS"}, job2_tags
        )

        job3 = self._shuffle_reduce("job3_country_entity", job1)
        job3_tags = {line.split("\t", 1)[0] for line in job3.splitlines()}
        self.assertEqual(
            {"COUNTRY_TEAM", "COUNTRY_MATCHDAY", "COUNTRY_STADIUM"},
            job3_tags,
        )

        job4 = self._shuffle_reduce("job4_popular_entity", job3)
        job4_tags = {line.split("\t", 1)[0] for line in job4.splitlines()}
        self.assertEqual(
            {"POPULAR_TEAM", "POPULAR_MATCHDAY", "POPULAR_STADIUM"}, job4_tags
        )

        job5_input = job2 + job3 + job4
        job5 = self._shuffle_reduce("job5_final_report", job5_input)
        summary = json.loads(job5.strip())
        self.assertEqual(12, summary["total_requests"])
        self.assertEqual("team-service", summary["most_requested_service"])
        self.assertEqual("team-service", summary["highest_error_rate_service"])
        self.assertEqual("/api/matches", summary["slowest_endpoint"])
        self.assertEqual("Argentina", summary["most_popular_team_overall"])
        self.assertEqual(
            "2026-06-25", summary["most_requested_match_day_overall"]
        )
        self.assertEqual(
            "New York New Jersey Stadium",
            summary["most_requested_stadium_overall"],
        )
        self.assertEqual("Argentina", summary["popular_team_by_country"]["Iran"])
        self.assertEqual(
            "Argentina", summary["popular_team_by_country"]["Germany"]
        )
        self.assertEqual("Argentina", summary["predicted_champion"])
        self.assertEqual("France vs Argentina", summary["predicted_final"])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            raw_paths = {}
            for job_name, output in {
                "job1": job1,
                "job2": job2,
                "job3": job3,
                "job4": job4,
                "job5": job5,
            }.items():
                raw_path = temp_root / f"{job_name}.txt"
                raw_path.write_text(output, encoding="utf-8")
                raw_paths[job_name] = raw_path

            output_root = temp_root / "outputs"
            created = self.materializer.materialize_all(raw_paths, output_root)
            self.assertEqual(13, len(created))
            expected_paths = (
                "job1/cleaned_nginx_logs.csv",
                "job1/cleaned_service_logs.csv",
                "job1/invalid_logs.csv",
                "job2/service_stats.csv",
                "job2/endpoint_stats.csv",
                "job2/scenario_stats.csv",
                "job3/country_team_requests.csv",
                "job3/country_matchday_requests.csv",
                "job3/country_stadium_requests.csv",
                "job4/popular_team_by_country.csv",
                "job4/popular_matchday_by_country.csv",
                "job4/popular_stadium_by_country.csv",
                "final/summary.json",
            )
            for relative_path in expected_paths:
                with self.subTest(output=relative_path):
                    self.assertTrue((output_root / relative_path).is_file())
            materialized_summary = json.loads(
                (output_root / "final/summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary, materialized_summary)

    def test_streaming_programs_use_stdin_stdout_without_pandas(self):
        for job in (
            "job1_parse_clean",
            "job2_nginx_aggregation",
            "job3_country_entity",
            "job4_popular_entity",
            "job5_final_report",
        ):
            for program in ("mapper.py", "reducer.py"):
                with self.subTest(job=job, program=program):
                    source = (MAPREDUCE / job / program).read_text(encoding="utf-8")
                    self.assertIn("sys.stdin", source)
                    self.assertNotIn("pandas", source.lower())


if __name__ == "__main__":
    unittest.main()
