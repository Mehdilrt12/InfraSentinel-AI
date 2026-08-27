#!/usr/bin/env python3
"""Reproductible agent-ingestion load test for InfraSentinel AI.

The script provisions isolated agents through the real domain services, drives the
HTTP agent endpoints, samples the backend/PostgreSQL/Redis processes, writes a JSON
report, and removes its tenant unless --keep-data is supplied.
"""

import argparse
import json
import math
import os
import random
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import redis  # noqa: E402
from accounts.models import Customer  # noqa: E402
from django.conf import settings  # noqa: E402
from django.db import close_old_connections, connection  # noqa: E402
from inventory.models import Environment, Machine  # noqa: E402
from inventory.services import create_enrollment_code, enroll_agent  # noqa: E402


METRIC_DEFINITIONS = (
    ("system.cpu.utilization", "%"),
    ("system.memory.utilization", "%"),
    ("system.disk.utilization", "%"),
    ("system.disk.free", "bytes"),
    ("system.disk.io.read", "bytes/s"),
    ("system.disk.io.write", "bytes/s"),
    ("system.network.in", "bytes/s"),
    ("system.network.out", "bytes/s"),
    ("system.network.latency", "ms"),
    ("system.uptime", "seconds"),
    ("system.process.count", "count"),
    ("windows.service.state", "state"),
)


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def safe_mean(values):
    return statistics.fmean(values) if values else 0.0


def mb(value):
    return round(value / (1024 * 1024), 3)


class RequestStatistics:
    def __init__(self):
        self._lock = threading.Lock()
        self.records = []
        self.accepted_metrics = 0

    def add(self, request_type, status, elapsed_ms, accepted=0, error=""):
        with self._lock:
            self.records.append(
                {
                    "type": request_type,
                    "status": status,
                    "elapsed_ms": elapsed_ms,
                    "error": error[:240],
                }
            )
            self.accepted_metrics += accepted

    def summarize(self, elapsed_seconds):
        total = len(self.records)
        failures = [row for row in self.records if not 200 <= row["status"] < 300]
        latencies = [row["elapsed_ms"] for row in self.records]
        metric_latencies = [
            row["elapsed_ms"] for row in self.records if row["type"] == "metrics"
        ]
        statuses = Counter(str(row["status"]) for row in self.records)
        errors = Counter(row["error"] for row in failures if row["error"])
        return {
            "requests": total,
            "requests_per_second": round(total / elapsed_seconds, 3),
            "error_rate_percent": round((len(failures) / total * 100) if total else 0, 3),
            "status_counts": dict(sorted(statuses.items())),
            "accepted_metrics": self.accepted_metrics,
            "latency_ms": {
                "mean": round(safe_mean(latencies), 3),
                "p50": round(percentile(latencies, 0.50), 3),
                "p95": round(percentile(latencies, 0.95), 3),
                "p99": round(percentile(latencies, 0.99), 3),
                "max": round(max(latencies, default=0.0), 3),
            },
            "metric_request_latency_ms": {
                "mean": round(safe_mean(metric_latencies), 3),
                "p50": round(percentile(metric_latencies, 0.50), 3),
                "p95": round(percentile(metric_latencies, 0.95), 3),
                "p99": round(percentile(metric_latencies, 0.99), 3),
                "max": round(max(metric_latencies, default=0.0), 3),
            },
            "top_errors": [
                {"error": error, "count": count}
                for error, count in errors.most_common(5)
            ],
        }


def database_snapshot(include_row_counts=False):
    close_old_connections()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT xact_commit, xact_rollback, tup_inserted, tup_updated,
                   blks_read, blks_hit, temp_files, temp_bytes, deadlocks,
                   numbackends, pg_database_size(current_database())
              FROM pg_stat_database
             WHERE datname = current_database()
            """
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(*) FILTER (WHERE state = 'active'), count(*)
              FROM pg_stat_activity
             WHERE datname = current_database()
            """
        )
        active, connections = cursor.fetchone()
    keys = (
        "xact_commit",
        "xact_rollback",
        "tup_inserted",
        "tup_updated",
        "blks_read",
        "blks_hit",
        "temp_files",
        "temp_bytes",
        "deadlocks",
        "numbackends",
        "database_size_bytes",
    )
    result = dict(zip(keys, row))
    result.update(active_connections=active, connections=connections)
    if include_row_counts:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM metrics_normalizedmetric")
            result["metric_rows"] = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM realtime_realtimeevent")
            result["realtime_rows"] = cursor.fetchone()[0]
    return result


def redis_snapshot(client):
    stats = client.info("stats")
    memory = client.info("memory")
    clients = client.info("clients")
    return {
        "total_commands_processed": stats.get("total_commands_processed", 0),
        "instantaneous_ops_per_sec": stats.get("instantaneous_ops_per_sec", 0),
        "used_memory": memory.get("used_memory", 0),
        "used_memory_peak": memory.get("used_memory_peak", 0),
        "connected_clients": clients.get("connected_clients", 0),
        "celery_queue": client.llen("celery"),
        "hyperv_queue": client.llen("hyperv"),
    }


class ResourceMonitor:
    def __init__(self, backend_pid):
        self.process = psutil.Process(backend_pid)
        self.redis = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        self.samples = []
        self.stop_event = threading.Event()
        self.thread = None
        self.process.cpu_percent(None)
        psutil.cpu_percent(None)

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop_event.wait(1):
            try:
                sample = {
                    "timestamp": time.time(),
                    "backend_cpu_percent": self.process.cpu_percent(None),
                    "backend_rss_bytes": self.process.memory_info().rss,
                    "backend_threads": self.process.num_threads(),
                    "system_cpu_percent": psutil.cpu_percent(None),
                    "system_memory_percent": psutil.virtual_memory().percent,
                    "postgresql": database_snapshot(),
                    "redis": redis_snapshot(self.redis),
                }
                self.samples.append(sample)
            except (psutil.Error, redis.RedisError, Exception) as exc:
                self.samples.append({"monitor_error": f"{type(exc).__name__}: {exc}"})
        close_old_connections()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def summarize(self, before_db, after_db, before_redis, after_redis, duration):
        valid = [row for row in self.samples if "backend_cpu_percent" in row]
        cpu = [row["backend_cpu_percent"] for row in valid]
        rss = [row["backend_rss_bytes"] for row in valid]
        system_cpu = [row["system_cpu_percent"] for row in valid]
        active = [row["postgresql"]["active_connections"] for row in valid]
        connections = [row["postgresql"]["connections"] for row in valid]
        redis_ops = [row["redis"]["instantaneous_ops_per_sec"] for row in valid]
        redis_memory = [row["redis"]["used_memory"] for row in valid]
        celery_queue = [row["redis"]["celery_queue"] for row in valid]
        hyperv_queue = [row["redis"]["hyperv_queue"] for row in valid]
        reads = after_db["blks_read"] - before_db["blks_read"]
        hits = after_db["blks_hit"] - before_db["blks_hit"]
        return {
            "sample_count": len(valid),
            "backend": {
                "cpu_percent_mean": round(safe_mean(cpu), 3),
                "cpu_percent_p95": round(percentile(cpu, 0.95), 3),
                "cpu_percent_max": round(max(cpu, default=0.0), 3),
                "rss_mb_start": mb(rss[0]) if rss else 0,
                "rss_mb_max": mb(max(rss, default=0)),
                "rss_mb_end": mb(rss[-1]) if rss else 0,
                "threads_max": max(
                    (row["backend_threads"] for row in valid), default=0
                ),
            },
            "host": {
                "cpu_percent_mean": round(safe_mean(system_cpu), 3),
                "cpu_percent_max": round(max(system_cpu, default=0.0), 3),
                "memory_percent_max": round(
                    max((row["system_memory_percent"] for row in valid), default=0.0),
                    3,
                ),
            },
            "postgresql": {
                "transactions_per_second": round(
                    (
                        after_db["xact_commit"]
                        + after_db["xact_rollback"]
                        - before_db["xact_commit"]
                        - before_db["xact_rollback"]
                    )
                    / duration,
                    3,
                ),
                "tuples_inserted_per_second": round(
                    (after_db["tup_inserted"] - before_db["tup_inserted"])
                    / duration,
                    3,
                ),
                "tuples_updated_per_second": round(
                    (after_db["tup_updated"] - before_db["tup_updated"])
                    / duration,
                    3,
                ),
                "metric_rows_inserted_per_second": round(
                    (after_db["metric_rows"] - before_db["metric_rows"])
                    / duration,
                    3,
                ),
                "realtime_rows_inserted_per_second": round(
                    (after_db["realtime_rows"] - before_db["realtime_rows"])
                    / duration,
                    3,
                ),
                "active_connections_max": max(active, default=0),
                "connections_max": max(connections, default=0),
                "cache_hit_percent_delta": round(
                    hits / (hits + reads) * 100 if hits + reads else 100.0, 3
                ),
                "database_growth_mb": mb(
                    after_db["database_size_bytes"]
                    - before_db["database_size_bytes"]
                ),
                "temp_bytes_delta": after_db["temp_bytes"] - before_db["temp_bytes"],
                "deadlocks_delta": after_db["deadlocks"] - before_db["deadlocks"],
            },
            "redis": {
                "commands_per_second": round(
                    (
                        after_redis["total_commands_processed"]
                        - before_redis["total_commands_processed"]
                    )
                    / duration,
                    3,
                ),
                "instantaneous_ops_per_second_max": max(redis_ops, default=0),
                "used_memory_mb_start": mb(before_redis["used_memory"]),
                "used_memory_mb_max": mb(max(redis_memory, default=0)),
                "used_memory_mb_end": mb(after_redis["used_memory"]),
                "connected_clients_max": max(
                    (row["redis"]["connected_clients"] for row in valid), default=0
                ),
            },
            "celery": {
                "celery_queue_length_max": max(celery_queue, default=0),
                "hyperv_queue_length_max": max(hyperv_queue, default=0),
                "celery_queue_length_end": after_redis["celery_queue"],
                "hyperv_queue_length_end": after_redis["hyperv_queue"],
            },
            "monitor_errors": [
                row["monitor_error"] for row in self.samples if "monitor_error" in row
            ],
        }


def processing_latency(customer_id, stage_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*),
                   avg(extract(epoch from (received_at - timestamp)) * 1000),
                   percentile_cont(0.50) WITHIN GROUP (
                     ORDER BY extract(epoch from (received_at - timestamp)) * 1000
                   ),
                   percentile_cont(0.95) WITHIN GROUP (
                     ORDER BY extract(epoch from (received_at - timestamp)) * 1000
                   ),
                   percentile_cont(0.99) WITHIN GROUP (
                     ORDER BY extract(epoch from (received_at - timestamp)) * 1000
                   ),
                   max(extract(epoch from (received_at - timestamp)) * 1000)
              FROM metrics_normalizedmetric
             WHERE customer_id = %s
               AND metadata ->> 'load_stage' = %s
            """,
            [str(customer_id), stage_name],
        )
        count, average, p50, p95, p99, maximum = cursor.fetchone()
    return {
        "samples": count,
        "mean_ms": round(float(average or 0), 3),
        "p50_ms": round(float(p50 or 0), 3),
        "p95_ms": round(float(p95 or 0), 3),
        "p99_ms": round(float(p99 or 0), 3),
        "max_ms": round(float(maximum or 0), 3),
    }


def metric_value(name, agent_index, sequence, rng):
    wave = math.sin((sequence + agent_index) / 7)
    if name == "system.cpu.utilization":
        return max(1, min(98, 42 + 20 * wave + rng.uniform(-5, 5)))
    if name == "system.memory.utilization":
        return max(10, min(96, 58 + 10 * wave + rng.uniform(-3, 3)))
    if name == "system.disk.utilization":
        return 63 + (agent_index % 15) + rng.uniform(-1, 1)
    if name == "system.disk.free":
        return (180 - agent_index % 80) * 1024**3
    if name == "system.disk.io.read":
        return 4_000_000 + abs(wave) * 35_000_000 + rng.uniform(0, 500_000)
    if name == "system.disk.io.write":
        return 2_000_000 + abs(wave) * 20_000_000 + rng.uniform(0, 500_000)
    if name == "system.network.in":
        return 1_000_000 + abs(wave) * 18_000_000 + rng.uniform(0, 300_000)
    if name == "system.network.out":
        return 700_000 + abs(wave) * 9_000_000 + rng.uniform(0, 200_000)
    if name == "system.network.latency":
        return 8 + abs(wave) * 30 + rng.uniform(0, 4)
    if name == "system.uptime":
        return 86400 + agent_index * 600 + sequence
    if name == "system.process.count":
        return 115 + agent_index % 40 + round(wave * 4)
    return 1


def build_metrics(run_id, stage_name, agent_index, sequence, rng):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    rows = []
    for metric_name, unit in METRIC_DEFINITIONS:
        status = "running" if metric_name == "windows.service.state" else "ok"
        rows.append(
            {
                "timestamp": timestamp,
                "metric_name": metric_name,
                "metric_value": metric_value(
                    metric_name, agent_index, sequence, rng
                ),
                "unit": unit,
                "status": status,
                "metadata": {
                    "load_run_id": run_id,
                    "load_stage": stage_name,
                    "collector": "phase24-realistic-windows",
                    **(
                        {"service_name": "W32Time"}
                        if metric_name == "windows.service.state"
                        else {}
                    ),
                },
                "idempotency_key": (
                    f"{run_id}:{stage_name}:{agent_index}:{sequence}:{metric_name}"
                ),
            }
        )
    return rows


def send_request(session, method, url, token, payload, request_type, statistics):
    started = time.perf_counter()
    try:
        response = session.request(
            method,
            url,
            json=payload,
            headers={"X-Agent-Token": token, "Accept": "application/json"},
            timeout=15,
            allow_redirects=False,
        )
        elapsed = (time.perf_counter() - started) * 1000
        accepted = 0
        error = ""
        if response.status_code == 202:
            try:
                accepted = int(response.json().get("accepted", 0))
            except (ValueError, TypeError):
                error = "Invalid success response"
        elif not response.ok:
            error = f"HTTP {response.status_code}"
        statistics.add(request_type, response.status_code, elapsed, accepted, error)
    except requests.RequestException as exc:
        elapsed = (time.perf_counter() - started) * 1000
        statistics.add(request_type, 0, elapsed, error=f"{type(exc).__name__}: {exc}")


def agent_worker(
    agent_info,
    agent_index,
    base_url,
    run_id,
    stage_name,
    start_event,
    stage_end,
    interval_seconds,
    heartbeat_seconds,
    statistics,
):
    session = requests.Session()
    session.trust_env = False
    rng = random.Random(f"{run_id}:{stage_name}:{agent_index}")
    start_event.wait()
    sequence = 0
    next_request = time.monotonic() + rng.uniform(0, interval_seconds)
    next_heartbeat = next_request
    while True:
        now = time.monotonic()
        if now >= stage_end:
            break
        wait = min(max(0.0, next_request - now), stage_end - now)
        if wait > 0:
            time.sleep(wait)
        if time.monotonic() >= stage_end:
            break
        if time.monotonic() >= next_heartbeat:
            send_request(
                session,
                "POST",
                f"{base_url}/api/agent/heartbeat/",
                agent_info["token"],
                {"version": "2.0.0-load"},
                "heartbeat",
                statistics,
            )
            next_heartbeat = max(
                next_heartbeat + heartbeat_seconds, time.monotonic()
            )
        metrics = build_metrics(run_id, stage_name, agent_index, sequence, rng)
        send_request(
            session,
            "POST",
            f"{base_url}/api/agent/metrics/",
            agent_info["token"],
            {"machine_id": agent_info["machine_id"], "metrics": metrics},
            "metrics",
            statistics,
        )
        sequence += 1
        next_request = max(next_request + interval_seconds, time.monotonic())
    session.close()


def provision_agents(run_id, count):
    customer = Customer.objects.create(
        name=f"Performance Test {run_id}", slug=f"perf-{run_id.lower()}"
    )
    environment = Environment.objects.create(
        customer=customer,
        name="Windows Load Environment",
        kind=Environment.Kind.WINDOWS,
        metadata={"load_test": True, "run_id": run_id},
    )
    agents = []
    for index in range(count):
        code = create_enrollment_code(customer, environment, ttl_minutes=60)
        agent, token = enroll_agent(
            code,
            external_id=f"load-{run_id}-{index:03d}",
            hostname=f"LOAD-WIN-{index:03d}",
            ip_address=f"10.240.{index // 254}.{index % 254 + 1}",
            os_information={
                "system": "Windows",
                "release": "Server 2022",
                "architecture": "AMD64",
                "load_test": True,
            },
            version="2.0.0-load",
            audit_ip="127.0.0.1",
        )
        agents.append(
            {
                "agent_id": str(agent.pk),
                "machine_id": str(agent.machine_id),
                "token": token,
            }
        )
    return customer, agents


def database_metadata():
    with connection.cursor() as cursor:
        cursor.execute("SELECT version(), current_database(), current_setting('max_connections')")
        version, database, max_connections = cursor.fetchone()
    return {
        "version": version,
        "database": database,
        "max_connections": int(max_connections),
    }


def run_stage(args, customer, agents, agent_count, redis_client):
    stage_name = f"agents-{agent_count}"
    statistics = RequestStatistics()
    monitor = ResourceMonitor(args.backend_pid)
    before_db = database_snapshot(include_row_counts=True)
    before_redis = redis_snapshot(redis_client)
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    stage_end = started + args.duration
    start_event = threading.Event()
    monitor.start()
    with ThreadPoolExecutor(max_workers=agent_count) as executor:
        futures = [
            executor.submit(
                agent_worker,
                agents[index],
                index,
                args.base_url.rstrip("/"),
                args.run_id,
                stage_name,
                start_event,
                stage_end,
                args.interval,
                args.heartbeat_interval,
                statistics,
            )
            for index in range(agent_count)
        ]
        start_event.set()
        for future in futures:
            future.result()
    elapsed = time.monotonic() - started
    monitor.stop()
    after_db = database_snapshot(include_row_counts=True)
    after_redis = redis_snapshot(redis_client)
    summary = statistics.summarize(elapsed)
    summary.update(
        {
            "stage": stage_name,
            "agents": agent_count,
            "started_at": started_wall.isoformat(),
            "duration_seconds": round(elapsed, 3),
            "configured_duration_seconds": args.duration,
            "request_interval_seconds": args.interval,
            "metrics_per_batch": len(METRIC_DEFINITIONS),
            "metric_processing_latency": processing_latency(
                customer.pk, stage_name
            ),
            "resources": monitor.summarize(
                before_db, after_db, before_redis, after_redis, elapsed
            ),
        }
    )
    return summary


def cleanup_customer(customer):
    machine_deleted = Machine.objects.filter(customer=customer).delete()[0]
    environment_deleted = Environment.objects.filter(customer=customer).delete()[0]
    customer_deleted = Customer.objects.filter(pk=customer.pk).delete()[0]
    return {
        "machine_cascade_deleted": machine_deleted,
        "environment_cascade_deleted": environment_deleted,
        "customer_cascade_deleted": customer_deleted,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--backend-pid", type=int, required=True)
    parser.add_argument("--stages", default="1,10,25,50,100")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--heartbeat-interval", type=float, default=60.0)
    parser.add_argument("--cooldown", type=float, default=5.0)
    parser.add_argument("--run-id", default=datetime.now().strftime("P24%Y%m%d%H%M%S"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--keep-data", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    stages = [int(value) for value in args.stages.split(",") if value.strip()]
    if not stages or any(value < 1 or value > 1000 for value in stages):
        raise SystemExit("Les paliers doivent contenir entre 1 et 1000 agents.")
    if args.duration < 5 or args.interval <= 0 or args.heartbeat_interval <= 0:
        raise SystemExit("Durée minimale: 5 s; intervalles strictement positifs.")
    if not psutil.pid_exists(args.backend_pid):
        raise SystemExit(f"Processus backend introuvable: {args.backend_pid}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    redis_client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
    redis_client.ping()
    customer = None
    report = {
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "stages": stages,
            "duration_seconds": args.duration,
            "interval_seconds": args.interval,
            "heartbeat_interval_seconds": args.heartbeat_interval,
            "metrics_per_batch": len(METRIC_DEFINITIONS),
            "load_model": "closed-loop agents with randomized initial jitter",
            "throttle_profile": os.getenv("AGENT_REQUEST_RATE", "settings default"),
        },
        "environment": {
            "base_url": args.base_url,
            "backend_pid": args.backend_pid,
            "backend_command": "dedicated single-process Daphne",
            "django_version": django.get_version(),
            "python_version": sys.version.split()[0],
            "debug": settings.DEBUG,
            "host": {
                "platform": sys.platform,
                "logical_cpus": psutil.cpu_count(),
                "physical_cpus": psutil.cpu_count(logical=False),
                "memory_gb": round(psutil.virtual_memory().total / 1024**3, 3),
            },
            "postgresql": database_metadata(),
            "redis": {
                "version": redis_client.info("server").get("redis_version"),
                "endpoint": (
                    f"{urlparse(settings.REDIS_URL).hostname}:"
                    f"{urlparse(settings.REDIS_URL).port or 6379}"
                ),
            },
        },
        "stages": [],
        "cleanup": None,
    }
    try:
        customer, agents = provision_agents(args.run_id, max(stages))
        for index, agent_count in enumerate(stages):
            result = run_stage(args, customer, agents, agent_count, redis_client)
            report["stages"].append(result)
            print(
                f"{agent_count:>3} agents | {result['requests_per_second']:>7.2f} req/s | "
                f"p95 {result['latency_ms']['p95']:>8.2f} ms | "
                f"errors {result['error_rate_percent']:>6.2f}% | "
                f"CPU {result['resources']['backend']['cpu_percent_mean']:>6.2f}%",
                flush=True,
            )
            if index < len(stages) - 1:
                time.sleep(args.cooldown)
    finally:
        if customer and not args.keep_data:
            report["cleanup"] = cleanup_customer(customer)
        elif customer:
            report["cleanup"] = {"kept_customer_id": str(customer.pk)}
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
