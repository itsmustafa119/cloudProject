# Architecture and Data Conventions

This document fixes the contracts used by all later implementation steps.
Changing one of these contracts requires updating every affected producer,
consumer, test, and document.

## Components and ports

| Component | Compose service name | Container port | Host port |
|---|---|---:|---:|
| Match API | `match-service` | 8000 | none |
| Team API | `team-service` | 8000 | none |
| Stadium API | `stadium-service` | 8000 | none |
| Nginx gateway | `nginx` | 80 | 8080 |
| Hadoop NameNode UI | `namenode` | 9870 | 9870 |
| Hadoop DataNode UI | `datanode` | 9864 | 9864 |

Backend ports remain private to the Compose network. Tests and the traffic
generator must use `http://localhost:8080` rather than a backend address.

## Gateway routes

| Public route | Target service | Service endpoint |
|---|---|---|
| `/api/matches` | `match-service` | `/api/matches` |
| `/api/teams` | `team-service` | `/api/teams` |
| `/api/stadiums` | `stadium-service` | `/api/stadiums` |

## Request-header behavior

Nginx forwards these effective values to the selected backend:

- `X-Request-ID`: preserve a nonempty client value; otherwise use Nginx's
  generated request ID.
- `X-Client-Country`: preserve a nonempty client value; otherwise use
  `Unknown`.
- `X-Scenario`: canonicalize the supported values `normal`, `slow`, and
  `server_error` case-insensitively; default an empty value to `normal`.
  Unknown nonempty values remain visible in the gateway log and are normalized
  by the backend service.

The effective values, not blank originals, are written to the gateway and
service logs. Supported traffic scenarios are `normal`, `slow`, and
`server_error`. Unknown values may behave as normal traffic but remain visible
in the gateway log for analysis.

## Runtime paths

All paths below are relative to the repository root on the host and appear
under `/project` in the Hadoop NameNode container.

| Purpose | Host path |
|---|---|
| Gateway log | `data/nginx/nginx_access.log` |
| Match log | `data/service_logs/match_service.log` |
| Team log | `data/service_logs/team_service.log` |
| Stadium log | `data/service_logs/stadium_service.log` |
| MapReduce source | `mapreduce/` |
| Pipeline scripts | `scripts/` |
| Local results | `outputs/` |

Backend services resolve the default log directory from the repository layout.
`SERVICE_LOG_DIR` may override that directory at runtime, which allows a later
container to mount the same shared log location without embedding a path from a
developer's machine.

Log producers append UTF-8 JSON Lines: one compact JSON object and one newline
per request. Timestamps use UTC ISO-8601 with a `Z` suffix. Status and timing
values are numeric, not strings, except raw Nginx `request_time_sec`, which the
specification requires as a string.

## Raw Nginx schema

The field order is stable for readability, although consumers must parse by
name:

```text
timestamp, request_id, client_ip, client_country, scenario, method, path,
service, status_code, request_time_sec, user_agent
```

`path` includes the query string. `service` is one of the three Compose service
names or `unknown` for an unmatched route.

## Raw service schema

```text
timestamp, request_id, client_country, scenario, service, endpoint,
entity_type, entity_value, status_code, processing_time_ms, event_type
```

The PDF's mandatory service schema does not list `scenario`, while another
requirement says the service must use `X-Scenario` in its structured record.
The project therefore includes `scenario` as a backward-compatible extension.
All fields explicitly required by the PDF remain present.

Entity and event mappings are fixed:

| Service | Entity type | Event type |
|---|---|---|
| `match-service` | `match_day` | `match_lookup` |
| `team-service` | `team` | `team_lookup` |
| `stadium-service` name query | `stadium` | `stadium_lookup` |
| `stadium-service` city query | `city` | `stadium_lookup` |

Every completed API request writes exactly one service record, including 400,
404, and 500 responses. Health checks are operational records and are excluded
from the analytical service-log files.

## Cleaned output schemas

CSV files are UTF-8, comma-delimited, RFC 4180 quoted when necessary, and have
exactly one header row.

### Job 1

`cleaned_nginx_logs.csv`:

```text
timestamp,request_id,client_country,scenario,service,method,path,status_code,request_time_ms,user_agent
```

`cleaned_service_logs.csv`:

```text
timestamp,request_id,client_country,service,endpoint,entity_type,entity_value,status_code,processing_time_ms,event_type
```

The cleaned service schema intentionally matches the PDF's required columns;
the raw `scenario` extension is not needed by downstream service analytics.

`invalid_logs.csv`:

```text
source,error,raw_line
```

### Job 2

`service_stats.csv`:

```text
service,total_requests,success_count,client_error_count,server_error_count,error_count,error_rate,avg_response_time_ms
```

`endpoint_stats.csv`:

```text
service,endpoint,total_requests,success_count,client_error_count,server_error_count,error_count,error_rate,avg_response_time_ms
```

`scenario_stats.csv`:

```text
scenario,total_requests,success_count,client_error_count,server_error_count,error_count,error_rate,avg_response_time_ms
```

Success means status 200-399. Client errors are 400-499, server errors are
500-599, and `error_count` is their sum. Error rate is
`error_count / total_requests`, represented as a decimal rounded to six places.
Average times are milliseconds rounded to three places. Endpoints are obtained
by removing the query string from the gateway `path`.

### Job 3

```text
country_team_requests.csv: country,team,total_requests
country_matchday_requests.csv: country,match_day,total_requests
country_stadium_requests.csv: country,entity_type,entity_value,total_requests
```

Keeping `entity_type` in the stadium output prevents city searches from being
mistaken for stadium-name searches.

Job 3 counts every structurally valid cleaned service record, regardless of
whether its response was successful or an error. This follows the PDF's
request-count wording; status-based analysis belongs to Job 2. The traffic
generator must therefore keep invalid entity requests at a low enough weight
that they do not accidentally dominate popularity results.

### Job 4

```text
popular_team_by_country.csv: country,popular_team,total_requests
popular_matchday_by_country.csv: country,popular_match_day,total_requests
popular_stadium_by_country.csv: country,entity_type,popular_entity,total_requests
```

### Job 5

`outputs/final/summary.json` contains:

```text
total_requests
most_requested_service
highest_error_rate_service
slowest_endpoint
most_popular_team_overall
most_requested_match_day_overall
most_requested_stadium_overall
popular_team_by_country
predicted_champion
predicted_final
predicted_final_winner
predicted_final_stadium
```

`total_requests`, service error rate, and slowest endpoint come from Job 2.
Overall team and match-day values come from Job 3. The overall stadium value
uses only Job 3 rows whose `entity_type` is `stadium`; city rows do not compete
for `most_requested_stadium_overall`. Prediction fields come from a small,
versioned metadata input derived from the supplied match-service starter data.

## Hadoop Streaming record convention

Mapper output uses one tab to separate key and value:

```text
<compact JSON array key>\t<compact JSON value>
```

For example, Job 3 emits:

```text
["Iran","team-service","team","Argentina"]\t1
```

JSON arrays prevent spaces, commas, tabs, quotes, and multiword entity names
from corrupting compound keys. Programs write diagnostics only to stderr;
stdout is reserved for Hadoop records.

## Deterministic selection rules

For every maximum/minimum selection:

1. Select the best numeric value required by the metric.
2. On a tie, compare the candidate name case-insensitively in ascending order.
3. If still tied, compare the original UTF-8 string in ascending order.

This rule applies to popular entities, most-requested service, highest error
rate, and slowest endpoint. Empty datasets return `null` in JSON and only the
header in CSV rather than inventing a winner.

## Final-run policy

- Debug dataset: at least 1,000 Nginx requests.
- Submission dataset: at least 100,000 Nginx requests.
- Source analytics only from Nginx and backend service logs.
- Generator trace/debug files are never MapReduce inputs.
- Final logs and all final outputs must come from the same clean run.
