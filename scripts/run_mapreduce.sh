#!/usr/bin/env bash
set -euo pipefail

# Run this script inside the Hadoop NameNode container. The supplied Hadoop
# Compose file mounts the repository at /project.
PROJECT_ROOT="${PROJECT_ROOT:-/project}"
STREAMING_JAR="${HADOOP_STREAMING_JAR:-/opt/hadoop-3.2.1/share/hadoop/tools/lib/hadoop-streaming-3.2.1.jar}"
HDFS_ROOT="${HDFS_ROOT:-/phase1}"
HDFS_INPUT="${HDFS_ROOT}/input"
HDFS_OUTPUT="${HDFS_ROOT}/output"
LOCAL_OUTPUT="${PROJECT_ROOT}/outputs"

export PYTHONIOENCODING="UTF-8"

require_file() {
  local path="$1"
  if [[ ! -s "$path" ]]; then
    echo "ERROR: required nonempty file not found: $path" >&2
    exit 1
  fi
}

run_streaming() {
  local job_name="$1"
  local files="$2"
  local mapper="$3"
  local reducer="$4"
  local input_path="$5"
  local output_path="$6"

  echo "Running ${job_name}..."
  hdfs dfs -rm -r -f "$output_path" >/dev/null 2>&1 || true
  hadoop jar "$STREAMING_JAR" \
    -D "mapreduce.job.name=${job_name}" \
    -D mapreduce.job.reduces=1 \
    -D mapreduce.input.fileinputformat.input.dir.recursive=true \
    -files "$files" \
    -mapper "$mapper" \
    -reducer "$reducer" \
    -input "$input_path" \
    -output "$output_path"
}

command -v hdfs >/dev/null 2>&1 || {
  echo "ERROR: hdfs command is unavailable" >&2
  exit 1
}
command -v hadoop >/dev/null 2>&1 || {
  echo "ERROR: hadoop command is unavailable" >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 command is unavailable" >&2
  exit 1
}

require_file "$STREAMING_JAR"
require_file "${PROJECT_ROOT}/data/nginx/nginx_access.log"
require_file "${PROJECT_ROOT}/data/service_logs/match_service.log"
require_file "${PROJECT_ROOT}/data/service_logs/team_service.log"
require_file "${PROJECT_ROOT}/data/service_logs/stadium_service.log"

echo "Preparing isolated HDFS namespace at ${HDFS_ROOT}..."
hdfs dfs -rm -r -f "$HDFS_INPUT" >/dev/null 2>&1 || true
hdfs dfs -mkdir -p "${HDFS_INPUT}/service_logs"
hdfs dfs -put -f \
  "${PROJECT_ROOT}/data/nginx/nginx_access.log" \
  "${HDFS_INPUT}/nginx_access.log"
hdfs dfs -put -f \
  "${PROJECT_ROOT}/data/service_logs/match_service.log" \
  "${HDFS_INPUT}/service_logs/match_service.log"
hdfs dfs -put -f \
  "${PROJECT_ROOT}/data/service_logs/team_service.log" \
  "${HDFS_INPUT}/service_logs/team_service.log"
hdfs dfs -put -f \
  "${PROJECT_ROOT}/data/service_logs/stadium_service.log" \
  "${HDFS_INPUT}/service_logs/stadium_service.log"

JOB1_DIR="${PROJECT_ROOT}/mapreduce/job1_parse_clean"
JOB2_DIR="${PROJECT_ROOT}/mapreduce/job2_nginx_aggregation"
JOB3_DIR="${PROJECT_ROOT}/mapreduce/job3_country_entity"
JOB4_DIR="${PROJECT_ROOT}/mapreduce/job4_popular_entity"
JOB5_DIR="${PROJECT_ROOT}/mapreduce/job5_final_report"

run_streaming \
  "phase1-job1-parse-clean" \
  "${JOB1_DIR}/mapper.py,${JOB1_DIR}/reducer.py" \
  "python3 mapper.py" \
  "python3 reducer.py" \
  "$HDFS_INPUT" \
  "${HDFS_OUTPUT}/job1"

run_streaming \
  "phase1-job2-nginx-aggregation" \
  "${JOB2_DIR}/mapper.py,${JOB2_DIR}/reducer.py" \
  "python3 mapper.py" \
  "python3 reducer.py" \
  "${HDFS_OUTPUT}/job1" \
  "${HDFS_OUTPUT}/job2"

run_streaming \
  "phase1-job3-country-entity" \
  "${JOB3_DIR}/mapper.py,${JOB3_DIR}/reducer.py" \
  "python3 mapper.py" \
  "python3 reducer.py" \
  "${HDFS_OUTPUT}/job1" \
  "${HDFS_OUTPUT}/job3"

run_streaming \
  "phase1-job4-popular-entity" \
  "${JOB4_DIR}/mapper.py,${JOB4_DIR}/reducer.py" \
  "python3 mapper.py" \
  "python3 reducer.py" \
  "${HDFS_OUTPUT}/job3" \
  "${HDFS_OUTPUT}/job4"

# Job 5 consumes all general, entity-count, and country-popularity outputs.
echo "Running phase1-job5-final-report..."
hdfs dfs -rm -r -f "${HDFS_OUTPUT}/job5" >/dev/null 2>&1 || true
hadoop jar "$STREAMING_JAR" \
  -D mapreduce.job.name=phase1-job5-final-report \
  -D mapreduce.job.reduces=1 \
  -D mapreduce.input.fileinputformat.input.dir.recursive=true \
  -files "${JOB5_DIR}/mapper.py,${JOB5_DIR}/reducer.py,${JOB5_DIR}/predictions.json" \
  -mapper "python3 mapper.py" \
  -reducer "python3 reducer.py" \
  -input "${HDFS_OUTPUT}/job2" \
  -input "${HDFS_OUTPUT}/job3" \
  -input "${HDFS_OUTPUT}/job4" \
  -output "${HDFS_OUTPUT}/job5"

RAW_DIR="$(mktemp -d /tmp/phase1-mapreduce.XXXXXX)"
trap 'rm -rf "$RAW_DIR"' EXIT

echo "Retrieving Hadoop part files..."
for job_number in 1 2 3 4 5; do
  hdfs dfs -getmerge \
    "${HDFS_OUTPUT}/job${job_number}/part-*" \
    "${RAW_DIR}/job${job_number}.txt"
done

echo "Materializing required host outputs..."
python3 "${PROJECT_ROOT}/scripts/materialize_mapreduce_outputs.py" \
  --job1 "${RAW_DIR}/job1.txt" \
  --job2 "${RAW_DIR}/job2.txt" \
  --job3 "${RAW_DIR}/job3.txt" \
  --job4 "${RAW_DIR}/job4.txt" \
  --job5 "${RAW_DIR}/job5.txt" \
  --output-root "$LOCAL_OUTPUT"

echo "MapReduce pipeline completed successfully."
echo "Final summary: ${LOCAL_OUTPUT}/final/summary.json"
