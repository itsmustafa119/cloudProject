# World Cup Log Analytics with Nginx and Hadoop Streaming

## Report scope

This report describes the mandatory Phase 1 implementation: three FastAPI
services, an Nginx gateway, structured gateway and service logs, a concurrent
traffic generator, five Hadoop Streaming jobs, output validation, and
reproducible testing.

## Implementation summary

All public traffic enters through Nginx on host port 8080. Nginx routes each
request by exact API path, forwards correlation headers, and records a JSONL
gateway event. The selected backend records a second JSONL event with
entity-level fields. Hadoop Job 1 cleans both families. Jobs 2-4 calculate
gateway and entity statistics. Job 5 creates the required final JSON report.

## Verification status

The codebase has deterministic local end-to-end coverage and a guarded live
execution workflow. The live 100,000-request dataset, Docker screenshots, and
Hadoop screenshots must be generated on a Docker-capable machine before the
report is submitted. Fixture results are used only to test calculations.

## Reproduction

The authoritative build, run, validation, MapReduce, output inspection, and
clean-rerun commands are documented in the repository README. The final data
workflow is `bash scripts/run_final_data.sh --confirm-final-run`.
