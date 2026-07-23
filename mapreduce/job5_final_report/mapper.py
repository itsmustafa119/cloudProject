#!/usr/bin/env python3
"""Normalize tagged Job 2-4 outputs under one final-summary reduce key."""

import csv
import json
import sys


SUPPORTED_TAGS = {
    "SERVICE_STATS",
    "ENDPOINT_STATS",
    "SCENARIO_STATS",
    "COUNTRY_TEAM",
    "COUNTRY_MATCHDAY",
    "COUNTRY_STADIUM",
    "POPULAR_TEAM",
    "POPULAR_MATCHDAY",
    "POPULAR_STADIUM",
}


def main():
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue
        tag, payload = line.split("\t", 1)
        if tag not in SUPPORTED_TAGS:
            continue
        try:
            row = next(csv.reader([payload]))
        except csv.Error as exc:
            print(f"job5 mapper skipped malformed CSV: {exc}", file=sys.stderr)
            continue
        value = json.dumps(
            {"tag": tag, "row": row}, ensure_ascii=False, separators=(",", ":")
        )
        print(f"summary\t{value}")


if __name__ == "__main__":
    main()
