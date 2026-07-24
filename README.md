# World Cup Log Analytics - Phase 1

This repository contains the starter code and implementation workspace for the
Cloud Computing final project, Phase 1.

Project planning and conventions are documented before implementation begins:

- [Implementation plan](docs/implementation-plan.md)
- [Architecture and data conventions](docs/conventions.md)

Steps 1 and 2 are complete, and Steps 3-6 implement the service containers,
Nginx gateway, application Compose stack, and traffic generator. Real container
builds and live traffic checks still need to run on a machine with Docker
installed. The five MapReduce mapper/reducer stages are implemented; Hadoop
execution automation, generated outputs, and the optional Spark extension are
implemented in later steps.

## Current verification

Run the structured-logging unit tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

Build the backend images from the repository root:

```bash
docker build -t phase1-match-service ./match-service
docker build -t phase1-team-service ./team-service
docker build -t phase1-stadium-service ./stadium-service
```

Start and verify the complete application stack:

```bash
docker compose up --build -d
docker compose ps
docker compose exec nginx nginx -t
curl http://localhost:8080/health
```

Stop the application stack without deleting the persisted host logs:

```bash
docker compose down
```

Generate the required debug traffic through Nginx:

```bash
python traffic-generator/generate.py --requests 1000 --nginx-url http://localhost:8080
```

After debug verification, generate the final dataset:

```bash
python traffic-generator/generate.py --requests 100000 --nginx-url http://localhost:8080
```

Use `--seed`, `--workers`, `--timeout`, and `--progress-every` to control a
run. The generator prints an in-memory execution summary; it does not create a
trace file, and MapReduce must use Nginx and service logs as its inputs.

Prepare a clean run by stopping the stack and truncating the known logs in
place. The explicit confirmation flag prevents accidental modification while
containers may still be writing:

```bash
docker compose down
python scripts/prepare_clean_run.py --confirm-stack-stopped
docker compose up --build -d
```

After generating the 1,000-request debug dataset, validate both log families
and their request-level correlation:

```bash
python scripts/validate_logs.py --expected-min-requests 1000
```

For the final dataset, repeat validation with
`--expected-min-requests 100000` before starting MapReduce.

Start the supplied Hadoop environment, enter the NameNode, and execute the
complete five-job pipeline:

```bash
docker compose -f hadoop/docker-compose.yml up -d
docker compose -f hadoop/docker-compose.yml exec namenode bash
bash /project/scripts/run_mapreduce.sh
```

The pipeline uploads the four source logs to HDFS, runs all five Hadoop
Streaming jobs, and writes every required CSV plus
`outputs/final/summary.json` back to the host-mounted repository.

Run the deterministic end-to-end fixture before using the large live dataset:

```bash
python scripts/verify_local_e2e.py
```

This command executes all five mapper/reducer pairs with a local Hadoop
shuffle/sort simulation, checks numeric aggregation and deterministic tie
breaking against hand-calculated expectations, and verifies all 13 output
artifacts. To inspect the generated fixture artifacts or test a safe rerun:

```bash
python scripts/verify_local_e2e.py --output-root outputs/e2e-test
python scripts/verify_local_e2e.py --output-root outputs/e2e-test
```

The local verifier supplements, but does not replace, the documented clean
Docker build, live Nginx header-forwarding check, and Hadoop-container run.

## Final data run

On a machine with Docker and Docker Compose v2, execute the guarded final run:

```bash
bash scripts/run_final_data.sh --confirm-final-run
```

The explicit confirmation is required because this run stops the application
stack and truncates the four known runtime logs. It then performs a clean
application build, generates 100,000 requests through Nginx, validates
request-level correlation, executes Hadoop Jobs 1-5, and cross-checks
`summary.json` against every intermediate CSV. It leaves the containers,
source logs, and analytical outputs in place for report evidence.

Do not commit or submit fixture-generated data as the final dataset. The final
logs and outputs must be created together by the guarded Docker run.
