#!/usr/bin/env python3
"""Validate and correlate Phase 1 Nginx and backend JSON Lines logs."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NGINX_LOG = PROJECT_ROOT / "data" / "nginx" / "nginx_access.log"
DEFAULT_SERVICE_LOGS = (
    PROJECT_ROOT / "data" / "service_logs" / "match_service.log",
    PROJECT_ROOT / "data" / "service_logs" / "team_service.log",
    PROJECT_ROOT / "data" / "service_logs" / "stadium_service.log",
)

NGINX_REQUIRED_FIELDS = {
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
}

SERVICE_REQUIRED_FIELDS = {
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

SERVICE_RULES = {
    "match-service": {
        "endpoint": "/api/matches",
        "entity_types": {"match_day"},
        "event_type": "match_lookup",
    },
    "team-service": {
        "endpoint": "/api/teams",
        "entity_types": {"team"},
        "event_type": "team_lookup",
    },
    "stadium-service": {
        "endpoint": "/api/stadiums",
        "entity_types": {"stadium", "city"},
        "event_type": "stadium_lookup",
    },
}


@dataclass(frozen=True)
class LocatedRecord:
    source: str
    line_number: int
    data: dict


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    nginx_records: list[LocatedRecord] = field(default_factory=list)
    service_records: list[LocatedRecord] = field(default_factory=list)
    correlated_requests: int = 0
    status_counts: Counter = field(default_factory=Counter)
    service_counts: Counter = field(default_factory=Counter)
    scenario_counts: Counter = field(default_factory=Counter)
    country_counts: Counter = field(default_factory=Counter)
    entity_type_counts: Counter = field(default_factory=Counter)
    scenario_times: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @property
    def ok(self):
        return not self.errors


def _error_at(source: str, line_number: int, message: str):
    return f"{source}:{line_number}: {message}"


def _valid_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_integer(value):
    return type(value) is int


def _as_nonnegative_float(value):
    if isinstance(value, bool):
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if converted >= 0 else None


def _read_jsonl(path: Path, report: ValidationReport) -> list[LocatedRecord]:
    if not path.is_file():
        report.errors.append(f"{path}: required log file does not exist")
        return []

    records = []
    with path.open("r", encoding="utf-8") as log_file:
        for line_number, raw_line in enumerate(log_file, start=1):
            line = raw_line.rstrip("\r\n")
            if not line:
                report.errors.append(
                    _error_at(str(path), line_number, "blank JSONL record")
                )
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                report.errors.append(
                    _error_at(
                        str(path),
                        line_number,
                        f"invalid JSON ({exc.msg} at column {exc.colno})",
                    )
                )
                continue
            if not isinstance(value, dict):
                report.errors.append(
                    _error_at(str(path), line_number, "record must be a JSON object")
                )
                continue
            records.append(LocatedRecord(str(path), line_number, value))
    return records


def _validate_common_fields(
    record: LocatedRecord, required_fields: set[str], report: ValidationReport
):
    data = record.data
    missing = sorted(required_fields - set(data))
    if missing:
        report.errors.append(
            _error_at(
                record.source,
                record.line_number,
                "missing required fields: " + ", ".join(missing),
            )
        )
        return False

    valid = True
    if not _valid_timestamp(data["timestamp"]):
        report.errors.append(
            _error_at(record.source, record.line_number, "invalid timestamp")
        )
        valid = False
    for field_name in ("request_id", "client_country", "scenario", "service"):
        if not isinstance(data[field_name], str) or not data[field_name].strip():
            report.errors.append(
                _error_at(
                    record.source,
                    record.line_number,
                    f"{field_name} must be a nonempty string",
                )
            )
            valid = False
    if not _is_integer(data["status_code"]) or not 100 <= data["status_code"] <= 599:
        report.errors.append(
            _error_at(
                record.source,
                record.line_number,
                "status_code must be an integer between 100 and 599",
            )
        )
        valid = False
    return valid


def _validate_nginx_record(record: LocatedRecord, report: ValidationReport):
    data = record.data
    valid = _validate_common_fields(record, NGINX_REQUIRED_FIELDS, report)
    if not valid:
        return False

    for field_name in ("client_ip", "method", "path", "user_agent"):
        if not isinstance(data[field_name], str):
            report.errors.append(
                _error_at(
                    record.source,
                    record.line_number,
                    f"{field_name} must be a string",
                )
            )
            valid = False
    for field_name in ("client_ip", "method", "path"):
        if isinstance(data[field_name], str) and not data[field_name].strip():
            report.errors.append(
                _error_at(
                    record.source,
                    record.line_number,
                    f"{field_name} must not be empty",
                )
            )
            valid = False
    if data["service"] not in SERVICE_RULES:
        report.errors.append(
            _error_at(
                record.source,
                record.line_number,
                f"unknown gateway service: {data['service']!r}",
            )
        )
        valid = False
    request_time = _as_nonnegative_float(data["request_time_sec"])
    if request_time is None or not isinstance(data["request_time_sec"], str):
        report.errors.append(
            _error_at(
                record.source,
                record.line_number,
                "request_time_sec must be a numeric nonnegative string",
            )
        )
        valid = False
    if valid:
        expected_path = SERVICE_RULES[data["service"]]["endpoint"]
        if urlsplit(data["path"]).path != expected_path:
            report.errors.append(
                _error_at(
                    record.source,
                    record.line_number,
                    f"path does not match {data['service']}: {data['path']!r}",
                )
            )
            valid = False
    return valid


def _validate_service_record(record: LocatedRecord, report: ValidationReport):
    data = record.data
    valid = _validate_common_fields(record, SERVICE_REQUIRED_FIELDS, report)
    if not valid:
        return False

    for field_name in ("endpoint", "entity_type", "entity_value", "event_type"):
        if not isinstance(data[field_name], str):
            report.errors.append(
                _error_at(
                    record.source,
                    record.line_number,
                    f"{field_name} must be a string",
                )
            )
            valid = False
    processing_time = _as_nonnegative_float(data["processing_time_ms"])
    if processing_time is None or isinstance(data["processing_time_ms"], str):
        report.errors.append(
            _error_at(
                record.source,
                record.line_number,
                "processing_time_ms must be numeric and nonnegative",
            )
        )
        valid = False

    rules = SERVICE_RULES.get(data["service"])
    if rules is None:
        report.errors.append(
            _error_at(
                record.source,
                record.line_number,
                f"unknown backend service: {data['service']!r}",
            )
        )
        return False
    if data["endpoint"] != rules["endpoint"]:
        report.errors.append(
            _error_at(record.source, record.line_number, "unexpected endpoint")
        )
        valid = False
    if (
        isinstance(data["entity_type"], str)
        and data["entity_type"] not in rules["entity_types"]
    ):
        report.errors.append(
            _error_at(record.source, record.line_number, "unexpected entity_type")
        )
        valid = False
    if data["event_type"] != rules["event_type"]:
        report.errors.append(
            _error_at(record.source, record.line_number, "unexpected event_type")
        )
        valid = False
    return valid


def _index_unique(
    records: Iterable[LocatedRecord], label: str, report: ValidationReport
):
    indexed = {}
    for record in records:
        request_id = record.data["request_id"]
        if request_id in indexed:
            report.errors.append(
                _error_at(
                    record.source,
                    record.line_number,
                    f"duplicate {label} request_id: {request_id}",
                )
            )
            continue
        indexed[request_id] = record
    return indexed


def _check_correlation(report: ValidationReport):
    gateway_by_id = _index_unique(report.nginx_records, "gateway", report)
    service_by_id = _index_unique(report.service_records, "service", report)

    for request_id, gateway_record in gateway_by_id.items():
        service_record = service_by_id.get(request_id)
        if service_record is None:
            report.errors.append(
                f"request_id {request_id}: gateway record has no service record"
            )
            continue
        gateway = gateway_record.data
        service = service_record.data
        comparisons = (
            ("service", gateway["service"], service["service"]),
            ("status_code", gateway["status_code"], service["status_code"]),
            ("client_country", gateway["client_country"], service["client_country"]),
            ("scenario", gateway["scenario"], service["scenario"]),
            ("endpoint", urlsplit(gateway["path"]).path, service["endpoint"]),
        )
        mismatches = [
            f"{field} gateway={left!r} service={right!r}"
            for field, left, right in comparisons
            if left != right
        ]
        if mismatches:
            report.errors.append(
                f"request_id {request_id}: correlation mismatch: "
                + "; ".join(mismatches)
            )
        else:
            report.correlated_requests += 1

    for request_id in service_by_id.keys() - gateway_by_id.keys():
        report.errors.append(
            f"request_id {request_id}: service record has no gateway record"
        )


def _check_diversity(report: ValidationReport):
    required_services = set(SERVICE_RULES)
    missing_services = required_services - set(report.service_counts)
    if missing_services:
        report.errors.append(
            "missing services in gateway traffic: " + ", ".join(sorted(missing_services))
        )

    required_scenarios = {"normal", "slow", "server_error"}
    missing_scenarios = required_scenarios - set(report.scenario_counts)
    if missing_scenarios:
        report.errors.append(
            "missing traffic scenarios: " + ", ".join(sorted(missing_scenarios))
        )

    if len(report.country_counts) < 3:
        report.errors.append("traffic must contain at least three client countries")

    status_classes = {
        "success": any(200 <= code < 400 for code in report.status_counts),
        "4xx": any(400 <= code < 500 for code in report.status_counts),
        "5xx": any(500 <= code < 600 for code in report.status_counts),
    }
    for label, present in status_classes.items():
        if not present:
            report.errors.append(f"traffic has no {label} responses")

    required_entity_types = {"team", "match_day", "stadium", "city"}
    missing_entity_types = required_entity_types - set(report.entity_type_counts)
    if missing_entity_types:
        report.errors.append(
            "missing service entity types: "
            + ", ".join(sorted(missing_entity_types))
        )

    entity_values_by_service = defaultdict(set)
    for record in report.service_records:
        value = record.data["entity_value"]
        if value:
            entity_values_by_service[record.data["service"]].add(value)
    for service in sorted(required_services):
        if len(entity_values_by_service[service]) < 2:
            report.errors.append(
                f"{service} must contain at least two distinct nonempty entity values"
            )

    normal_times = report.scenario_times.get("normal", [])
    slow_times = report.scenario_times.get("slow", [])
    if normal_times and slow_times:
        normal_average = sum(normal_times) / len(normal_times)
        slow_average = sum(slow_times) / len(slow_times)
        if slow_average <= normal_average:
            report.errors.append(
                "slow scenario average response time is not greater than normal"
            )


def validate_logs(
    nginx_path: Path,
    service_paths: Iterable[Path],
    expected_min_requests: int = 1000,
    require_diversity: bool = True,
):
    report = ValidationReport()
    raw_nginx = _read_jsonl(Path(nginx_path), report)
    raw_services = []
    for service_path in service_paths:
        raw_services.extend(_read_jsonl(Path(service_path), report))

    report.nginx_records = [
        record for record in raw_nginx if _validate_nginx_record(record, report)
    ]
    report.service_records = [
        record
        for record in raw_services
        if _validate_service_record(record, report)
    ]

    for record in report.nginx_records:
        data = record.data
        report.status_counts[data["status_code"]] += 1
        report.service_counts[data["service"]] += 1
        report.scenario_counts[data["scenario"]] += 1
        report.country_counts[data["client_country"]] += 1
        report.scenario_times[data["scenario"]].append(
            float(data["request_time_sec"])
        )
    for record in report.service_records:
        report.entity_type_counts[record.data["entity_type"]] += 1

    if len(report.nginx_records) < expected_min_requests:
        report.errors.append(
            f"gateway log has {len(report.nginx_records)} valid requests; "
            f"expected at least {expected_min_requests}"
        )

    _check_correlation(report)
    if require_diversity:
        _check_diversity(report)
    return report


def _format_counter(counter: Counter):
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter)) or "none"


def print_report(report: ValidationReport, max_errors: int = 20):
    print("Log validation summary")
    print(f"  valid gateway records: {len(report.nginx_records)}")
    print(f"  valid service records: {len(report.service_records)}")
    print(f"  correlated requests: {report.correlated_requests}")
    print(f"  services: {_format_counter(report.service_counts)}")
    print(f"  scenarios: {_format_counter(report.scenario_counts)}")
    print(f"  statuses: {_format_counter(report.status_counts)}")
    print(f"  countries: {_format_counter(report.country_counts)}")
    print(f"  entity types: {_format_counter(report.entity_type_counts)}")

    if report.ok:
        print("VALIDATION PASSED")
        return
    print(f"VALIDATION FAILED: {len(report.errors)} error(s)")
    for error in report.errors[:max_errors]:
        print(f"  - {error}")
    remaining = len(report.errors) - max_errors
    if remaining > 0:
        print(f"  ... {remaining} more error(s) omitted")


def _nonnegative_int(value: str):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate Phase 1 gateway/service logs before MapReduce."
    )
    parser.add_argument("--nginx-log", type=Path, default=DEFAULT_NGINX_LOG)
    parser.add_argument(
        "--service-log",
        type=Path,
        action="append",
        dest="service_logs",
        help="service log path; repeat for each file (defaults to all three)",
    )
    parser.add_argument(
        "--expected-min-requests", type=_nonnegative_int, default=1000
    )
    parser.add_argument("--skip-diversity", action="store_true")
    parser.add_argument("--max-errors", type=_nonnegative_int, default=20)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    service_logs = args.service_logs or DEFAULT_SERVICE_LOGS
    report = validate_logs(
        args.nginx_log,
        service_logs,
        expected_min_requests=args.expected_min_requests,
        require_diversity=not args.skip_diversity,
    )
    print_report(report, max_errors=args.max_errors)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
