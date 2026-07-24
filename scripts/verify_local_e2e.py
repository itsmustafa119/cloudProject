#!/usr/bin/env python3
"""Run all five Streaming jobs locally against a hand-calculated fixture."""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from materialize_mapreduce_outputs import materialize_all


ROOT = Path(__file__).resolve().parent.parent
MAPREDUCE = ROOT / "mapreduce"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "e2e" / "raw_logs.jsonl"
DEFAULT_EXPECTED = ROOT / "tests" / "fixtures" / "e2e" / "expected_results.json"


def run_program(relative_path: str, input_text: str) -> str:
    script = MAPREDUCE / relative_path
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
    if result.returncode:
        raise RuntimeError(
            f"{relative_path} failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def shuffle_reduce(job_directory: str, mapper_input: str) -> str:
    mapped = run_program(f"{job_directory}/mapper.py", mapper_input)
    lines = sorted(line for line in mapped.splitlines() if line)
    reducer_input = "\n".join(lines) + ("\n" if lines else "")
    return run_program(f"{job_directory}/reducer.py", reducer_input)


def execute_pipeline(raw_input: str) -> dict[str, str]:
    job1 = shuffle_reduce("job1_parse_clean", raw_input)
    job2 = shuffle_reduce("job2_nginx_aggregation", job1)
    job3 = shuffle_reduce("job3_country_entity", job1)
    job4 = shuffle_reduce("job4_popular_entity", job3)
    job5 = shuffle_reduce("job5_final_report", job2 + job3 + job4)
    return {
        "job1": job1,
        "job2": job2,
        "job3": job3,
        "job4": job4,
        "job5": job5,
    }


def tagged_rows(text: str, expected_tag: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith(expected_tag + "\t"):
            rows.append(next(csv.reader([line.split("\t", 1)[1]])))
    return rows


def validate_expected(results: dict[str, str], expected: dict) -> None:
    counts = Counter(
        line.split("\t", 1)[0] for line in results["job1"].splitlines()
    )
    if dict(counts) != expected["job1_tag_counts"]:
        raise AssertionError(
            f"Job 1 tag counts differ: expected "
            f"{expected['job1_tag_counts']}, got {dict(counts)}"
        )

    service_stats = {
        row[0]: row[1:] for row in tagged_rows(results["job2"], "SERVICE_STATS")
    }
    if service_stats != expected["service_stats"]:
        raise AssertionError(
            f"service statistics differ: expected "
            f"{expected['service_stats']}, got {service_stats}"
        )

    popularity_checks = (
        ("POPULAR_TEAM", "popular_team_by_country"),
        ("POPULAR_MATCHDAY", "popular_matchday_by_country"),
        ("POPULAR_STADIUM", "popular_stadium_by_country"),
    )
    for tag, expected_key in popularity_checks:
        actual = {
            row[0]: row[1:] for row in tagged_rows(results["job4"], tag)
        }
        if actual != expected[expected_key]:
            raise AssertionError(
                f"{tag} differs: expected {expected[expected_key]}, got {actual}"
            )

    summary = json.loads(results["job5"].strip())
    if summary != expected["summary"]:
        raise AssertionError(
            "final summary differs:\n"
            f"expected={json.dumps(expected['summary'], ensure_ascii=False)}\n"
            f"actual={json.dumps(summary, ensure_ascii=False)}"
        )


def materialize(results: dict[str, str], output_root: Path) -> list[Path]:
    with tempfile.TemporaryDirectory(prefix="phase1-e2e-raw-") as temp_dir:
        raw_root = Path(temp_dir)
        raw_paths = {}
        for job_name, output in results.items():
            raw_path = raw_root / f"{job_name}.txt"
            raw_path.write_text(output, encoding="utf-8")
            raw_paths[job_name] = raw_path
        return materialize_all(raw_paths, output_root)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Simulate Hadoop Streaming shuffle/sort locally and compare every "
            "stage with deterministic hand-calculated expectations."
        )
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Keep materialized artifacts here; otherwise use a temporary directory.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        raw_input = args.fixture.read_text(encoding="utf-8")
        expected = json.loads(args.expected.read_text(encoding="utf-8"))
        results = execute_pipeline(raw_input)
        validate_expected(results, expected)

        if args.output_root is None:
            with tempfile.TemporaryDirectory(prefix="phase1-e2e-output-") as temp_dir:
                created = materialize(results, Path(temp_dir))
                if len(created) != 13:
                    raise AssertionError(f"expected 13 artifacts, got {len(created)}")
        else:
            created = materialize(results, args.output_root)
            if len(created) != 13:
                raise AssertionError(f"expected 13 artifacts, got {len(created)}")
    except (OSError, ValueError, RuntimeError, AssertionError, json.JSONDecodeError) as exc:
        print(f"END-TO-END VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1

    print("END-TO-END VERIFICATION PASSED")
    print("validated 5 Streaming jobs and 13 materialized artifacts")
    if args.output_root is not None:
        print(f"artifacts: {args.output_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
