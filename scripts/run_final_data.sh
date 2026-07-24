#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm-final-run" ]]; then
    echo "ERROR: pass --confirm-final-run to replace runtime logs and outputs" >&2
    exit 2
fi

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="${SCRIPT_PATH%/*}"
if [[ "$SCRIPT_DIR" == "$SCRIPT_PATH" ]]; then
    SCRIPT_DIR="."
fi
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUEST_COUNT="${REQUEST_COUNT:-100000}"
NGINX_URL="${NGINX_URL:-http://localhost:8080}"

if ! [[ "$REQUEST_COUNT" =~ ^[0-9]+$ ]] || (( REQUEST_COUNT < 100000 )); then
    echo "ERROR: REQUEST_COUNT must be an integer of at least 100000" >&2
    exit 2
fi
for command_name in docker python; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "ERROR: required command is unavailable: $command_name" >&2
        exit 1
    fi
done
if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose v2 is required" >&2
    exit 1
fi

cd "$PROJECT_ROOT"

echo "[1/8] Stopping the application stack"
docker compose down

echo "[2/8] Truncating only the four known runtime logs"
python scripts/prepare_clean_run.py --confirm-stack-stopped

echo "[3/8] Building and starting the application stack"
docker compose up --build -d --wait --wait-timeout 180
docker compose exec -T nginx nginx -t

echo "[4/8] Confirming the Nginx gateway is reachable"
python -c 'import sys, urllib.request; response = urllib.request.urlopen(sys.argv[1] + "/health", timeout=10); assert response.status == 200' "$NGINX_URL"

echo "[5/8] Generating ${REQUEST_COUNT} requests through Nginx"
python traffic-generator/generate.py \
    --requests "$REQUEST_COUNT" \
    --nginx-url "$NGINX_URL"

echo "[6/8] Validating the final correlated source logs"
python scripts/validate_logs.py --expected-min-requests "$REQUEST_COUNT"

echo "[7/8] Starting Hadoop and executing all five Streaming jobs"
docker compose -f hadoop/docker-compose.yml up -d
for attempt in $(seq 1 60); do
    if docker compose -f hadoop/docker-compose.yml exec -T namenode \
        hdfs dfs -ls / >/dev/null 2>&1; then
        break
    fi
    if (( attempt == 60 )); then
        echo "ERROR: HDFS did not become ready within 120 seconds" >&2
        exit 1
    fi
    sleep 2
done
docker compose -f hadoop/docker-compose.yml exec -T namenode \
    bash /project/scripts/run_mapreduce.sh

echo "[8/8] Cross-checking final and intermediate artifacts"
python scripts/verify_final_artifacts.py \
    --expected-min-requests "$REQUEST_COUNT"

echo "FINAL DATA RUN PASSED"
echo "Runtime logs and analytical outputs have been preserved in data/ and outputs/."
