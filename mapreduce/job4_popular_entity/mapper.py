#!/usr/bin/env python3
"""Group Job 3 entity counts by category and country."""

import csv
import json
import sys


def emit(key, value):
    encoded_key = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
    encoded_value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    print(f"{encoded_key}\t{encoded_value}")


def process(tag, payload):
    row = next(csv.reader([payload]))
    if tag == "COUNTRY_TEAM" and len(row) == 3:
        emit(["team", row[0]], [row[1], int(row[2])])
    elif tag == "COUNTRY_MATCHDAY" and len(row) == 3:
        emit(["matchday", row[0]], [row[1], int(row[2])])
    elif tag == "COUNTRY_STADIUM" and len(row) == 4:
        emit(["stadium", row[0]], [row[1], row[2], int(row[3])])


def main():
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue
        tag, payload = line.split("\t", 1)
        if tag in {"COUNTRY_TEAM", "COUNTRY_MATCHDAY", "COUNTRY_STADIUM"}:
            try:
                process(tag, payload)
            except (ValueError, IndexError) as exc:
                print(f"job4 mapper skipped row: {exc}: {payload!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
