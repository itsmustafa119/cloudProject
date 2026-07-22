# World Cup Log Analytics - Phase 1

This repository contains the starter code and implementation workspace for the
Cloud Computing final project, Phase 1.

Project planning and conventions are documented before implementation begins:

- [Implementation plan](docs/implementation-plan.md)
- [Architecture and data conventions](docs/conventions.md)

Steps 1 and 2 are complete, and the Step 3 service containers, Step 4 Nginx
gateway, and Step 5 application Compose stack are implemented. Real container
builds and runtime checks still need to run on a machine with Docker installed.
Traffic generation, MapReduce jobs, generated outputs, and the optional Spark
extension are implemented in later steps.

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
