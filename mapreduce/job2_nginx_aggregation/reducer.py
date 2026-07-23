#!/usr/bin/env python3
"""Aggregate gateway metrics and emit tagged CSV result rows."""

import csv
import io
import json
import sys


def csv_row(values):
    output = io.StringIO()
    csv.writer(output, lineterminator="").writerow(values)
    return output.getvalue()


def output_group(key, totals):
    dimension = key[0]
    total, success, client_error, server_error, error, response_time_sum = totals
    error_rate = error / total if total else 0.0
    average_time = response_time_sum / total if total else 0.0
    metrics = (
        total,
        success,
        client_error,
        server_error,
        error,
        f"{error_rate:.6f}",
        f"{average_time:.3f}",
    )

    if dimension == "service":
        print(f"SERVICE_STATS\t{csv_row((key[1], *metrics))}")
    elif dimension == "endpoint":
        print(f"ENDPOINT_STATS\t{csv_row((key[1], key[2], *metrics))}")
    elif dimension == "scenario":
        print(f"SCENARIO_STATS\t{csv_row((key[1], *metrics))}")


def main():
    current_key = None
    totals = None
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue
        key_text, value_text = line.split("\t", 1)
        key = json.loads(key_text)
        values = json.loads(value_text)
        if key != current_key:
            if current_key is not None:
                output_group(current_key, totals)
            current_key = key
            totals = [0, 0, 0, 0, 0, 0.0]
        for index, value in enumerate(values):
            totals[index] += value
    if current_key is not None:
        output_group(current_key, totals)


if __name__ == "__main__":
    main()
