"""
team-service
============
Returns information about a FIFA World Cup 2026 national team.

    GET /api/teams?name=Argentina

Phase 1 notes:
* No database. Teams live in an in-memory dictionary.
* This service writes a structured JSON Lines log to:
      data/service_logs/team_service.log
* Response shape can be influenced via the X-Scenario header:
      X-Scenario: slow         -> add extra latency
      X-Scenario: server_error -> return 500
"""
import json
import os
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="team-service")

# ---------------------------------------------------------------------------
# In-memory "database": team name -> info
# Dataset covers group-stage and all predicted knockout matches.
# ---------------------------------------------------------------------------
TEAMS = {
    # CONMEBOL
    "Argentina":      {"country_code": "ARG", "confederation": "CONMEBOL"},
    "Brazil":         {"country_code": "BRA", "confederation": "CONMEBOL"},
    "Uruguay":        {"country_code": "URU", "confederation": "CONMEBOL"},
    "Colombia":       {"country_code": "COL", "confederation": "CONMEBOL"},
    "Ecuador":        {"country_code": "ECU", "confederation": "CONMEBOL"},
    "Paraguay":       {"country_code": "PAR", "confederation": "CONMEBOL"},
    # CONCACAF (hosts + others)
    "USA":            {"country_code": "USA", "confederation": "CONCACAF"},
    "United States":  {"country_code": "USA", "confederation": "CONCACAF"},
    "Mexico":         {"country_code": "MEX", "confederation": "CONCACAF"},
    "Canada":         {"country_code": "CAN", "confederation": "CONCACAF"},
    # UEFA
    "France":         {"country_code": "FRA", "confederation": "UEFA"},
    "Germany":        {"country_code": "GER", "confederation": "UEFA"},
    "Spain":          {"country_code": "ESP", "confederation": "UEFA"},
    "England":        {"country_code": "ENG", "confederation": "UEFA"},
    "Portugal":       {"country_code": "POR", "confederation": "UEFA"},
    "Netherlands":    {"country_code": "NED", "confederation": "UEFA"},
    "Belgium":        {"country_code": "BEL", "confederation": "UEFA"},
    "Croatia":        {"country_code": "CRO", "confederation": "UEFA"},
    "Italy":          {"country_code": "ITA", "confederation": "UEFA"},
    "Serbia":         {"country_code": "SRB", "confederation": "UEFA"},
    "Denmark":        {"country_code": "DEN", "confederation": "UEFA"},
    "Switzerland":    {"country_code": "SUI", "confederation": "UEFA"},
    "Austria":        {"country_code": "AUT", "confederation": "UEFA"},
    "Norway":         {"country_code": "NOR", "confederation": "UEFA"},
    "Sweden":         {"country_code": "SWE", "confederation": "UEFA"},
    # AFC
    "Japan":          {"country_code": "JPN", "confederation": "AFC"},
    "South Korea":    {"country_code": "KOR", "confederation": "AFC"},
    "Australia":      {"country_code": "AUS", "confederation": "AFC"},
    "Saudi Arabia":   {"country_code": "KSA", "confederation": "AFC"},
    "Iran":           {"country_code": "IRN", "confederation": "AFC"},
    # CAF
    "Morocco":        {"country_code": "MAR", "confederation": "CAF"},
    "Senegal":        {"country_code": "SEN", "confederation": "CAF"},
    "Nigeria":        {"country_code": "NGA", "confederation": "CAF"},
    "South Africa":   {"country_code": "RSA", "confederation": "CAF"},
    "Ivory Coast":    {"country_code": "CIV", "confederation": "CAF"},
    "Ghana":          {"country_code": "GHA", "confederation": "CAF"},
    "Algeria":        {"country_code": "ALG", "confederation": "CAF"},
    "Tunisia":        {"country_code": "TUN", "confederation": "CAF"},
    "Egypt":          {"country_code": "EGY", "confederation": "CAF"},
}

SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8000"))
_DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "service_logs"
_LOG_LOCK = threading.Lock()


def _scenario_from_request(request: Request):
    """Return the normalized scenario forwarded by the gateway."""
    return (request.headers.get("x-scenario", "normal").strip().lower()
            or "normal")


def _service_log_path():
    """Resolve the host/project log directory, with a container override."""
    configured_dir = os.environ.get("SERVICE_LOG_DIR")
    log_dir = Path(configured_dir) if configured_dir else _DEFAULT_LOG_DIR
    return log_dir / "team_service.log"


def write_service_log(request_id, client_country, scenario, entity_value,
                      status_code, processing_time_ms):
    """
    Write one structured JSON Lines record for a completed lookup request.

    Required output file: data/service_logs/team_service.log

    Append one JSON object per request (one line per entry, no indentation).
    Required fields:
      timestamp           ISO-8601 UTC string, e.g. datetime.utcnow().isoformat() + "Z"
      request_id          value of X-Request-ID header  (passed as argument)
      client_country      value of X-Client-Country header  (passed as argument)
      scenario            normalized value of X-Scenario (schema extension)
      service             "team-service"
      endpoint            "/api/teams"
      entity_type         "team"
      entity_value        the requested team name  (passed as argument)
      status_code         HTTP status code returned  (passed as argument)
      processing_time_ms  milliseconds elapsed since request start  (passed as argument)
      event_type          "team_lookup"
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request_id": request_id,
        "client_country": client_country,
        "scenario": scenario,
        "service": "team-service",
        "endpoint": "/api/teams",
        "entity_type": "team",
        "entity_value": entity_value,
        "status_code": int(status_code),
        "processing_time_ms": max(0, int(processing_time_ms)),
        "event_type": "team_lookup",
    }
    log_path = _service_log_path()
    encoded_record = json.dumps(
        record, ensure_ascii=False, separators=(",", ":")
    )

    with _LOG_LOCK:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(encoded_record + "\n")


def _apply_scenario(request: Request):
    """Shape the response based on X-Scenario. Returns a JSONResponse or None."""
    scenario = _scenario_from_request(request)
    if scenario == "slow":
        time.sleep(random.uniform(0.3, 1.1))
    else:
        time.sleep(random.uniform(0.003, 0.04))
    if scenario == "server_error":
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "service": "team-service"},
        )
    return None


@app.get("/health")
def health():
    return {"status": "ok", "service": "team-service"}


@app.get("/api/teams")
def get_team(request: Request, name: str = ""):
    started_at = time.perf_counter()
    request_id = request.headers.get("x-request-id", "")
    client_country = request.headers.get("x-client-country", "")
    scenario = _scenario_from_request(request)

    forced = _apply_scenario(request)
    if forced is not None:
        write_service_log(request_id, client_country, scenario, name,
                          500, int((time.perf_counter() - started_at) * 1000))
        return forced

    if not name:
        write_service_log(request_id, client_country, scenario, "",
                          400, int((time.perf_counter() - started_at) * 1000))
        return JSONResponse(
            status_code=400,
            content={"error": "missing 'name' query parameter",
                     "example": "/api/teams?name=Argentina"},
        )

    for team_name, info in TEAMS.items():
        if team_name.lower() == name.lower():
            result = {"name": team_name}
            result.update(info)
            write_service_log(request_id, client_country, scenario, team_name,
                              200, int((time.perf_counter() - started_at) * 1000))
            return result

    write_service_log(request_id, client_country, scenario, name,
                      404, int((time.perf_counter() - started_at) * 1000))
    return JSONResponse(
        status_code=404,
        content={"error": "team not found", "name": name},
    )
