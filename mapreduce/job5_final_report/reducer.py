#!/usr/bin/env python3
"""Combine analytical outputs into the required final summary JSON."""

import json
import sys
from collections import Counter
from pathlib import Path


def lexical_key(value):
    return value.casefold(), value


def select_max(mapping):
    if not mapping:
        return None
    maximum = max(mapping.values())
    candidates = [key for key, value in mapping.items() if value == maximum]
    return min(candidates, key=lexical_key)


def load_predictions():
    candidates = (
        Path("predictions.json"),
        Path(__file__).resolve().parent / "predictions.json",
    )
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("predictions.json was not provided to Job 5")


def main():
    service_requests = {}
    service_error_rates = {}
    endpoint_response_times = {}
    team_totals = Counter()
    matchday_totals = Counter()
    stadium_totals = Counter()
    popular_team_by_country = {}

    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue
        _, value_text = line.split("\t", 1)
        value = json.loads(value_text)
        tag = value["tag"]
        row = value["row"]

        if tag == "SERVICE_STATS" and len(row) == 8:
            service_requests[row[0]] = int(row[1])
            service_error_rates[row[0]] = float(row[6])
        elif tag == "ENDPOINT_STATS" and len(row) == 9:
            endpoint_response_times[row[1]] = float(row[8])
        elif tag == "COUNTRY_TEAM" and len(row) == 3:
            team_totals[row[1]] += int(row[2])
        elif tag == "COUNTRY_MATCHDAY" and len(row) == 3:
            matchday_totals[row[1]] += int(row[2])
        elif tag == "COUNTRY_STADIUM" and len(row) == 4 and row[1] == "stadium":
            stadium_totals[row[2]] += int(row[3])
        elif tag == "POPULAR_TEAM" and len(row) == 3:
            popular_team_by_country[row[0]] = row[1]

    predictions = load_predictions()
    summary = {
        "total_requests": sum(service_requests.values()),
        "most_requested_service": select_max(service_requests),
        "highest_error_rate_service": select_max(service_error_rates),
        "slowest_endpoint": select_max(endpoint_response_times),
        "most_popular_team_overall": select_max(team_totals),
        "most_requested_match_day_overall": select_max(matchday_totals),
        "most_requested_stadium_overall": select_max(stadium_totals),
        "popular_team_by_country": {
            country: popular_team_by_country[country]
            for country in sorted(popular_team_by_country, key=lexical_key)
        },
        "predicted_champion": predictions["predicted_champion"],
        "predicted_final": predictions["predicted_final"],
        "predicted_final_winner": predictions["predicted_final_winner"],
        "predicted_final_stadium": predictions["predicted_final_stadium"],
    }
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
