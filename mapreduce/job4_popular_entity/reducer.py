#!/usr/bin/env python3
"""Select each country's most requested entity with deterministic ties."""

import csv
import io
import json
import sys


def csv_row(values):
    output = io.StringIO()
    csv.writer(output, lineterminator="").writerow(values)
    return output.getvalue()


def candidate_key(value):
    entity_value = value[-2] if len(value) == 3 else value[0]
    total = value[-1]
    return (-total, entity_value.casefold(), entity_value, *value[:-2])


def output_group(key, candidates):
    winner = min(candidates, key=candidate_key)
    category, country = key
    if category == "team":
        print(f"POPULAR_TEAM\t{csv_row((country, winner[0], winner[1]))}")
    elif category == "matchday":
        print(f"POPULAR_MATCHDAY\t{csv_row((country, winner[0], winner[1]))}")
    elif category == "stadium":
        print(
            f"POPULAR_STADIUM\t"
            f"{csv_row((country, winner[0], winner[1], winner[2]))}"
        )


def main():
    current_key = None
    candidates = []
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue
        key_text, value_text = line.split("\t", 1)
        key = json.loads(key_text)
        value = json.loads(value_text)
        if key != current_key:
            if current_key is not None:
                output_group(current_key, candidates)
            current_key = key
            candidates = []
        candidates.append(value)
    if current_key is not None:
        output_group(current_key, candidates)


if __name__ == "__main__":
    main()
