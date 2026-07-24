# Phase 1 Implementation Plan

This plan is derived from `Cloud_Final_Project_Phase1.pdf` and the supplied
starter repository. Complete the steps in order because each step produces the
inputs required by later steps.

## Current baseline

The repository initially provides:

- FastAPI starter applications for match, team, and stadium lookups;
- in-memory World Cup datasets and basic success/error scenarios;
- TODO placeholders for structured service logging; and
- a sample Docker Compose environment for Hadoop NameNode and DataNode.

## Step 1 - Structure and conventions

Status: Complete.

- Create the planned directory skeleton.
- Fix service names, ports, paths, schemas, MapReduce key formats, default
  header behavior, tie-breaking rules, and output column order.
- Document the service-log `X-Scenario` compatibility decision.

Definition of done: `docs/conventions.md` is authoritative for subsequent
steps and every planned top-level work area exists.

## Step 2 - Backend structured logging

Status: Complete.

- Implement `write_service_log()` in all three services.
- Emit one JSON object per request to the service-specific JSON Lines file.
- Record success, validation, not-found, slow, and forced-error outcomes.
- Add tests for required fields, entity mapping, timing, and valid JSONL.

Definition of done: every API request produces exactly one correct service-log
record.

## Step 3 - Service containerization

Status: Implemented; image build and runtime verification require Docker.

- Add a dependency file and Dockerfile for each backend.
- Bind applications to `0.0.0.0:8000` inside their containers.
- Persist service logs through a shared host volume.
- Verify health endpoints and independent image builds.

Definition of done: all backend images build and run without host-specific
absolute paths.

## Step 4 - Nginx gateway

Status: Implemented; `nginx -t` and proxy runtime verification require Nginx
or Docker.

- Create a complete `nginx.conf` with upstreams and route-based proxying.
- Forward request ID, country, and scenario headers.
- Emit the mandatory JSON Lines gateway schema.
- Persist `data/nginx/nginx_access.log` and expose host port 8080.

Definition of done: all public requests pass through Nginx and correlate with
backend records by request ID.

## Step 5 - Application Docker Compose stack

Status: Implemented; Compose build and runtime verification require Docker.

- Create the root Compose file for the three backends and Nginx.
- Configure network, dependencies, health checks, ports, and log volumes.
- Validate `docker compose up --build` and `nginx -t`.

Definition of done: one command starts the complete API and gateway stack.

## Step 6 - Traffic generator

Status: Complete; live gateway execution requires the Docker stack.

- Implement `traffic-generator/generate.py` with request-count and Nginx URL
  arguments.
- Generate unique request IDs and varied countries, entities, and scenarios.
- Include normal, slow, invalid/4xx, forced/5xx, and deliberately unbalanced
  traffic.
- Add bounded concurrency, timeouts, a reproducible seed, and a run summary.
- Send traffic only through Nginx.

Definition of done: debug runs contain at least 1,000 requests and the final
run supports at least 100,000 meaningful requests.

## Step 7 - Source-log validation

Status: Validation and clean-run tooling complete; live debug-dataset
validation requires the Docker stack.

- Validate JSONL syntax and mandatory fields in both log families.
- Correlate gateway and backend entries and compare statuses.
- Confirm diversity across services, endpoints, countries, scenarios, entity
  values, errors, and response times.
- Document a safe clean-run procedure that does not delete an actively open
  Nginx log file.

Definition of done: a verified debug dataset is ready for Hadoop.

## Step 8 - Five Hadoop Streaming jobs

Status: Mapper/reducer implementations complete; Hadoop execution and host
output extraction are completed in Step 9.

### Job 1 - Parse and clean

- Parse gateway and service JSONL, validate fields and numeric values, convert
  gateway seconds to milliseconds, and separate invalid rows.
- Produce `cleaned_nginx_logs.csv`, `cleaned_service_logs.csv`, and
  `invalid_logs.csv` under `outputs/job1/`.

### Job 2 - General gateway aggregation

- Calculate service, endpoint, and scenario statistics, including response
  classes, error rate, and average response time.
- Produce the three CSV files under `outputs/job2/`.

### Job 3 - Country/entity counts

- Count requests by country for teams, match days, stadiums, and cities from
  cleaned service logs.
- Produce the three required CSV files under `outputs/job3/`.

### Job 4 - Popular entity by country

- Select the most requested team, match day, and stadium/city per country with
  deterministic tie-breaking.
- Produce the three required CSV files under `outputs/job4/`.

### Job 5 - Final report

- Combine Jobs 2-4 with prediction metadata.
- Produce `outputs/final/summary.json` with every required summary field.

Definition of done: all results originate from Hadoop Streaming mapper/reducer
executions rather than Pandas or a local-only replacement.

## Step 9 - MapReduce pipeline automation

Status: Complete; execution against the live Hadoop containers remains part of
the end-to-end verification step.

- Implement `scripts/run_mapreduce.sh`.
- Upload inputs to HDFS, clear previous HDFS outputs, execute Jobs 1-5 in
  order, retrieve part files, add CSV headers exactly once, and validate final
  artifacts.
- Make reruns safe and fail immediately on errors.

Definition of done: one script produces every intermediate output and the
final summary on the host.

## Step 10 - End-to-end testing

Status: Local deterministic end-to-end verification complete; clean container
build, live header-forwarding checks, and real Hadoop execution require Docker.

- Test APIs, header forwarding, both log schemas, malformed inputs, empty
  inputs, numeric aggregation, ties, and pipeline reruns.
- Compare small Hadoop results with hand-calculated fixtures.
- Perform a clean build and execution using only documented commands.

Definition of done: the complete mandatory system is reproducible from a clean
checkout.

## Step 11 - Final data run

Status: Guarded final-run automation and cross-artifact verification complete;
the genuine 100,000-request run requires a Docker-capable machine and must not
be replaced with synthetic submission artifacts.

- Safely clear previous runtime logs and start the stack.
- Generate at least 100,000 requests through Nginx.
- Run the Hadoop pipeline and verify the final summary against intermediate
  CSV files.
- Preserve the gateway log, all service logs, and all required outputs.

Definition of done: all submitted data artifacts come from the same verified
final run.

## Step 12 - Documentation and PDF report

Status: Complete documentation, report source, evidence checklist, and
visually verified draft PDF are implemented. Live screenshots, final-run
results, and team identification require the Docker run and student details.

- Complete the README with architecture, prerequisites, commands, output
  meanings, assumptions, and clean-rerun instructions.
- Capture evidence of containers, Nginx requests, both log families, traffic
  generation, Hadoop Streaming, intermediate files, and `summary.json`.
- Create and visually verify the required PDF report.

Definition of done: another person can run and explain the project from the
documentation and report.

## Step 13 - Submission package

- Check all required source, configuration, log, mapper/reducer, pipeline,
  output, and report files.
- Exclude caches, temporary files, secrets, and local Hadoop state.
- Perform one final clean execution and create
  `CC_Project_Phase1_StudentID1_StudentID2.zip` using the real student IDs.

Definition of done: the archive is complete, runnable, reproducible, and named
according to the specification.

## Optional Step 14 - Spark Structured Streaming

- Read newly created JSONL batch files with explicit schemas and checkpoints.
- Cast gateway request time to `double`.
- Produce live request count, error rate, busiest service/endpoint, popular
  team by country, and average response-time windows.
- Demonstrate updates as new files arrive and include evidence in the report.

Begin this optional step only after the mandatory pipeline passes end to end.
