#!/usr/bin/env python3
"""Parse raw gateway/service JSONL and emit tagged, cleaned CSV records."""

import csv
import io
import json
import os
import sys


NGINX_FIELDS = (
    "timestamp",
    "request_id",
    "client_country",
    "scenario",
    "service",
    "method",
    "path",
    "status_code",
    "request_time_ms",
    "user_agent",
)

SERVICE_FIELDS = (
    "timestamp",
    "request_id",
    "client_country",
    "service",
    "endpoint",
    "entity_type",
    "entity_value",
    "status_code",
    "processing_time_ms",
    "event_type",
)

RAW_NGINX_REQUIRED = {
    "timestamp",
    "request_id",
    "client_ip",
    "client_country",
    "scenario",
    "method",
    "path",
    "service",
    "status_code",
    "request_time_sec",
    "user_agent",
}

RAW_SERVICE_REQUIRED = {
    "timestamp",
    "request_id",
    "client_country",
    "service",
    "endpoint",
    "entity_type",
    "entity_value",
    "status_code",
    "processing_time_ms",
    "event_type",
}


def csv_row(values):
    output = io.StringIO()
    csv.writer(output, lineterminator="").writerow(values)
    return output.getvalue()


def emit(tag, values):
    print(f"{tag}\t{csv_row(values)}")


def input_source():
    source = (
        os.environ.get("mapreduce_map_input_file")
        or os.environ.get("map_input_file")
        or "unknown"
    )
    return os.path.basename(source)


def emit_invalid(reason, raw_line):
    emit("INVALID", (input_source(), reason, raw_line))


def integer(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    converted = int(value)
    if str(converted) != str(value) and not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return converted


def nonnegative_number(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    converted = float(value)
    if converted < 0:
        raise ValueError(f"{field_name} must be nonnegative")
    return converted


def require_fields(record, required):
    missing = sorted(required - set(record))
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))


def parse_nginx(record):
    require_fields(record, RAW_NGINX_REQUIRED)
    status_code = integer(record["status_code"], "status_code")
    request_time_ms = nonnegative_number(
        record["request_time_sec"], "request_time_sec"
    ) * 1000
    cleaned = {
        "timestamp": record["timestamp"],
        "request_id": record["request_id"],
        "client_country": record["client_country"],
        "scenario": record["scenario"],
        "service": record["service"],
        "method": record["method"],
        "path": record["path"],
        "status_code": status_code,
        "request_time_ms": f"{request_time_ms:.3f}",
        "user_agent": record["user_agent"],
    }
    emit("NGINX", (cleaned[field] for field in NGINX_FIELDS))


def parse_service(record):
    require_fields(record, RAW_SERVICE_REQUIRED)
    status_code = integer(record["status_code"], "status_code")
    processing_time_ms = nonnegative_number(
        record["processing_time_ms"], "processing_time_ms"
    )
    cleaned = {
        "timestamp": record["timestamp"],
        "request_id": record["request_id"],
        "client_country": record["client_country"],
        "service": record["service"],
        "endpoint": record["endpoint"],
        "entity_type": record["entity_type"],
        "entity_value": record["entity_value"],
        "status_code": status_code,
        "processing_time_ms": f"{processing_time_ms:.3f}",
        "event_type": record["event_type"],
    }
    emit("SERVICE", (cleaned[field] for field in SERVICE_FIELDS))


def process_line(raw_line):
    try:
        record = json.loads(raw_line)
        if not isinstance(record, dict):
            raise ValueError("record must be a JSON object")
        if "request_time_sec" in record:
            parse_nginx(record)
        elif "processing_time_ms" in record:
            parse_service(record)
        else:
            raise ValueError("unrecognized log schema")
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        emit_invalid(str(exc), raw_line)


def main():
    for line in sys.stdin:
        raw_line = line.rstrip("\r\n")
        if raw_line:
            process_line(raw_line)
        else:
            emit_invalid("blank JSONL record", raw_line)


if __name__ == "__main__":
    main()
