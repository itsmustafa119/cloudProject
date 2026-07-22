"""Static contract tests for the three backend service containers."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERVICES = ("match-service", "team-service", "stadium-service")
EXPECTED_REQUIREMENTS = {
    "fastapi==0.115.12",
    "uvicorn==0.34.2",
}


class ContainerContractTests(unittest.TestCase):
    def test_each_service_has_the_expected_container_files(self):
        for service in SERVICES:
            with self.subTest(service=service):
                service_dir = ROOT / service
                self.assertTrue((service_dir / "Dockerfile").is_file())
                self.assertTrue((service_dir / "requirements.txt").is_file())
                self.assertTrue((service_dir / ".dockerignore").is_file())

    def test_dependencies_are_pinned_and_consistent(self):
        for service in SERVICES:
            with self.subTest(service=service):
                requirements = {
                    line.strip()
                    for line in (ROOT / service / "requirements.txt")
                    .read_text(encoding="utf-8")
                    .splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                }
                self.assertEqual(EXPECTED_REQUIREMENTS, requirements)
                self.assertTrue(all("==" in item for item in requirements))

    def test_dockerfiles_follow_the_service_runtime_contract(self):
        required_fragments = (
            "FROM python:3.12-slim",
            "WORKDIR /app",
            "SERVICE_PORT=8000",
            "SERVICE_LOG_DIR=/data/service_logs",
            "pip install --no-cache-dir",
            "COPY main.py ./",
            "USER appuser",
            "EXPOSE 8000",
            "HEALTHCHECK",
            "http://127.0.0.1:8000/health",
            'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]',
        )

        for service in SERVICES:
            with self.subTest(service=service):
                dockerfile = (ROOT / service / "Dockerfile").read_text(
                    encoding="utf-8"
                )
                for fragment in required_fragments:
                    self.assertIn(fragment, dockerfile)
                self.assertNotIn("C:\\", dockerfile)
                self.assertNotIn("/Users/", dockerfile)

    def test_dockerignore_excludes_local_python_and_log_artifacts(self):
        required_patterns = {"__pycache__/", "*.py[cod]", "*.log"}
        for service in SERVICES:
            with self.subTest(service=service):
                patterns = set(
                    (ROOT / service / ".dockerignore")
                    .read_text(encoding="utf-8")
                    .splitlines()
                )
                self.assertTrue(required_patterns.issubset(patterns))


if __name__ == "__main__":
    unittest.main()
