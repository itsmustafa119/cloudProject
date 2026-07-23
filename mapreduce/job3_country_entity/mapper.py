#!/usr/bin/env python3
"""Count requested entities by client country from cleaned service CSV."""

import csv
import json
import sys


def emit(key):
    encoded_key = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
    print(f"{encoded_key}\t1")


def process(payload):
    row = next(csv.reader([payload]))
    if row and row[0] == "timestamp":
        return
    if len(row) != 10:
        print(f"job3 mapper skipped malformed row: {payload!r}", file=sys.stderr)
        return
    _, _, country, service, _, entity_type, entity_value, _, _, _ = row

    if service == "team-service" and entity_type == "team":
        emit(["team", country, entity_value])
    elif service == "match-service" and entity_type == "match_day":
        emit(["matchday", country, entity_value])
    elif service == "stadium-service" and entity_type in {"stadium", "city"}:
        emit(["stadium", country, entity_type, entity_value])
    else:
        print(f"job3 mapper skipped unknown entity row: {payload!r}", file=sys.stderr)


def main():
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if not line:
            continue
        if line.startswith("SERVICE\t"):
            process(line.split("\t", 1)[1])
        elif "\t" not in line:
            process(line)


if __name__ == "__main__":
    main()
