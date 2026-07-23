#!/usr/bin/env python3
"""Sum country/entity request counts and emit tagged CSV rows."""

import csv
import io
import json
import sys


def csv_row(values):
    output = io.StringIO()
    csv.writer(output, lineterminator="").writerow(values)
    return output.getvalue()


def output_group(key, total):
    category = key[0]
    if category == "team":
        print(f"COUNTRY_TEAM\t{csv_row((key[1], key[2], total))}")
    elif category == "matchday":
        print(f"COUNTRY_MATCHDAY\t{csv_row((key[1], key[2], total))}")
    elif category == "stadium":
        print(
            f"COUNTRY_STADIUM\t{csv_row((key[1], key[2], key[3], total))}"
        )


def main():
    current_key = None
    total = 0
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue
        key_text, value_text = line.split("\t", 1)
        key = json.loads(key_text)
        value = int(value_text)
        if key != current_key:
            if current_key is not None:
                output_group(current_key, total)
            current_key = key
            total = 0
        total += value
    if current_key is not None:
        output_group(current_key, total)


if __name__ == "__main__":
    main()
