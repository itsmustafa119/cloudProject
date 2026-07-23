#!/usr/bin/env python3
"""Safely truncate Phase 1 runtime logs after the application stack is stopped."""

import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATHS = (
    Path("data/nginx/nginx_access.log"),
    Path("data/service_logs/match_service.log"),
    Path("data/service_logs/team_service.log"),
    Path("data/service_logs/stadium_service.log"),
)


def truncate_logs(project_root: Path, stack_stopped: bool):
    if not stack_stopped:
        raise ValueError(
            "refusing to modify logs without confirmation that the stack is stopped"
        )

    root = project_root.resolve()
    truncated = []
    for relative_path in LOG_PATHS:
        target = (root / relative_path).resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"log path escapes project root: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8"):
            pass
        truncated.append(target)
    return truncated


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Truncate known runtime logs in place. Stop Docker Compose first; "
            "this tool never deletes a live log file."
        )
    )
    parser.add_argument(
        "--confirm-stack-stopped",
        action="store_true",
        help="required acknowledgement that no process is writing the logs",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        truncated = truncate_logs(PROJECT_ROOT, args.confirm_stack_stopped)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    for path in truncated:
        print(f"truncated: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
