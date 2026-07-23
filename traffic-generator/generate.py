#!/usr/bin/env python3
"""Generate reproducible World Cup API traffic through the Nginx gateway."""

import argparse
import random
import socket
import sys
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


USER_AGENT = "phase1-traffic-generator/1.0"

CLIENT_COUNTRIES = (
    "Iran",
    "Iran",
    "Germany",
    "Germany",
    "Brazil",
    "Argentina",
    "Japan",
    "Canada",
    "Mexico",
    "France",
)

COUNTRY_TEAM_PREFERENCES = {
    "Iran": ("Argentina", "Argentina", "Argentina", "Iran", "Iran", "Brazil"),
    "Germany": ("Germany", "Germany", "Germany", "Argentina", "France"),
    "Brazil": ("Brazil", "Brazil", "Brazil", "Argentina", "Germany"),
    "Argentina": ("Argentina", "Argentina", "Argentina", "Brazil", "France"),
    "Japan": ("Japan", "Japan", "Japan", "Argentina", "South Korea"),
    "Canada": ("Canada", "Canada", "Canada", "Argentina", "USA"),
    "Mexico": ("Mexico", "Mexico", "Mexico", "Argentina", "Brazil"),
    "France": ("France", "France", "France", "Argentina", "Germany"),
}

MATCH_DATES = (
    "2026-06-25",
    "2026-06-25",
    "2026-06-25",
    "2026-06-25",
    "2026-06-13",
    "2026-06-18",
    "2026-06-22",
    "2026-07-19",
)

STADIUM_NAMES = (
    "New York New Jersey Stadium",
    "New York New Jersey Stadium",
    "New York New Jersey Stadium",
    "New York New Jersey Stadium",
    "Dallas Stadium",
    "Mexico City Stadium",
    "Los Angeles Stadium",
    "BC Place Vancouver",
)

STADIUM_CITIES = (
    "New York New Jersey",
    "New York New Jersey",
    "Dallas",
    "Mexico City",
    "Los Angeles",
    "Vancouver",
)


@dataclass(frozen=True)
class RequestSpec:
    request_id: str
    client_country: str
    scenario: str
    service: str
    url: str

    @property
    def headers(self):
        return {
            "X-Request-ID": self.request_id,
            "X-Client-Country": self.client_country,
            "X-Scenario": self.scenario,
            "User-Agent": USER_AGENT,
        }


@dataclass(frozen=True)
class RequestResult:
    spec: RequestSpec
    status_code: Optional[int]
    latency_ms: float
    transport_error: Optional[str] = None


@dataclass
class LoadStats:
    requested: int
    completed: int = 0
    transport_errors: int = 0
    status_counts: Counter = field(default_factory=Counter)
    service_counts: Counter = field(default_factory=Counter)
    scenario_counts: Counter = field(default_factory=Counter)
    country_counts: Counter = field(default_factory=Counter)
    transport_error_types: Counter = field(default_factory=Counter)
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0

    def record(self, result: RequestResult):
        self.completed += 1
        self.service_counts[result.spec.service] += 1
        self.scenario_counts[result.spec.scenario] += 1
        self.country_counts[result.spec.client_country] += 1
        self.total_latency_ms += result.latency_ms
        self.min_latency_ms = min(self.min_latency_ms, result.latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, result.latency_ms)

        if result.status_code is not None:
            self.status_counts[result.status_code] += 1
        if result.transport_error is not None:
            self.transport_errors += 1
            self.transport_error_types[result.transport_error] += 1

    @property
    def average_latency_ms(self):
        return self.total_latency_ms / self.completed if self.completed else 0.0


def _normalize_nginx_url(value: str):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise argparse.ArgumentTypeError("Nginx URL must use http or https")
    if not parsed.hostname:
        raise argparse.ArgumentTypeError("Nginx URL must include a hostname")
    if parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("Nginx URL must not contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise argparse.ArgumentTypeError(
            "Nginx URL must be a gateway base URL without a path, query, or fragment"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")


def _positive_int(value: str):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _nonnegative_int(value: str):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def _positive_float(value: str):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def _url(base_url: str, endpoint: str, **query):
    query_string = urlencode(query)
    return f"{base_url}{endpoint}" + (f"?{query_string}" if query_string else "")


def _coverage_cases(base_url: str):
    """Return a deterministic prefix that guarantees required traffic coverage."""
    return (
        ("Iran", "normal", "team-service", _url(base_url, "/api/teams", name="Argentina")),
        ("Germany", "normal", "match-service", _url(base_url, "/api/matches", date="2026-06-25")),
        (
            "Brazil",
            "normal",
            "stadium-service",
            _url(base_url, "/api/stadiums", name="New York New Jersey Stadium"),
        ),
        ("Iran", "normal", "team-service", _url(base_url, "/api/teams", name="Unknown FC")),
        ("Canada", "normal", "match-service", _url(base_url, "/api/matches", date="not-a-date")),
        ("Mexico", "normal", "stadium-service", _url(base_url, "/api/stadiums")),
        ("Japan", "server_error", "team-service", _url(base_url, "/api/teams", name="Japan")),
        (
            "France",
            "server_error",
            "match-service",
            _url(base_url, "/api/matches", date="2026-06-25"),
        ),
        (
            "Argentina",
            "server_error",
            "stadium-service",
            _url(base_url, "/api/stadiums", city="Dallas"),
        ),
        ("Iran", "slow", "team-service", _url(base_url, "/api/teams", name="Argentina")),
        ("Germany", "slow", "match-service", _url(base_url, "/api/matches", date="2026-06-25")),
        (
            "Brazil",
            "slow",
            "stadium-service",
            _url(base_url, "/api/stadiums", name="New York New Jersey Stadium"),
        ),
    )


def _random_request(rng: random.Random, base_url: str):
    country = rng.choice(CLIENT_COUNTRIES)
    service = rng.choices(
        ("team-service", "match-service", "stadium-service"),
        weights=(48, 30, 22),
        k=1,
    )[0]
    scenario = rng.choices(
        ("normal", "slow", "server_error"), weights=(92, 5, 3), k=1
    )[0]
    invalid = scenario != "server_error" and rng.random() < 0.07

    if service == "team-service":
        if invalid:
            if rng.random() < 0.25:
                endpoint = _url(base_url, "/api/teams")
            else:
                endpoint = _url(base_url, "/api/teams", name="Unknown FC")
        else:
            team = rng.choice(COUNTRY_TEAM_PREFERENCES[country])
            endpoint = _url(base_url, "/api/teams", name=team)
    elif service == "match-service":
        if invalid:
            invalid_date = rng.choice(("not-a-date", "2026-01-01", ""))
            endpoint = (
                _url(base_url, "/api/matches", date=invalid_date)
                if invalid_date
                else _url(base_url, "/api/matches")
            )
        else:
            endpoint = _url(base_url, "/api/matches", date=rng.choice(MATCH_DATES))
    else:
        if invalid:
            invalid_kind = rng.choice(("missing", "name", "city"))
            if invalid_kind == "missing":
                endpoint = _url(base_url, "/api/stadiums")
            elif invalid_kind == "name":
                endpoint = _url(base_url, "/api/stadiums", name="Unknown Stadium")
            else:
                endpoint = _url(base_url, "/api/stadiums", city="Unknown City")
        elif rng.random() < 0.75:
            endpoint = _url(
                base_url, "/api/stadiums", name=rng.choice(STADIUM_NAMES)
            )
        else:
            endpoint = _url(
                base_url, "/api/stadiums", city=rng.choice(STADIUM_CITIES)
            )

    return country, scenario, service, endpoint


def generate_specs(count: int, base_url: str, seed: int) -> Iterable[RequestSpec]:
    """Yield deterministic request specifications without retaining all in memory."""
    rng = random.Random(seed)
    coverage = _coverage_cases(base_url)
    for index in range(1, count + 1):
        if index <= len(coverage):
            country, scenario, service, endpoint = coverage[index - 1]
        else:
            country, scenario, service, endpoint = _random_request(rng, base_url)
        yield RequestSpec(
            request_id=f"req_{index:06d}",
            client_country=country,
            scenario=scenario,
            service=service,
            url=endpoint,
        )


def send_request(spec: RequestSpec, timeout: float) -> RequestResult:
    started_at = time.perf_counter()
    request = Request(spec.url, headers=spec.headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read()
            status_code = response.status
        error = None
    except HTTPError as exc:
        status_code = exc.code
        error = None
        exc.close()
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        status_code = None
        error = type(exc).__name__
    latency_ms = (time.perf_counter() - started_at) * 1000
    return RequestResult(spec, status_code, latency_ms, error)


def run_traffic(
    specs: Iterable[RequestSpec],
    request_count: int,
    workers: int,
    timeout: float,
    progress_every: int,
):
    """Execute a bounded number of concurrent requests and aggregate results."""
    stats = LoadStats(requested=request_count)
    spec_iterator = iter(specs)
    max_in_flight = max(workers, workers * 4)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {}

        def submit_next():
            try:
                spec = next(spec_iterator)
            except StopIteration:
                return False
            future = executor.submit(send_request, spec, timeout)
            pending[future] = spec
            return True

        for _ in range(min(request_count, max_in_flight)):
            submit_next()

        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                pending.pop(future)
                stats.record(future.result())
                submit_next()
                if progress_every and stats.completed % progress_every == 0:
                    print(
                        f"progress: {stats.completed}/{request_count} requests",
                        flush=True,
                    )

    return stats


def _format_counter(counter: Counter):
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter)) or "none"


def print_summary(stats: LoadStats, elapsed_seconds: float):
    min_latency = stats.min_latency_ms if stats.completed else 0.0
    throughput = stats.completed / elapsed_seconds if elapsed_seconds else 0.0
    print("\nTraffic generation summary")
    print(f"  requested: {stats.requested}")
    print(f"  completed: {stats.completed}")
    print(f"  transport errors: {stats.transport_errors}")
    print(f"  HTTP statuses: {_format_counter(stats.status_counts)}")
    print(f"  services: {_format_counter(stats.service_counts)}")
    print(f"  scenarios: {_format_counter(stats.scenario_counts)}")
    print(f"  countries: {_format_counter(stats.country_counts)}")
    if stats.transport_error_types:
        print(f"  transport error types: {_format_counter(stats.transport_error_types)}")
    print(f"  elapsed seconds: {elapsed_seconds:.3f}")
    print(f"  throughput req/s: {throughput:.2f}")
    print(
        "  latency ms min/avg/max: "
        f"{min_latency:.2f}/{stats.average_latency_ms:.2f}/{stats.max_latency_ms:.2f}"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate reproducible requests through the Phase 1 Nginx gateway."
    )
    parser.add_argument(
        "--requests",
        type=_positive_int,
        default=1000,
        help="number of requests to send (debug minimum: 1000; final minimum: 100000)",
    )
    parser.add_argument(
        "--nginx-url",
        type=_normalize_nginx_url,
        default="http://localhost:8080",
        help="Nginx gateway base URL",
    )
    parser.add_argument("--workers", type=_positive_int, default=32)
    parser.add_argument("--timeout", type=_positive_float, default=5.0)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--progress-every",
        type=_nonnegative_int,
        default=1000,
        help="print progress every N completions; 0 disables progress output",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(
        f"sending {args.requests} requests to {args.nginx_url} "
        f"with {args.workers} workers (seed={args.seed})"
    )
    started_at = time.perf_counter()
    specs = generate_specs(args.requests, args.nginx_url, args.seed)
    stats = run_traffic(
        specs,
        request_count=args.requests,
        workers=args.workers,
        timeout=args.timeout,
        progress_every=args.progress_every,
    )
    elapsed_seconds = time.perf_counter() - started_at
    print_summary(stats, elapsed_seconds)
    return 2 if stats.transport_errors else 0


if __name__ == "__main__":
    sys.exit(main())
