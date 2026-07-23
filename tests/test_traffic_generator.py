"""Tests for deterministic request generation and load-runner behavior."""

import argparse
import importlib.util
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parent.parent
GENERATOR_PATH = ROOT / "traffic-generator" / "generate.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("phase1_traffic_generator", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TrafficGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = _load_generator()
        cls.base_url = "http://localhost:8080"

    def test_coverage_prefix_contains_all_services_and_required_scenarios(self):
        specs = list(self.generator.generate_specs(12, self.base_url, seed=1))
        self.assertEqual(
            {"team-service", "match-service", "stadium-service"},
            {spec.service for spec in specs},
        )
        self.assertEqual(
            {"normal", "slow", "server_error"},
            {spec.scenario for spec in specs},
        )
        self.assertTrue(any("Unknown" in spec.url for spec in specs))
        self.assertTrue(any("not-a-date" in spec.url for spec in specs))
        self.assertTrue(any(spec.url.endswith("/api/stadiums") for spec in specs))

    def test_request_ids_headers_and_urls_are_gateway_safe(self):
        specs = list(self.generator.generate_specs(1000, self.base_url, seed=2026))
        self.assertEqual(1000, len({spec.request_id for spec in specs}))
        self.assertEqual("req_000001", specs[0].request_id)
        self.assertEqual("req_001000", specs[-1].request_id)
        for spec in specs:
            self.assertTrue(spec.url.startswith(f"{self.base_url}/api/"))
            self.assertEqual(spec.request_id, spec.headers["X-Request-ID"])
            self.assertEqual(spec.client_country, spec.headers["X-Client-Country"])
            self.assertEqual(spec.scenario, spec.headers["X-Scenario"])
            self.assertEqual(self.generator.USER_AGENT, spec.headers["User-Agent"])

    def test_generation_is_reproducible_for_a_seed(self):
        first = list(self.generator.generate_specs(250, self.base_url, seed=42))
        second = list(self.generator.generate_specs(250, self.base_url, seed=42))
        different = list(self.generator.generate_specs(250, self.base_url, seed=43))
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)

    def test_random_distribution_is_varied_and_deliberately_unbalanced(self):
        specs = list(self.generator.generate_specs(5000, self.base_url, seed=2026))
        services = Counter(spec.service for spec in specs)
        scenarios = Counter(spec.scenario for spec in specs)
        countries = Counter(spec.client_country for spec in specs)
        self.assertGreater(services["team-service"], services["match-service"])
        self.assertGreater(services["match-service"], services["stadium-service"])
        self.assertGreater(scenarios["normal"], scenarios["slow"])
        self.assertGreater(scenarios["slow"], scenarios["server_error"])
        self.assertGreater(len(countries), 5)

    def test_weighting_creates_expected_country_and_entity_popularity(self):
        specs = list(self.generator.generate_specs(10000, self.base_url, seed=2026))
        teams_by_country = {}
        match_days = Counter()
        stadiums = Counter()

        for spec in specs:
            query = parse_qs(urlsplit(spec.url).query)
            if spec.service == "team-service" and "name" in query:
                teams_by_country.setdefault(spec.client_country, Counter())[
                    query["name"][0]
                ] += 1
            elif spec.service == "match-service" and "date" in query:
                match_days[query["date"][0]] += 1
            elif spec.service == "stadium-service" and "name" in query:
                stadiums[query["name"][0]] += 1

        expected_teams = {
            "Iran": "Argentina",
            "Germany": "Germany",
            "Brazil": "Brazil",
        }
        for country, expected_team in expected_teams.items():
            with self.subTest(country=country):
                self.assertEqual(
                    expected_team, teams_by_country[country].most_common(1)[0][0]
                )
        self.assertEqual("2026-06-25", match_days.most_common(1)[0][0])
        self.assertEqual(
            "New York New Jersey Stadium", stadiums.most_common(1)[0][0]
        )

    def test_base_url_validation_rejects_non_gateway_shapes(self):
        self.assertEqual(
            "http://localhost:8080",
            self.generator._normalize_nginx_url("http://localhost:8080/"),
        )
        invalid_values = (
            "localhost:8080",
            "ftp://localhost:8080",
            "http://localhost:8080/api/teams",
            "http://user:pass@localhost:8080",
            "http://localhost:8080?debug=1",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    self.generator._normalize_nginx_url(value)

    def test_bounded_runner_aggregates_http_results_without_trace_files(self):
        specs = list(self.generator.generate_specs(20, self.base_url, seed=5))

        def fake_send(spec, _timeout):
            status = 500 if spec.scenario == "server_error" else 200
            return self.generator.RequestResult(spec, status, 10.0)

        with patch.object(self.generator, "send_request", side_effect=fake_send):
            stats = self.generator.run_traffic(
                specs,
                request_count=20,
                workers=4,
                timeout=1.0,
                progress_every=0,
            )

        self.assertEqual(20, stats.completed)
        self.assertEqual(0, stats.transport_errors)
        self.assertEqual(20, sum(stats.status_counts.values()))
        self.assertEqual(20, sum(stats.service_counts.values()))
        self.assertEqual(10.0, stats.average_latency_ms)


if __name__ == "__main__":
    unittest.main()
