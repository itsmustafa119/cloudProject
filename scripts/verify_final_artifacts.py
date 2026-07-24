#!/usr/bin/env python3
"""Cross-check final MapReduce artifacts against one another and predictions."""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from materialize_mapreduce_outputs import LAYOUTS, SUMMARY_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"
DEFAULT_PREDICTIONS = (
    PROJECT_ROOT / "mapreduce" / "job5_final_report" / "predictions.json"
)


def lexical_key(value):
    return value.casefold(), value


def select_max(mapping):
    if not mapping:
        return None
    maximum = max(mapping.values())
    return min(
        (key for key, value in mapping.items() if value == maximum),
        key=lexical_key,
    )


def read_csv(output_root: Path, relative_path: str, expected_header: str):
    path = output_root / relative_path
    if not path.is_file():
        raise ValueError(f"required artifact does not exist: {path}")
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.reader(source)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"artifact is empty: {path}") from None
        expected = next(csv.reader([expected_header]))
        if header != expected:
            raise ValueError(
                f"{path}: header differs; expected {expected}, got {header}"
            )
        rows = list(reader)
    expected_columns = len(expected)
    for line_number, row in enumerate(rows, start=2):
        if len(row) != expected_columns:
            raise ValueError(
                f"{path}:{line_number}: expected {expected_columns} columns, "
                f"got {len(row)}"
            )
    return rows


def load_artifacts(output_root: Path):
    artifacts = {}
    for job_name, layouts in LAYOUTS.items():
        for tag, (relative_path, header, _, required) in layouts.items():
            rows = read_csv(output_root, relative_path, header)
            if required and not rows:
                raise ValueError(f"{relative_path}: required artifact has no rows")
            artifacts[tag] = rows
    return artifacts


def load_summary(output_root: Path):
    path = output_root / "final" / "summary.json"
    if not path.is_file():
        raise ValueError(f"required artifact does not exist: {path}")
    summary = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"{path}: summary must be a JSON object")
    if set(summary) != SUMMARY_FIELDS:
        missing = sorted(SUMMARY_FIELDS - set(summary))
        extra = sorted(set(summary) - SUMMARY_FIELDS)
        raise ValueError(f"{path}: summary fields differ; missing={missing}, extra={extra}")
    return summary


def integer(value, location):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{location}: expected an integer, got {value!r}") from None


def number(value, location):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{location}: expected a number, got {value!r}") from None


def check_equal(actual, expected, label):
    if actual != expected:
        raise ValueError(f"{label} differs: expected {expected!r}, got {actual!r}")


def verify_artifacts(
    output_root: Path,
    predictions_path: Path,
    expected_min_requests: int = 100_000,
):
    artifacts = load_artifacts(output_root)
    summary = load_summary(output_root)
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))

    nginx_ids = [row[1] for row in artifacts["NGINX"]]
    service_ids = [row[1] for row in artifacts["SERVICE"]]
    if len(nginx_ids) != len(set(nginx_ids)):
        raise ValueError("cleaned Nginx output contains duplicate request IDs")
    if len(service_ids) != len(set(service_ids)):
        raise ValueError("cleaned service output contains duplicate request IDs")
    check_equal(set(service_ids), set(nginx_ids), "cleaned request-ID correlation")

    service_requests = {}
    service_error_rates = {}
    for row in artifacts["SERVICE_STATS"]:
        service_requests[row[0]] = integer(row[1], f"service_stats:{row[0]}")
        service_error_rates[row[0]] = number(
            row[6], f"service_stats:{row[0]}:error_rate"
        )
    total_requests = sum(service_requests.values())
    if total_requests < expected_min_requests:
        raise ValueError(
            f"final data has {total_requests} requests; "
            f"expected at least {expected_min_requests}"
        )
    check_equal(len(nginx_ids), total_requests, "cleaned Nginx row count")
    check_equal(len(service_ids), total_requests, "cleaned service row count")

    endpoint_times = {
        row[1]: number(row[8], f"endpoint_stats:{row[1]}:average_time")
        for row in artifacts["ENDPOINT_STATS"]
    }
    team_totals = Counter()
    for country, team, count in artifacts["COUNTRY_TEAM"]:
        team_totals[team] += integer(count, f"country_team:{country}:{team}")
    matchday_totals = Counter()
    for country, matchday, count in artifacts["COUNTRY_MATCHDAY"]:
        matchday_totals[matchday] += integer(
            count, f"country_matchday:{country}:{matchday}"
        )
    stadium_totals = Counter()
    for country, entity_type, entity_value, count in artifacts["COUNTRY_STADIUM"]:
        if entity_type == "stadium":
            stadium_totals[entity_value] += integer(
                count, f"country_stadium:{country}:{entity_value}"
            )
    popular_teams = {
        country: team for country, team, _ in artifacts["POPULAR_TEAM"]
    }

    expected_summary = {
        "total_requests": total_requests,
        "most_requested_service": select_max(service_requests),
        "highest_error_rate_service": select_max(service_error_rates),
        "slowest_endpoint": select_max(endpoint_times),
        "most_popular_team_overall": select_max(team_totals),
        "most_requested_match_day_overall": select_max(matchday_totals),
        "most_requested_stadium_overall": select_max(stadium_totals),
        "popular_team_by_country": {
            country: popular_teams[country]
            for country in sorted(popular_teams, key=lexical_key)
        },
        "predicted_champion": predictions["predicted_champion"],
        "predicted_final": predictions["predicted_final"],
        "predicted_final_winner": predictions["predicted_final_winner"],
        "predicted_final_stadium": predictions["predicted_final_stadium"],
    }
    check_equal(summary, expected_summary, "final summary")
    return {
        "total_requests": total_requests,
        "invalid_rows": len(artifacts["INVALID"]),
        "services": len(service_requests),
        "countries": len({row[0] for row in artifacts["POPULAR_TEAM"]}),
    }


def nonnegative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify final summary values against all intermediate CSV files."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument(
        "--expected-min-requests", type=nonnegative_int, default=100_000
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        report = verify_artifacts(
            args.output_root,
            args.predictions,
            expected_min_requests=args.expected_min_requests,
        )
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        print(f"FINAL ARTIFACT VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    print("FINAL ARTIFACT VERIFICATION PASSED")
    print(f"  total requests: {report['total_requests']}")
    print(f"  invalid source rows: {report['invalid_rows']}")
    print(f"  aggregated services: {report['services']}")
    print(f"  countries with a popular team: {report['countries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
