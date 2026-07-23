#!/usr/bin/env python3
"""Split tagged Hadoop part files into the required local CSV/JSON artifacts."""

import argparse
import csv
import json
from pathlib import Path


LAYOUTS = {
    "job1": {
        "NGINX": (
            "job1/cleaned_nginx_logs.csv",
            "timestamp,request_id,client_country,scenario,service,method,path,"
            "status_code,request_time_ms,user_agent",
            10,
            True,
        ),
        "SERVICE": (
            "job1/cleaned_service_logs.csv",
            "timestamp,request_id,client_country,service,endpoint,entity_type,"
            "entity_value,status_code,processing_time_ms,event_type",
            10,
            True,
        ),
        "INVALID": (
            "job1/invalid_logs.csv",
            "source,error,raw_line",
            3,
            False,
        ),
    },
    "job2": {
        "SERVICE_STATS": (
            "job2/service_stats.csv",
            "service,total_requests,success_count,client_error_count,"
            "server_error_count,error_count,error_rate,avg_response_time_ms",
            8,
            True,
        ),
        "ENDPOINT_STATS": (
            "job2/endpoint_stats.csv",
            "service,endpoint,total_requests,success_count,client_error_count,"
            "server_error_count,error_count,error_rate,avg_response_time_ms",
            9,
            True,
        ),
        "SCENARIO_STATS": (
            "job2/scenario_stats.csv",
            "scenario,total_requests,success_count,client_error_count,"
            "server_error_count,error_count,error_rate,avg_response_time_ms",
            8,
            True,
        ),
    },
    "job3": {
        "COUNTRY_TEAM": (
            "job3/country_team_requests.csv",
            "country,team,total_requests",
            3,
            True,
        ),
        "COUNTRY_MATCHDAY": (
            "job3/country_matchday_requests.csv",
            "country,match_day,total_requests",
            3,
            True,
        ),
        "COUNTRY_STADIUM": (
            "job3/country_stadium_requests.csv",
            "country,entity_type,entity_value,total_requests",
            4,
            True,
        ),
    },
    "job4": {
        "POPULAR_TEAM": (
            "job4/popular_team_by_country.csv",
            "country,popular_team,total_requests",
            3,
            True,
        ),
        "POPULAR_MATCHDAY": (
            "job4/popular_matchday_by_country.csv",
            "country,popular_match_day,total_requests",
            3,
            True,
        ),
        "POPULAR_STADIUM": (
            "job4/popular_stadium_by_country.csv",
            "country,entity_type,popular_entity,total_requests",
            4,
            True,
        ),
    },
}

SUMMARY_FIELDS = {
    "total_requests",
    "most_requested_service",
    "highest_error_rate_service",
    "slowest_endpoint",
    "most_popular_team_overall",
    "most_requested_match_day_overall",
    "most_requested_stadium_overall",
    "popular_team_by_country",
    "predicted_champion",
    "predicted_final",
    "predicted_final_winner",
    "predicted_final_stadium",
}


def _read_tagged(path: Path, expected_tags: set[str]):
    rows = {tag: [] for tag in expected_tags}
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            line = line.rstrip("\r\n")
            if not line:
                continue
            if "\t" not in line:
                raise ValueError(f"{path}:{line_number}: missing tag separator")
            tag, payload = line.split("\t", 1)
            if tag not in expected_tags:
                raise ValueError(f"{path}:{line_number}: unexpected tag {tag!r}")
            rows[tag].append(payload)
    return rows


def _validate_csv_payload(payload: str, expected_columns: int, location: str):
    row = next(csv.reader([payload]))
    if len(row) != expected_columns:
        raise ValueError(
            f"{location}: expected {expected_columns} CSV columns, got {len(row)}"
        )


def materialize_tagged_job(job_name: str, raw_path: Path, output_root: Path):
    layout = LAYOUTS[job_name]
    tagged_rows = _read_tagged(raw_path, set(layout))
    created = []
    for tag, (relative_path, header, column_count, required) in layout.items():
        rows = tagged_rows[tag]
        if required and not rows:
            raise ValueError(f"{raw_path}: required tag {tag!r} has no rows")
        for index, payload in enumerate(rows, start=1):
            _validate_csv_payload(payload, column_count, f"{raw_path}:{tag}:{index}")

        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="\n") as output:
            output.write(header + "\n")
            for payload in rows:
                output.write(payload + "\n")
        created.append(destination)
    return created


def materialize_summary(raw_path: Path, output_root: Path):
    lines = [
        line.strip()
        for line in raw_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(lines) != 1:
        raise ValueError(f"{raw_path}: expected exactly one nonempty summary line")
    summary = json.loads(lines[0])
    if not isinstance(summary, dict):
        raise ValueError(f"{raw_path}: summary must be a JSON object")
    missing = sorted(SUMMARY_FIELDS - set(summary))
    if missing:
        raise ValueError(f"{raw_path}: missing summary fields: {', '.join(missing)}")
    if not isinstance(summary["total_requests"], int) or summary["total_requests"] < 1:
        raise ValueError(f"{raw_path}: total_requests must be a positive integer")

    destination = output_root / "final" / "summary.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def materialize_all(raw_paths: dict[str, Path], output_root: Path):
    created = []
    for job_name in ("job1", "job2", "job3", "job4"):
        created.extend(
            materialize_tagged_job(job_name, raw_paths[job_name], output_root)
        )
    created.append(materialize_summary(raw_paths["job5"], output_root))
    return created


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Create required host outputs from merged Hadoop part files."
    )
    for job_name in ("job1", "job2", "job3", "job4", "job5"):
        parser.add_argument(f"--{job_name}", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    raw_paths = {
        job_name: getattr(args, job_name)
        for job_name in ("job1", "job2", "job3", "job4", "job5")
    }
    try:
        created = materialize_all(raw_paths, args.output_root)
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for path in created:
        print(f"created: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
