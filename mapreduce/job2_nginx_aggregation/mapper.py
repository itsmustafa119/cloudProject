#!/usr/bin/env python3
"""Emit service, endpoint, and scenario aggregation keys from cleaned Nginx CSV."""

import csv
import json
import sys
from urllib.parse import urlsplit


def emit(key, metrics):
    encoded_key = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
    encoded_value = json.dumps(metrics, separators=(",", ":"))
    print(f"{encoded_key}\t{encoded_value}")


def process(payload):
    row = next(csv.reader([payload]))
    if row and row[0] == "timestamp":
        return
    if len(row) != 10:
        print(f"job2 mapper skipped malformed row: {payload!r}", file=sys.stderr)
        return
    _, _, _, scenario, service, _, path, status_text, time_text, _ = row
    try:
        status_code = int(status_text)
        response_time_ms = float(time_text)
    except ValueError:
        print(f"job2 mapper skipped nonnumeric row: {payload!r}", file=sys.stderr)
        return

    success = int(200 <= status_code < 400)
    client_error = int(400 <= status_code < 500)
    server_error = int(500 <= status_code < 600)
    error = client_error + server_error
    metrics = [1, success, client_error, server_error, error, response_time_ms]
    endpoint = urlsplit(path).path

    emit(["service", service], metrics)
    emit(["endpoint", service, endpoint], metrics)
    emit(["scenario", scenario], metrics)


def main():
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if not line:
            continue
        if line.startswith("NGINX\t"):
            process(line.split("\t", 1)[1])
        elif "\t" not in line:
            process(line)


if __name__ == "__main__":
    main()
