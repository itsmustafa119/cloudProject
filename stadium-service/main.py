"""
stadium-service
===============
Returns information about a FIFA World Cup 2026 stadium or host city.

    GET /api/stadiums?name=New York New Jersey Stadium
    GET /api/stadiums?name=MetLife Stadium          (alias supported)
    GET /api/stadiums?city=New York New Jersey
    GET /api/stadiums?city=New York                 (city alias supported)

Phase 1 notes:
* No database. Stadiums live in an in-memory list.
* Each entry has a canonical `name` (city-based, e.g. "Dallas Stadium") and
  a `common_name` (the real venue name, e.g. "AT&T Stadium").
* This service must write a structured JSON Lines log to:
      data/service_logs/stadium_service.log
  Implement write_service_log() below to complete this requirement.
* entity_type depends on the query parameter used:
      name query  -> entity_type = "stadium",  entity_value = stadium name
      city query  -> entity_type = "city",     entity_value = city name
* Response shape can be influenced via the X-Scenario header:
      X-Scenario: slow         -> add extra latency
      X-Scenario: server_error -> return 500
"""
import os
import random
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="stadium-service")

# ---------------------------------------------------------------------------
# In-memory "database": all 16 official FIFA World Cup 2026 venues
# ---------------------------------------------------------------------------
STADIUMS = [
    {"name": "Atlanta Stadium",                "common_name": "Mercedes-Benz Stadium",  "city": "Atlanta",               "country": "USA",    "capacity": 68000},
    {"name": "Boston Stadium",                 "common_name": "Gillette Stadium",        "city": "Boston",                "country": "USA",    "capacity": 66000},
    {"name": "Dallas Stadium",                 "common_name": "AT&T Stadium",            "city": "Dallas",                "country": "USA",    "capacity": 94000},
    {"name": "Guadalajara Stadium",            "common_name": "Estadio Akron",           "city": "Guadalajara",           "country": "Mexico", "capacity": 46000},
    {"name": "Houston Stadium",                "common_name": "NRG Stadium",             "city": "Houston",               "country": "USA",    "capacity": 72000},
    {"name": "Kansas City Stadium",            "common_name": "Arrowhead Stadium",       "city": "Kansas City",           "country": "USA",    "capacity": 73500},
    {"name": "Los Angeles Stadium",            "common_name": "SoFi Stadium",            "city": "Los Angeles",           "country": "USA",    "capacity": 70000},
    {"name": "Mexico City Stadium",            "common_name": "Estadio Azteca",          "city": "Mexico City",           "country": "Mexico", "capacity": 87500},
    {"name": "Miami Stadium",                  "common_name": "Hard Rock Stadium",       "city": "Miami",                 "country": "USA",    "capacity": 65000},
    {"name": "Monterrey Stadium",              "common_name": "Estadio BBVA",            "city": "Monterrey",             "country": "Mexico", "capacity": 53500},
    {"name": "New York New Jersey Stadium",    "common_name": "MetLife Stadium",         "city": "New York New Jersey",   "country": "USA",    "capacity": 82500},
    {"name": "Philadelphia Stadium",           "common_name": "Lincoln Financial Field", "city": "Philadelphia",          "country": "USA",    "capacity": 69500},
    {"name": "San Francisco Bay Area Stadium", "common_name": "Levi's Stadium",          "city": "San Francisco Bay Area","country": "USA",    "capacity": 68500},
    {"name": "Seattle Stadium",                "common_name": "Lumen Field",             "city": "Seattle",               "country": "USA",    "capacity": 69000},
    {"name": "Toronto Stadium",                "common_name": "BMO Field",               "city": "Toronto",               "country": "Canada", "capacity": 45000},
    {"name": "BC Place Vancouver",             "common_name": "BC Place",                "city": "Vancouver",             "country": "Canada", "capacity": 54000},
]

# Primary lookup: canonical name -> stadium object
_BY_NAME = {s["name"].lower(): s for s in STADIUMS}

# Alias lookup: common name / old name -> canonical name
_ALIASES = {
    # Common aliases
    "vancouver stadium":        "BC Place Vancouver",
    "metlife stadium":          "New York New Jersey Stadium",
    "at&t stadium":             "Dallas Stadium",
    "sofi stadium":             "Los Angeles Stadium",
    "estadio azteca":           "Mexico City Stadium",
    # All common names for full backward compatibility
    "mercedes-benz stadium":    "Atlanta Stadium",
    "gillette stadium":         "Boston Stadium",
    "estadio akron":            "Guadalajara Stadium",
    "nrg stadium":              "Houston Stadium",
    "arrowhead stadium":        "Kansas City Stadium",
    "hard rock stadium":        "Miami Stadium",
    "estadio bbva":             "Monterrey Stadium",
    "lincoln financial field":  "Philadelphia Stadium",
    "levi's stadium":           "San Francisco Bay Area Stadium",
    "lumen field":              "Seattle Stadium",
    "bmo field":                "Toronto Stadium",
    "bc place":                 "BC Place Vancouver",
}

# City aliases: short / legacy city name -> canonical city name
_CITY_ALIASES = {
    "new york":      "New York New Jersey",
    "san francisco": "San Francisco Bay Area",
}

SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8000"))


def write_service_log(request_id, client_country, entity_type, entity_value, status_code, processing_time_ms):
    """
    TODO: Students must implement structured JSON Lines logging here.

    Required output file: data/service_logs/stadium_service.log

    Append one JSON object per request (one line per entry, no indentation).
    Required fields:
      timestamp           ISO-8601 UTC string, e.g. datetime.utcnow().isoformat() + "Z"
      request_id          value of X-Request-ID header  (passed as argument)
      client_country      value of X-Client-Country header  (passed as argument)
      service             "stadium-service"
      endpoint            "/api/stadiums"
      entity_type         "stadium" when querying by name, "city" when querying by city
                          (passed as argument — already determined for you)
      entity_value        the requested stadium name or city name  (passed as argument)
      status_code         HTTP status code returned  (passed as argument)
      processing_time_ms  milliseconds elapsed since request start  (passed as argument)
      event_type          "stadium_lookup"
    """
    pass


def _find_stadium(name: str):
    key = name.lower()
    s = _BY_NAME.get(key)
    if s:
        return s
    canonical = _ALIASES.get(key)
    if canonical:
        return _BY_NAME.get(canonical.lower())
    return None


def _find_by_city(city: str):
    canonical = _CITY_ALIASES.get(city.lower(), city)
    return [s for s in STADIUMS if s["city"].lower() == canonical.lower()]


def _apply_scenario(request: Request):
    """Shape the response based on X-Scenario. Returns a JSONResponse or None."""
    scenario = request.headers.get("x-scenario", "normal").lower()
    if scenario == "slow":
        time.sleep(random.uniform(0.5, 1.5))
    else:
        time.sleep(random.uniform(0.004, 0.05))
    if scenario == "server_error":
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "service": "stadium-service"},
        )
    return None


@app.get("/health")
def health():
    return {"status": "ok", "service": "stadium-service"}


@app.get("/api/stadiums")
def get_stadium(request: Request, name: str = "", city: str = ""):
    started_at = time.perf_counter()
    request_id = request.headers.get("x-request-id", "")
    client_country = request.headers.get("x-client-country", "")
    entity_type = "stadium" if name else "city"
    entity_value = name if name else city

    forced = _apply_scenario(request)
    if forced is not None:
        write_service_log(request_id, client_country, entity_type, entity_value,
                          500, int((time.perf_counter() - started_at) * 1000))
        return forced

    if not name and not city:
        write_service_log(request_id, client_country, "stadium", "",
                          400, int((time.perf_counter() - started_at) * 1000))
        return JSONResponse(
            status_code=400,
            content={"error": "provide either 'name' or 'city' query parameter",
                     "example": "/api/stadiums?name=New York New Jersey Stadium"},
        )

    if name:
        stadium = _find_stadium(name)
        if stadium is None:
            write_service_log(request_id, client_country, "stadium", name,
                              404, int((time.perf_counter() - started_at) * 1000))
            return JSONResponse(
                status_code=404,
                content={"error": "stadium not found", "name": name},
            )
        write_service_log(request_id, client_country, "stadium", name,
                          200, int((time.perf_counter() - started_at) * 1000))
        return stadium

    results = _find_by_city(city)
    if not results:
        write_service_log(request_id, client_country, "city", city,
                          404, int((time.perf_counter() - started_at) * 1000))
        return JSONResponse(
            status_code=404,
            content={"error": "city not found", "city": city},
        )
    write_service_log(request_id, client_country, "city", city,
                      200, int((time.perf_counter() - started_at) * 1000))
    return {"city": city, "count": len(results), "stadiums": results}
