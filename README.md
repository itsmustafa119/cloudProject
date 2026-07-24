# World Cup Log Analytics - Cloud Computing Phase 1

This project runs three World Cup information services behind an Nginx API
gateway, generates correlated traffic, stores structured JSON Lines logs, and
analyzes those logs with five Hadoop Streaming MapReduce jobs.

## Architecture

```text
traffic generator
       |
       v
Nginx gateway :8080  ---> data/nginx/nginx_access.log
       |
       +-- /api/matches  ---> match-service:8000
       +-- /api/teams    ---> team-service:8000
       +-- /api/stadiums ---> stadium-service:8000
                                   |
                                   v
                         data/service_logs/*.log

gateway + service logs
       |
       v
HDFS -> Job 1 -> Jobs 2 and 3 -> Job 4 -> Job 5
       |
       v
outputs/job1..job4 and outputs/final/summary.json
```

Only Nginx publishes a host port. The traffic generator never contacts a
backend directly. Nginx supplies effective values for `X-Request-ID`,
`X-Client-Country`, and `X-Scenario`, forwards them to the selected backend,
and records the same values in its gateway log.

## Prerequisites

- Docker Engine or Docker Desktop with Docker Compose v2
- Python 3.10 or newer
- Bash for the Hadoop and final-run scripts
- `curl` for optional manual API checks

No personal absolute paths are used by the containers. The application and
Hadoop Compose projects mount repository-relative data and output folders.

## Repository layout

| Path | Purpose |
| --- | --- |
| `match-service/`, `team-service/`, `stadium-service/` | FastAPI backends, dependencies, and Dockerfiles |
| `nginx/nginx.conf` | Gateway routing, forwarded headers, and JSONL access log |
| `traffic-generator/generate.py` | Reproducible concurrent gateway traffic |
| `mapreduce/` | Five mapper/reducer pairs and prediction metadata |
| `scripts/` | Log preparation, validation, pipeline, and verification tools |
| `data/nginx/` | Persisted Nginx gateway log |
| `data/service_logs/` | Persisted per-service logs |
| `outputs/` | Required intermediate CSV files and final JSON summary |
| `tests/fixtures/e2e/` | Small deterministic, hand-calculated test dataset |
| `docs/` | Conventions, implementation plan, report source, and evidence guide |

## Start and test the API stack

```bash
docker compose up --build -d
docker compose ps
docker compose exec nginx nginx -t
curl http://localhost:8080/health
```

Example request with all correlation headers:

```bash
curl -H "X-Request-ID: manual-001" \
  -H "X-Client-Country: Iran" \
  -H "X-Scenario: normal" \
  "http://localhost:8080/api/teams?name=Argentina"
```

Other public routes are:

- `GET /api/matches?date=2026-06-25`
- `GET /api/teams?name=Argentina`
- `GET /api/stadiums?name=New+York+New+Jersey+Stadium`
- `GET /api/stadiums?city=New+York`

Stop the application without deleting persisted logs:

```bash
docker compose down
```

## Structured logs

Nginx writes `data/nginx/nginx_access.log`. Each JSON object contains:

```text
timestamp, request_id, client_ip, client_country, scenario, method, path,
service, status_code, request_time_sec, user_agent
```

The three backends write individual files under `data/service_logs/`. Each
JSON object contains:

```text
timestamp, request_id, client_country, scenario, service, endpoint,
entity_type, entity_value, status_code, processing_time_ms, event_type
```

Both families use one complete JSON object per line. Request IDs correlate the
gateway record with exactly one backend record.

## Traffic generation and source validation

Generate the required debug dataset through Nginx:

```bash
python traffic-generator/generate.py \
  --requests 1000 \
  --nginx-url http://localhost:8080

python scripts/validate_logs.py --expected-min-requests 1000
```

The generator supports `--seed`, `--workers`, `--timeout`, and
`--progress-every`. Its weighted input includes all services, multiple
countries and entities, normal and slow requests, 4xx responses, and forced
5xx responses.

For a clean run, stop the stack before truncating the four known log files:

```bash
docker compose down
python scripts/prepare_clean_run.py --confirm-stack-stopped
docker compose up --build -d
```

The preparation tool truncates files in place and refuses to run without the
explicit stopped-stack confirmation.

## Hadoop Streaming pipeline

Start Hadoop and execute the complete pipeline from the NameNode:

```bash
docker compose -f hadoop/docker-compose.yml up -d
docker compose -f hadoop/docker-compose.yml exec namenode bash
bash /project/scripts/run_mapreduce.sh
```

The pipeline uses one reducer per job so each tagged result set is
deterministic:

1. Job 1 parses both schemas, converts Nginx seconds to milliseconds, and
   separates invalid rows.
2. Job 2 calculates service, endpoint, and scenario request/error/time metrics
   from cleaned Nginx logs.
3. Job 3 counts team, match-day, stadium, and city requests by country from
   cleaned backend logs.
4. Job 4 selects each country's most popular entity with lexical tie-breaking.
5. Job 5 combines Jobs 2-4 with prediction metadata into the final summary.

`scripts/run_mapreduce.sh` uploads inputs to `/phase1` in HDFS, removes only
the previous `/phase1` job inputs and outputs, retrieves all part files, and
materializes the required host artifacts.

## Outputs

| Job | Artifacts |
| --- | --- |
| Job 1 | `cleaned_nginx_logs.csv`, `cleaned_service_logs.csv`, `invalid_logs.csv` |
| Job 2 | `service_stats.csv`, `endpoint_stats.csv`, `scenario_stats.csv` |
| Job 3 | `country_team_requests.csv`, `country_matchday_requests.csv`, `country_stadium_requests.csv` |
| Job 4 | `popular_team_by_country.csv`, `popular_matchday_by_country.csv`, `popular_stadium_by_country.csv` |
| Final | `outputs/final/summary.json` |

The final summary reports the total request count, most requested and
highest-error services, slowest endpoint, overall popular entities, popular
team by country, and the supplied prediction fields.

Serve the repository for quick browser inspection:

```bash
python -m http.server 9000
```

Then open `http://localhost:9000/outputs/final/summary.json`.

## Verification

Run the complete local test suite:

```bash
python -m unittest discover -s tests -v
```

Run the deterministic five-job fixture:

```bash
python scripts/verify_local_e2e.py
```

This simulates Hadoop's shuffle/sort, compares the results with
hand-calculated expectations, and materializes all 13 required artifacts in a
temporary directory. To inspect repeatable fixture outputs:

```bash
python scripts/verify_local_e2e.py --output-root outputs/e2e-test
python scripts/verify_local_e2e.py --output-root outputs/e2e-test
```

Fixture outputs are test data and must not be submitted as the final dataset.

## Final data run

On a Docker-capable machine, run the guarded workflow:

```bash
bash scripts/run_final_data.sh --confirm-final-run
```

This performs a clean build, generates at least 100,000 requests through
Nginx, validates request-level log correlation, executes Jobs 1-5, and checks
the final summary against every intermediate CSV:

```bash
python scripts/verify_final_artifacts.py --expected-min-requests 100000
```

The final source logs and outputs must all come from this same run. The script
leaves them in place for report evidence.

## Assumptions and deterministic rules

- Missing request IDs are replaced by Nginx's generated `$request_id`.
- Missing countries default to `Unknown`; missing scenarios default to
  `normal`.
- Backends normalize scenario text before logging.
- Gateway times are seconds stored as strings; Job 1 converts them to
  milliseconds.
- Service processing times are nonnegative numeric milliseconds.
- Popularity and maximum-metric ties use case-insensitive lexical order, then
  original text order.
- Stadium popularity uses `entity_type=stadium`; city requests remain
  available in the country/entity outputs.
- Spark Structured Streaming is optional and is not part of the mandatory
  implementation.

## Report and submission

Build the report PDF:

```bash
python scripts/build_report.py
```

Before submission, complete the live run and evidence checklist in
`docs/report-evidence-checklist.md`, rebuild the report, and package the
repository using the real student IDs.
