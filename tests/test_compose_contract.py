"""Static contract tests for the root application Docker Compose stack."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PATH = ROOT / "docker-compose.yml"
BACKENDS = ("match-service", "team-service", "stadium-service")


class ComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = COMPOSE_PATH.read_text(encoding="utf-8")

    def _service_block(self, service):
        pattern = re.compile(
            rf"(?m)^  {re.escape(service)}:\n(?P<body>(?:^    .*\n|^\s*$)*)"
        )
        match = pattern.search(self.compose)
        self.assertIsNotNone(match, f"missing Compose service: {service}")
        return match.group("body")

    def test_stack_defines_all_required_services(self):
        for service in (*BACKENDS, "nginx"):
            with self.subTest(service=service):
                self._service_block(service)

    def test_backends_build_from_their_own_contexts(self):
        for service in BACKENDS:
            with self.subTest(service=service):
                block = self._service_block(service)
                self.assertIn(f"context: ./{service}", block)
                self.assertIn("dockerfile: Dockerfile", block)
                self.assertIn('SERVICE_PORT: "8000"', block)
                self.assertIn("SERVICE_LOG_DIR: /data/service_logs", block)
                self.assertIn(
                    "./data/service_logs:/data/service_logs", block
                )
                self.assertIn('expose:\n      - "8000"', block)
                self.assertNotIn("ports:", block)

    def test_nginx_is_the_only_host_facing_service(self):
        nginx = self._service_block("nginx")
        self.assertIn('ports:\n      - "8080:80"', nginx)
        self.assertEqual(1, self.compose.count("ports:"))

    def test_nginx_mounts_the_full_config_and_persistent_log_directory(self):
        nginx = self._service_block("nginx")
        self.assertIn(
            "./nginx/nginx.conf:/etc/nginx/nginx.conf:ro", nginx
        )
        self.assertIn("./data/nginx:/var/log/nginx", nginx)

    def test_nginx_waits_for_all_backend_health_checks(self):
        nginx = self._service_block("nginx")
        for service in BACKENDS:
            with self.subTest(service=service):
                self.assertRegex(
                    nginx,
                    rf"{re.escape(service)}:\n        condition: service_healthy",
                )
        self.assertEqual(3, nginx.count("condition: service_healthy"))

    def test_all_services_share_one_private_bridge_network(self):
        self.assertEqual(4, self.compose.count("- app-network"))
        self.assertIn("networks:\n  app-network:\n    driver: bridge", self.compose)

    def test_gateway_has_a_health_check(self):
        nginx = self._service_block("nginx")
        self.assertIn("healthcheck:", nginx)
        self.assertIn("http://127.0.0.1/health", nginx)

    def test_compose_file_has_no_personal_machine_paths(self):
        self.assertNotIn("C:\\", self.compose)
        self.assertNotIn("/Users/", self.compose)


if __name__ == "__main__":
    unittest.main()
