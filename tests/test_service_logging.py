"""Unit tests for Phase 1 backend structured logging."""

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_KEYS = {
    "timestamp",
    "request_id",
    "client_country",
    "scenario",
    "service",
    "endpoint",
    "entity_type",
    "entity_value",
    "status_code",
    "processing_time_ms",
    "event_type",
}


def _install_fastapi_stubs_if_needed():
    """Allow logging tests to run before Step 3 adds Python dependencies."""
    try:
        import fastapi  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    fastapi_module = types.ModuleType("fastapi")
    responses_module = types.ModuleType("fastapi.responses")

    class FastAPI:
        def __init__(self, **_kwargs):
            pass

        def get(self, _path):
            def decorator(function):
                return function

            return decorator

    class Request:
        pass

    class JSONResponse:
        def __init__(self, status_code, content):
            self.status_code = status_code
            self.content = content

    fastapi_module.FastAPI = FastAPI
    fastapi_module.Request = Request
    responses_module.JSONResponse = JSONResponse
    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.responses"] = responses_module


def _load_service(module_name, relative_path):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRequest:
    def __init__(self, request_id="req-test", country="Iran", scenario="normal"):
        self.headers = {
            "x-request-id": request_id,
            "x-client-country": country,
            "x-scenario": scenario,
        }


class ServiceLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_fastapi_stubs_if_needed()
        cls.team = _load_service("phase1_team_service", "team-service/main.py")
        cls.match = _load_service("phase1_match_service", "match-service/main.py")
        cls.stadium = _load_service(
            "phase1_stadium_service", "stadium-service/main.py"
        )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_log_dir = os.environ.get("SERVICE_LOG_DIR")
        os.environ["SERVICE_LOG_DIR"] = self.temp_dir.name

    def tearDown(self):
        if self.previous_log_dir is None:
            os.environ.pop("SERVICE_LOG_DIR", None)
        else:
            os.environ["SERVICE_LOG_DIR"] = self.previous_log_dir
        self.temp_dir.cleanup()

    def _records(self, module):
        path = module._service_log_path()
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]

    def _assert_common_schema(self, record):
        self.assertEqual(EXPECTED_KEYS, set(record))
        self.assertTrue(record["timestamp"].endswith("Z"))
        parsed_timestamp = datetime.fromisoformat(
            record["timestamp"].replace("Z", "+00:00")
        )
        self.assertIsNotNone(parsed_timestamp.tzinfo)
        self.assertIsInstance(record["status_code"], int)
        self.assertIsInstance(record["processing_time_ms"], int)
        self.assertGreaterEqual(record["processing_time_ms"], 0)

    def test_team_success_and_unicode_not_found_are_each_logged_once(self):
        with patch.object(self.team, "_apply_scenario", return_value=None):
            result = self.team.get_team(
                FakeRequest("team-1", "Germany", " SLOW "), name="argentina"
            )
            self.assertEqual("Argentina", result["name"])

            self.team.get_team(
                FakeRequest("team-2", "Iran", "normal"), name="تیم ناشناخته"
            )

        records = self._records(self.team)
        self.assertEqual(2, len(records))
        self.assertEqual("Argentina", records[0]["entity_value"])
        self.assertEqual("slow", records[0]["scenario"])
        self.assertEqual(200, records[0]["status_code"])
        self.assertEqual("تیم ناشناخته", records[1]["entity_value"])
        self.assertEqual(404, records[1]["status_code"])
        self.assertIn(
            "تیم ناشناخته",
            self.team._service_log_path().read_text(encoding="utf-8"),
        )
        for record in records:
            self._assert_common_schema(record)
            self.assertEqual("team-service", record["service"])
            self.assertEqual("/api/teams", record["endpoint"])
            self.assertEqual("team", record["entity_type"])
            self.assertEqual("team_lookup", record["event_type"])

    def test_match_success_validation_not_found_and_forced_error_are_logged(self):
        request = FakeRequest("match-1", "Canada", "normal")
        with patch.object(self.match, "_apply_scenario", return_value=None):
            self.match.get_matches(request, date="2026-06-25")
            self.match.get_matches(request, date="not-a-date")
            self.match.get_matches(request, date="2026-01-01")
            self.match.get_matches(request, date="")

        with patch.object(self.match.random, "uniform", return_value=0):
            response = self.match.get_matches(
                FakeRequest("match-5", "Brazil", "server_error"),
                date="2026-06-25",
            )
        self.assertEqual(500, response.status_code)

        records = self._records(self.match)
        self.assertEqual(
            [200, 400, 404, 400, 500],
            [record["status_code"] for record in records],
        )
        self.assertEqual("server_error", records[-1]["scenario"])
        for record in records:
            self._assert_common_schema(record)
            self.assertEqual("match-service", record["service"])
            self.assertEqual("/api/matches", record["endpoint"])
            self.assertEqual("match_day", record["entity_type"])
            self.assertEqual("match_lookup", record["event_type"])

    def test_slow_scenario_is_normalized_and_included_in_measured_time(self):
        with patch.object(self.team.random, "uniform", return_value=0.01):
            self.team.get_team(
                FakeRequest("slow-1", "Iran", " SLOW "), name="Argentina"
            )

        records = self._records(self.team)
        self.assertEqual(1, len(records))
        self.assertEqual("slow", records[0]["scenario"])
        self.assertGreaterEqual(records[0]["processing_time_ms"], 5)
        self._assert_common_schema(records[0])

    def test_stadium_name_city_and_missing_queries_use_correct_entity_types(self):
        request = FakeRequest("stadium-1", "Mexico", "normal")
        with patch.object(self.stadium, "_apply_scenario", return_value=None):
            self.stadium.get_stadium(request, name="MetLife Stadium")
            self.stadium.get_stadium(request, city="New York")
            self.stadium.get_stadium(request)

        records = self._records(self.stadium)
        self.assertEqual(3, len(records))
        self.assertEqual(
            [("stadium", 200), ("city", 200), ("stadium", 400)],
            [
                (record["entity_type"], record["status_code"])
                for record in records
            ],
        )
        for record in records:
            self._assert_common_schema(record)
            self.assertEqual("stadium-service", record["service"])
            self.assertEqual("/api/stadiums", record["endpoint"])
            self.assertEqual("stadium_lookup", record["event_type"])

    def test_concurrent_appends_remain_complete_json_lines(self):
        def write_record(index):
            self.team.write_service_log(
                f"parallel-{index}",
                "Iran",
                "normal",
                "Argentina",
                200,
                index,
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write_record, range(40)))

        records = self._records(self.team)
        self.assertEqual(40, len(records))
        self.assertEqual(
            {f"parallel-{index}" for index in range(40)},
            {record["request_id"] for record in records},
        )
        for record in records:
            self._assert_common_schema(record)


if __name__ == "__main__":
    unittest.main()
