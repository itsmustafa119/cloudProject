# World Cup Log Analytics - Phase 1

This repository contains the starter code and implementation workspace for the
Cloud Computing final project, Phase 1.

Project planning and conventions are documented before implementation begins:

- [Implementation plan](docs/implementation-plan.md)
- [Architecture and data conventions](docs/conventions.md)

Steps 1 and 2 are complete, and Steps 3-6 implement the service containers,
Nginx gateway, application Compose stack, and traffic generator. Real container
builds and live traffic checks still need to run on a machine with Docker
installed. MapReduce jobs, generated outputs, and the optional Spark extension
are implemented in later steps.

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
