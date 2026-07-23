"""Tests for source-log validation and safe clean-run preparation."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_module(name, relative_path):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LogValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = _load_module("phase1_log_validator", "scripts/validate_logs.py")
        cls.cleaner = _load_module("phase1_log_cleaner", "scripts/prepare_clean_run.py")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.nginx_path = self.root / "data/nginx/nginx_access.log"
        self.service_paths = {
            service: self.root / f"data/service_logs/{service.replace('-', '_')}.log"
            for service in ("match-service", "team-service", "stadium-service")
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_jsonl(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )

    def _gateway_record(self, request_id, service, status, scenario, country, seconds):
        endpoint = self.validator.SERVICE_RULES[service]["endpoint"]
        return {
            "timestamp": "2026-07-23T10:00:00+03:30",
            "request_id": request_id,
            "client_ip": "172.18.0.1",
            "client_country": country,
            "scenario": scenario,
            "method": "GET",
            "path": endpoint + "?sample=value",
            "service": service,
            "status_code": status,
            "request_time_sec": f"{seconds:.3f}",
            "user_agent": "phase1-traffic-generator/1.0",
        }

    def _service_record(
        self, request_id, service, status, scenario, country, entity_type, value
    ):
        rules = self.validator.SERVICE_RULES[service]
        return {
            "timestamp": "2026-07-23T06:30:00Z",
            "request_id": request_id,
            "client_country": country,
            "scenario": scenario,
            "service": service,
            "endpoint": rules["endpoint"],
            "entity_type": entity_type,
            "entity_value": value,
            "status_code": status,
            "processing_time_ms": 25,
            "event_type": rules["event_type"],
        }

    def _valid_dataset(self):
        definitions = (
            ("req-1", "team-service", 200, "normal", "Iran", "team", "Argentina", 0.02),
            (
                "req-2",
                "match-service",
                200,
                "normal",
                "Germany",
                "match_day",
                "2026-06-25",
                0.03,
            ),
            (
                "req-3",
                "stadium-service",
                200,
                "normal",
                "Brazil",
                "stadium",
                "New York New Jersey Stadium",
                0.04,
            ),
            ("req-4", "stadium-service", 200, "normal", "Canada", "city", "Vancouver", 0.03),
            ("req-5", "team-service", 404, "normal", "Iran", "team", "Unknown FC", 0.02),
            ("req-6", "match-service", 400, "normal", "Mexico", "match_day", "not-a-date", 0.02),
            ("req-7", "team-service", 500, "server_error", "Japan", "team", "Japan", 0.01),
            ("req-8", "match-service", 200, "slow", "France", "match_day", "2026-06-25", 0.50),
        )
        gateway = []
        services = {service: [] for service in self.service_paths}
        for (
            request_id,
            service,
            status,
            scenario,
            country,
            entity_type,
            value,
            seconds,
        ) in definitions:
            gateway.append(
                self._gateway_record(
                    request_id, service, status, scenario, country, seconds
                )
            )
            services[service].append(
                self._service_record(
                    request_id,
                    service,
                    status,
                    scenario,
                    country,
                    entity_type,
                    value,
                )
            )
        return gateway, services

    def _write_valid_dataset(self):
        gateway, services = self._valid_dataset()
        self._write_jsonl(self.nginx_path, gateway)
        for service, records in services.items():
            self._write_jsonl(self.service_paths[service], records)

    def _validate(self, expected=8, diversity=True):
        return self.validator.validate_logs(
            self.nginx_path,
            self.service_paths.values(),
            expected_min_requests=expected,
            require_diversity=diversity,
        )

    def test_valid_diverse_correlated_dataset_passes(self):
        self._write_valid_dataset()
        report = self._validate()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(8, report.correlated_requests)
        self.assertEqual(8, len(report.nginx_records))
        self.assertEqual(8, len(report.service_records))

    def test_malformed_and_missing_fields_are_reported_with_locations(self):
        self._write_valid_dataset()
        with self.nginx_path.open("a", encoding="utf-8") as log_file:
            log_file.write("{broken json\n")
            log_file.write(json.dumps({"timestamp": "2026-01-01T00:00:00Z"}) + "\n")
        report = self._validate(diversity=False)
        self.assertFalse(report.ok)
        self.assertTrue(any("invalid JSON" in error for error in report.errors))
        self.assertTrue(any("missing required fields" in error for error in report.errors))

    def test_status_and_header_correlation_mismatches_fail(self):
        gateway, services = self._valid_dataset()
        services["team-service"][0]["status_code"] = 404
        services["team-service"][0]["client_country"] = "Canada"
        self._write_jsonl(self.nginx_path, gateway)
        for service, records in services.items():
            self._write_jsonl(self.service_paths[service], records)
        report = self._validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("correlation mismatch" in error for error in report.errors))

    def test_wrong_field_types_are_reported_without_crashing(self):
        gateway, services = self._valid_dataset()
        gateway[0]["request_time_sec"] = 0.02
        services["stadium-service"][0]["entity_type"] = ["stadium"]
        self._write_jsonl(self.nginx_path, gateway)
        for service, records in services.items():
            self._write_jsonl(self.service_paths[service], records)

        report = self._validate(diversity=False)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("numeric nonnegative string" in error for error in report.errors)
        )
        self.assertTrue(
            any("entity_type must be a string" in error for error in report.errors)
        )

    def test_duplicate_and_unmatched_request_ids_fail(self):
        gateway, services = self._valid_dataset()
        gateway.append(dict(gateway[0]))
        services["team-service"][0]["request_id"] = "service-only"
        self._write_jsonl(self.nginx_path, gateway)
        for service, records in services.items():
            self._write_jsonl(self.service_paths[service], records)
        report = self._validate(expected=8, diversity=False)
        self.assertFalse(report.ok)
        self.assertTrue(any("duplicate gateway request_id" in error for error in report.errors))
        self.assertTrue(any("has no gateway record" in error for error in report.errors))

    def test_clean_run_utility_requires_confirmation_and_truncates_in_place(self):
        for relative_path in self.cleaner.LOG_PATHS:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("existing log\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.cleaner.truncate_logs(self.root, stack_stopped=False)

        truncated = self.cleaner.truncate_logs(self.root, stack_stopped=True)
        self.assertEqual(len(self.cleaner.LOG_PATHS), len(truncated))
        for path in truncated:
            self.assertTrue(path.exists())
            self.assertEqual("", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
