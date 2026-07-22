"""
match-service
=============
Returns the World Cup 2026 matches scheduled for a given date.

    GET /api/matches?date=2026-06-25

Phase 1 notes:
* No database. The schedule lives in an in-memory dictionary.
* This service must write a structured JSON Lines log to:
      data/service_logs/match_service.log
  Implement write_service_log() below to complete this requirement.
* Response shape can be influenced via the X-Scenario header:
      X-Scenario: slow         -> add extra latency
      X-Scenario: server_error -> return 500
"""
import os
import random
import time
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="match-service")

# ---------------------------------------------------------------------------
# In-memory "database": date -> list of matches (group-stage schedule)
# Stadium names are the canonical city-based names used across all services.
# ---------------------------------------------------------------------------
SCHEDULE = {
    "2026-06-12": [
        {"team_a": "Mexico",      "team_b": "Ecuador",      "stadium": "Mexico City Stadium",          "city": "Mexico City",            "country": "Mexico", "stage": "Group Stage"},
        {"team_a": "USA",         "team_b": "Serbia",       "stadium": "Kansas City Stadium",          "city": "Kansas City",            "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Japan",       "team_b": "Belgium",      "stadium": "Dallas Stadium",               "city": "Dallas",                 "country": "USA",    "stage": "Group Stage"},
    ],
    "2026-06-13": [
        {"team_a": "Argentina",   "team_b": "Morocco",      "stadium": "New York New Jersey Stadium",  "city": "New York New Jersey",    "country": "USA",    "stage": "Group Stage"},
        {"team_a": "France",      "team_b": "South Korea",  "stadium": "Houston Stadium",              "city": "Houston",                "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Germany",     "team_b": "Saudi Arabia", "stadium": "Monterrey Stadium",            "city": "Monterrey",              "country": "Mexico", "stage": "Group Stage"},
    ],
    "2026-06-14": [
        {"team_a": "Spain",       "team_b": "Colombia",     "stadium": "Los Angeles Stadium",          "city": "Los Angeles",            "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Portugal",    "team_b": "Uruguay",      "stadium": "San Francisco Bay Area Stadium","city": "San Francisco Bay Area", "country": "USA",    "stage": "Group Stage"},
        {"team_a": "England",     "team_b": "Nigeria",      "stadium": "Atlanta Stadium",              "city": "Atlanta",                "country": "USA",    "stage": "Group Stage"},
    ],
    "2026-06-15": [
        {"team_a": "Brazil",      "team_b": "Croatia",      "stadium": "Dallas Stadium",               "city": "Dallas",                 "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Netherlands", "team_b": "Italy",        "stadium": "Miami Stadium",                "city": "Miami",                  "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Canada",      "team_b": "Senegal",      "stadium": "BC Place Vancouver",           "city": "Vancouver",              "country": "Canada", "stage": "Group Stage"},
    ],
    "2026-06-18": [
        {"team_a": "Mexico",      "team_b": "Denmark",      "stadium": "Mexico City Stadium",          "city": "Mexico City",            "country": "Mexico", "stage": "Group Stage"},
        {"team_a": "Argentina",   "team_b": "Iran",         "stadium": "New York New Jersey Stadium",  "city": "New York New Jersey",    "country": "USA",    "stage": "Group Stage"},
        {"team_a": "USA",         "team_b": "Ecuador",      "stadium": "Kansas City Stadium",          "city": "Kansas City",            "country": "USA",    "stage": "Group Stage"},
    ],
    "2026-06-19": [
        {"team_a": "France",      "team_b": "Nigeria",      "stadium": "Houston Stadium",              "city": "Houston",                "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Germany",     "team_b": "Japan",        "stadium": "Monterrey Stadium",            "city": "Monterrey",              "country": "Mexico", "stage": "Group Stage"},
        {"team_a": "Brazil",      "team_b": "Senegal",      "stadium": "Dallas Stadium",               "city": "Dallas",                 "country": "USA",    "stage": "Group Stage"},
    ],
    "2026-06-22": [
        {"team_a": "Spain",       "team_b": "South Korea",  "stadium": "Los Angeles Stadium",          "city": "Los Angeles",            "country": "USA",    "stage": "Group Stage"},
        {"team_a": "England",     "team_b": "Colombia",     "stadium": "Atlanta Stadium",              "city": "Atlanta",                "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Portugal",    "team_b": "Canada",       "stadium": "San Francisco Bay Area Stadium","city": "San Francisco Bay Area", "country": "USA",    "stage": "Group Stage"},
    ],
    "2026-06-25": [
        {"team_a": "Netherlands", "team_b": "Morocco",      "stadium": "BC Place Vancouver",           "city": "Vancouver",              "country": "Canada", "stage": "Group Stage"},
        {"team_a": "Belgium",     "team_b": "Australia",    "stadium": "Kansas City Stadium",          "city": "Kansas City",            "country": "USA",    "stage": "Group Stage"},
        {"team_a": "Croatia",     "team_b": "Italy",        "stadium": "Miami Stadium",                "city": "Miami",                  "country": "USA",    "stage": "Group Stage"},
    ],
}

# ---------------------------------------------------------------------------
# PREDICTED knockout matches — simulation only, NOT official FIFA results.
# Every entry carries "status": "predicted" and "is_prediction": True.
# ---------------------------------------------------------------------------
PREDICTED_KNOCKOUT_MATCHES = [
    # Round of 32
    {"date": "2026-06-28", "stage": "Round of 32",         "team_a": "South Africa",  "team_b": "Canada",      "stadium": "Toronto Stadium",              "city": "Toronto",              "country": "Canada", "status": "predicted", "is_prediction": True, "predicted_winner": "Canada",      "predicted_score": "1-2"},
    {"date": "2026-06-28", "stage": "Round of 32",         "team_a": "Brazil",        "team_b": "Sweden",      "stadium": "Houston Stadium",              "city": "Houston",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Brazil",      "predicted_score": "3-1"},
    {"date": "2026-06-29", "stage": "Round of 32",         "team_a": "Germany",       "team_b": "Australia",   "stadium": "Dallas Stadium",               "city": "Dallas",               "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Germany",     "predicted_score": "2-0"},
    {"date": "2026-06-29", "stage": "Round of 32",         "team_a": "Netherlands",   "team_b": "Morocco",     "stadium": "New York New Jersey Stadium",  "city": "New York New Jersey",  "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Netherlands", "predicted_score": "2-1"},
    {"date": "2026-06-30", "stage": "Round of 32",         "team_a": "Mexico",        "team_b": "Ivory Coast", "stadium": "Mexico City Stadium",          "city": "Mexico City",          "country": "Mexico", "status": "predicted", "is_prediction": True, "predicted_winner": "Mexico",      "predicted_score": "2-1"},
    {"date": "2026-06-30", "stage": "Round of 32",         "team_a": "France",        "team_b": "Ghana",       "stadium": "Boston Stadium",               "city": "Boston",               "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "France",      "predicted_score": "3-1"},
    {"date": "2026-07-01", "stage": "Round of 32",         "team_a": "United States", "team_b": "Belgium",     "stadium": "San Francisco Bay Area Stadium","city": "San Francisco Bay Area","country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "United States","predicted_score": "2-1"},
    {"date": "2026-07-01", "stage": "Round of 32",         "team_a": "England",       "team_b": "Algeria",     "stadium": "Seattle Stadium",              "city": "Seattle",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "England",     "predicted_score": "2-0"},
    {"date": "2026-07-02", "stage": "Round of 32",         "team_a": "Spain",         "team_b": "South Korea", "stadium": "Los Angeles Stadium",          "city": "Los Angeles",          "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Spain",       "predicted_score": "2-0"},
    {"date": "2026-07-02", "stage": "Round of 32",         "team_a": "Argentina",     "team_b": "Saudi Arabia","stadium": "Miami Stadium",                "city": "Miami",                "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Argentina",   "predicted_score": "3-1"},
    {"date": "2026-07-02", "stage": "Round of 32",         "team_a": "Portugal",      "team_b": "Japan",       "stadium": "Philadelphia Stadium",         "city": "Philadelphia",         "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Portugal",    "predicted_score": "2-1"},
    {"date": "2026-07-03", "stage": "Round of 32",         "team_a": "Switzerland",   "team_b": "Tunisia",     "stadium": "Atlanta Stadium",              "city": "Atlanta",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Switzerland", "predicted_score": "1-0"},
    {"date": "2026-07-03", "stage": "Round of 32",         "team_a": "Egypt",         "team_b": "Croatia",     "stadium": "Kansas City Stadium",          "city": "Kansas City",          "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Croatia",     "predicted_score": "1-2"},
    {"date": "2026-07-03", "stage": "Round of 32",         "team_a": "Uruguay",       "team_b": "Austria",     "stadium": "Monterrey Stadium",            "city": "Monterrey",            "country": "Mexico", "status": "predicted", "is_prediction": True, "predicted_winner": "Uruguay",     "predicted_score": "2-1"},
    {"date": "2026-07-03", "stage": "Round of 32",         "team_a": "Norway",        "team_b": "Paraguay",    "stadium": "Guadalajara Stadium",          "city": "Guadalajara",          "country": "Mexico", "status": "predicted", "is_prediction": True, "predicted_winner": "Norway",      "predicted_score": "2-1"},
    {"date": "2026-07-03", "stage": "Round of 32",         "team_a": "Colombia",      "team_b": "Iran",        "stadium": "BC Place Vancouver",           "city": "Vancouver",            "country": "Canada", "status": "predicted", "is_prediction": True, "predicted_winner": "Colombia",    "predicted_score": "2-0"},
    # Round of 16
    {"date": "2026-07-04", "stage": "Round of 16",         "team_a": "Canada",        "team_b": "Brazil",      "stadium": "Toronto Stadium",              "city": "Toronto",              "country": "Canada", "status": "predicted", "is_prediction": True, "predicted_winner": "Brazil",      "predicted_score": "1-3"},
    {"date": "2026-07-04", "stage": "Round of 16",         "team_a": "Germany",       "team_b": "Netherlands", "stadium": "Dallas Stadium",               "city": "Dallas",               "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Germany",     "predicted_score": "2-1"},
    {"date": "2026-07-05", "stage": "Round of 16",         "team_a": "Mexico",        "team_b": "France",      "stadium": "Mexico City Stadium",          "city": "Mexico City",          "country": "Mexico", "status": "predicted", "is_prediction": True, "predicted_winner": "France",      "predicted_score": "1-2"},
    {"date": "2026-07-05", "stage": "Round of 16",         "team_a": "United States", "team_b": "England",     "stadium": "New York New Jersey Stadium",  "city": "New York New Jersey",  "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "England",     "predicted_score": "1-2"},
    {"date": "2026-07-06", "stage": "Round of 16",         "team_a": "Spain",         "team_b": "Argentina",   "stadium": "Los Angeles Stadium",          "city": "Los Angeles",          "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Argentina",   "predicted_score": "1-2"},
    {"date": "2026-07-06", "stage": "Round of 16",         "team_a": "Portugal",      "team_b": "Switzerland", "stadium": "Miami Stadium",                "city": "Miami",                "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Portugal",    "predicted_score": "2-0"},
    {"date": "2026-07-07", "stage": "Round of 16",         "team_a": "Croatia",       "team_b": "Uruguay",     "stadium": "Atlanta Stadium",              "city": "Atlanta",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Uruguay",     "predicted_score": "1-2"},
    {"date": "2026-07-07", "stage": "Round of 16",         "team_a": "Norway",        "team_b": "Colombia",    "stadium": "Seattle Stadium",              "city": "Seattle",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Colombia",    "predicted_score": "1-2"},
    # Quarter-finals
    {"date": "2026-07-09", "stage": "Quarter-final",       "team_a": "Brazil",        "team_b": "Germany",     "stadium": "Boston Stadium",               "city": "Boston",               "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Brazil",      "predicted_score": "2-1"},
    {"date": "2026-07-10", "stage": "Quarter-final",       "team_a": "France",        "team_b": "England",     "stadium": "Kansas City Stadium",          "city": "Kansas City",          "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "France",      "predicted_score": "2-1"},
    {"date": "2026-07-10", "stage": "Quarter-final",       "team_a": "Argentina",     "team_b": "Portugal",    "stadium": "Houston Stadium",              "city": "Houston",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Argentina",   "predicted_score": "2-1"},
    {"date": "2026-07-11", "stage": "Quarter-final",       "team_a": "Uruguay",       "team_b": "Colombia",    "stadium": "BC Place Vancouver",           "city": "Vancouver",            "country": "Canada", "status": "predicted", "is_prediction": True, "predicted_winner": "Uruguay",     "predicted_score": "1-0"},
    # Semi-finals
    {"date": "2026-07-14", "stage": "Semi-final",          "team_a": "Brazil",        "team_b": "France",      "stadium": "Dallas Stadium",               "city": "Dallas",               "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "France",      "predicted_score": "1-2"},
    {"date": "2026-07-15", "stage": "Semi-final",          "team_a": "Argentina",     "team_b": "Uruguay",     "stadium": "Atlanta Stadium",              "city": "Atlanta",              "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Argentina",   "predicted_score": "2-0"},
    # Third-place play-off + Final
    {"date": "2026-07-18", "stage": "Third-place play-off","team_a": "Brazil",        "team_b": "Uruguay",     "stadium": "Miami Stadium",                "city": "Miami",                "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Brazil",      "predicted_score": "2-1"},
    {"date": "2026-07-19", "stage": "Final",               "team_a": "France",        "team_b": "Argentina",   "stadium": "New York New Jersey Stadium",  "city": "New York New Jersey",  "country": "USA",    "status": "predicted", "is_prediction": True, "predicted_winner": "Argentina",   "predicted_score": "1-2"},
]

PREDICTED_TOURNAMENT_RESULT = {
    "champion": "Argentina",
    "runner_up": "France",
    "third_place": "Brazil",
    "fourth_place": "Uruguay",
    "final_date": "2026-07-19",
    "final_stadium": "New York New Jersey Stadium",
    "final_city": "New York New Jersey",
}

# Unified lookup: SCHEDULE + PREDICTED_KNOCKOUT_MATCHES indexed by date
_ALL_MATCHES = dict(SCHEDULE)
for _m in PREDICTED_KNOCKOUT_MATCHES:
    _d = _m["date"]
    if _d not in _ALL_MATCHES:
        _ALL_MATCHES[_d] = []
    _ALL_MATCHES[_d].append(_m)

SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8000"))


def write_service_log(request_id, client_country, entity_value, status_code, processing_time_ms):
    """
    TODO: Students must implement structured JSON Lines logging here.

    Required output file: data/service_logs/match_service.log

    Append one JSON object per request (one line per entry, no indentation).
    Required fields:
      timestamp           ISO-8601 UTC string, e.g. datetime.utcnow().isoformat() + "Z"
      request_id          value of X-Request-ID header  (passed as argument)
      client_country      value of X-Client-Country header  (passed as argument)
      service             "match-service"
      endpoint            "/api/matches"
      entity_type         "match_day"
      entity_value        the requested date string  (passed as argument)
      status_code         HTTP status code returned  (passed as argument)
      processing_time_ms  milliseconds elapsed since request start  (passed as argument)
      event_type          "match_lookup"
    """
    pass


def _apply_scenario(request: Request):
    """Shape the response based on X-Scenario. Returns a JSONResponse or None."""
    scenario = request.headers.get("x-scenario", "normal").lower()
    if scenario == "slow":
        time.sleep(random.uniform(0.4, 1.3))
    else:
        time.sleep(random.uniform(0.005, 0.05))
    if scenario == "server_error":
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "service": "match-service"},
        )
    return None


@app.get("/health")
def health():
    return {"status": "ok", "service": "match-service"}


@app.get("/api/matches")
def get_matches(request: Request, date: str = ""):
    started_at = time.perf_counter()
    request_id = request.headers.get("x-request-id", "")
    client_country = request.headers.get("x-client-country", "")

    forced = _apply_scenario(request)
    if forced is not None:
        write_service_log(request_id, client_country, date,
                          500, int((time.perf_counter() - started_at) * 1000))
        return forced

    if not date:
        write_service_log(request_id, client_country, "",
                          400, int((time.perf_counter() - started_at) * 1000))
        return JSONResponse(
            status_code=400,
            content={"error": "missing 'date' query parameter",
                     "example": "/api/matches?date=2026-06-25"},
        )

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        write_service_log(request_id, client_country, date,
                          400, int((time.perf_counter() - started_at) * 1000))
        return JSONResponse(
            status_code=400,
            content={"error": "invalid date format, expected YYYY-MM-DD", "received": date},
        )

    matches = _ALL_MATCHES.get(date)
    if not matches:
        write_service_log(request_id, client_country, date,
                          404, int((time.perf_counter() - started_at) * 1000))
        return JSONResponse(
            status_code=404,
            content={"error": "no matches found for this date", "date": date},
        )

    write_service_log(request_id, client_country, date,
                      200, int((time.perf_counter() - started_at) * 1000))
    return {"date": date, "count": len(matches), "matches": matches}
