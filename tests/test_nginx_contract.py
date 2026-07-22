"""Static contract tests for the Phase 1 Nginx gateway configuration."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "nginx" / "nginx.conf"


class NginxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = CONFIG_PATH.read_text(encoding="utf-8")

    def test_configuration_is_complete_and_uses_the_expected_log_path(self):
        self.assertRegex(self.config, r"(?m)^events\s*\{")
        self.assertRegex(self.config, r"(?m)^http\s*\{")
        self.assertIn("log_format phase1_json escape=json", self.config)
        self.assertIn(
            "access_log /var/log/nginx/nginx_access.log phase1_json;",
            self.config,
        )
        self.assertIn("listen 80;", self.config)

    def test_all_required_gateway_log_fields_are_present(self):
        required_fields = (
            "timestamp",
            "request_id",
            "client_ip",
            "client_country",
            "scenario",
            "method",
            "path",
            "service",
            "status_code",
            "request_time_sec",
            "user_agent",
        )
        for field in required_fields:
            with self.subTest(field=field):
                self.assertIn(f'"{field}"', self.config)

    def test_upstreams_use_compose_dns_names_and_private_port(self):
        expected_servers = (
            "server match-service:8000;",
            "server team-service:8000;",
            "server stadium-service:8000;",
        )
        for server in expected_servers:
            with self.subTest(server=server):
                self.assertIn(server, self.config)
        self.assertNotIn("localhost:8000", self.config)
        self.assertNotIn("127.0.0.1:8000", self.config)

    def test_exact_api_routes_proxy_to_the_matching_upstreams(self):
        expected_routes = {
            "/api/matches": ("match-service", "match_service_upstream"),
            "/api/teams": ("team-service", "team_service_upstream"),
            "/api/stadiums": ("stadium-service", "stadium_service_upstream"),
        }
        for route, (service, upstream) in expected_routes.items():
            with self.subTest(route=route):
                block_pattern = re.compile(
                    rf"location = {re.escape(route)}\s*\{{(?P<body>.*?)\n\s*\}}",
                    re.DOTALL,
                )
                match = block_pattern.search(self.config)
                self.assertIsNotNone(match)
                body = match.group("body")
                self.assertIn(f'set $target_service "{service}";', body)
                self.assertIn(f"proxy_pass http://{upstream};", body)

    def test_effective_headers_are_defaulted_logged_and_forwarded(self):
        self.assertIn("$request_id", self.config)
        self.assertIn('"Unknown"', self.config)
        self.assertIn('"normal"', self.config)
        self.assertIn('"$effective_request_id"', self.config)
        self.assertIn('"$effective_client_country"', self.config)
        self.assertIn('"$effective_scenario"', self.config)

        self.assertEqual(
            3,
            self.config.count(
                "proxy_set_header X-Request-ID $effective_request_id;"
            ),
        )
        self.assertEqual(
            3,
            self.config.count(
                "proxy_set_header X-Client-Country $effective_client_country;"
            ),
        )
        self.assertEqual(
            3,
            self.config.count("proxy_set_header X-Scenario $effective_scenario;"),
        )

    def test_gateway_health_and_json_not_found_responses_exist(self):
        self.assertIn("location = /health", self.config)
        self.assertIn("return 200", self.config)
        self.assertIn("location /", self.config)
        self.assertIn("return 404", self.config)
        self.assertIn("route_not_found", self.config)

    def test_configuration_has_no_personal_machine_paths(self):
        self.assertNotIn("C:\\", self.config)
        self.assertNotIn("/Users/", self.config)


if __name__ == "__main__":
    unittest.main()
