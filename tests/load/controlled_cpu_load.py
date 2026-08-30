#!/usr/bin/env python3
"""Bounded local CPU workload used by the InfraSentinel controlled test.

The command refuses non-loopback API targets and deliberately caps duration and
worker count because package-temperature telemetry is unavailable on this host.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import shutil
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests


MAX_DURATION_SECONDS = 45
MAX_WORKERS = 24
MIN_AVAILABLE_RAM_BYTES = 2 * 1024**3


def busy_worker(stop_event: mp.synchronize.Event, deadline: float) -> None:
    process = psutil.Process()
    if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
        process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    value = 0.123456789
    while not stop_event.is_set() and time.monotonic() < deadline:
        for _ in range(50_000):
            value = math.sin(value) + math.cos(value)


def gpu_snapshot() -> dict[str, float | str] | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    fields = (
        "temperature.gpu,utilization.gpu,memory.used,power.draw,"
        "clocks_event_reasons.sw_thermal_slowdown,"
        "clocks_event_reasons.hw_thermal_slowdown"
    )
    output = subprocess.check_output(
        [
            executable,
            f"--query-gpu={fields}",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=3,
    ).strip().splitlines()[0]
    parts = [part.strip() for part in output.split(",")]
    return {
        "temperature_c": float(parts[0]),
        "utilization_percent": float(parts[1]),
        "memory_used_mib": float(parts[2]),
        "power_w": float(parts[3]),
        "software_thermal_slowdown": parts[4],
        "hardware_thermal_slowdown": parts[5],
    }


def docker_health(docker_executable: str) -> dict[str, str]:
    output = subprocess.check_output(
        [
            docker_executable,
            "ps",
            "--filter",
            "name=infrasentinel-ai-",
            "--format",
            "{{.Names}}|{{.Status}}",
        ],
        text=True,
        timeout=5,
    )
    rows = {}
    for line in output.splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            rows[name] = status
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/health/")
    parser.add_argument("--max-cpu-percent", type=float, default=85.0)
    parser.add_argument("--gpu-stop-temperature", type=float, default=85.0)
    return parser.parse_args()


def validate(args: argparse.Namespace) -> None:
    target = urlparse(args.api_url)
    if target.scheme != "http" or target.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise SystemExit("The healthcheck target must be loopback HTTP.")
    if not 1 <= args.workers <= MAX_WORKERS:
        raise SystemExit(f"Workers must be between 1 and {MAX_WORKERS}.")
    if not 5 <= args.duration <= MAX_DURATION_SECONDS:
        raise SystemExit(
            f"Duration must be between 5 and {MAX_DURATION_SECONDS} seconds."
        )
    if not 20 <= args.max_cpu_percent <= 85:
        raise SystemExit("The CPU abort threshold must be between 20 and 85 percent.")
    if not 60 <= args.gpu_stop_temperature <= 85:
        raise SystemExit("The GPU abort threshold must be between 60 and 85 C.")
    if "CONTROLLED_TEST" not in args.label:
        raise SystemExit("The label must contain CONTROLLED_TEST.")


def summarize(samples: list[dict]) -> dict:
    cpu = [sample["cpu_percent"] for sample in samples]
    ram = [sample["available_ram_bytes"] for sample in samples]
    latency = [sample["api_latency_ms"] for sample in samples]
    gpu = [sample["gpu"] for sample in samples if sample["gpu"]]
    return {
        "sample_count": len(samples),
        "cpu_percent": {
            "mean": round(statistics.fmean(cpu), 3) if cpu else 0,
            "max": round(max(cpu), 3) if cpu else 0,
        },
        "minimum_available_ram_gib": round(min(ram, default=0) / 1024**3, 3),
        "api": {
            "success_count": sum(sample["api_status"] == 200 for sample in samples),
            "latency_mean_ms": round(statistics.fmean(latency), 3) if latency else 0,
            "latency_max_ms": round(max(latency), 3) if latency else 0,
        },
        "gpu": {
            "max_temperature_c": max(
                (sample["temperature_c"] for sample in gpu), default=None
            ),
            "max_utilization_percent": max(
                (sample["utilization_percent"] for sample in gpu), default=None
            ),
            "max_memory_used_mib": max(
                (sample["memory_used_mib"] for sample in gpu), default=None
            ),
            "max_power_w": max((sample["power_w"] for sample in gpu), default=None),
        },
    }


def main() -> int:
    args = parse_args()
    validate(args)
    docker = shutil.which("docker.exe") or shutil.which("docker")
    if not docker:
        raise SystemExit("Docker CLI is unavailable.")

    session = requests.Session()
    session.trust_env = False
    stop_event = mp.Event()
    deadline = time.monotonic() + args.duration
    processes = [
        mp.Process(target=busy_worker, args=(stop_event, deadline), daemon=True)
        for _ in range(args.workers)
    ]
    samples: list[dict] = []
    abort_reason = None
    consecutive_api_failures = 0
    psutil.cpu_percent(None)

    report = {
        "test_marker": "CONTROLLED_TEST",
        "label": args.label,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "workers": args.workers,
            "duration_seconds": args.duration,
            "maximum_cpu_percent": args.max_cpu_percent,
            "minimum_available_ram_gib": MIN_AVAILABLE_RAM_BYTES / 1024**3,
            "gpu_stop_temperature_c": args.gpu_stop_temperature,
            "cpu_temperature": "UNAVAILABLE",
            "priority": "BELOW_NORMAL",
        },
        "samples": samples,
    }

    try:
        for process in processes:
            process.start()
        sample_index = 0
        while time.monotonic() < deadline:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            started = time.perf_counter()
            try:
                response = session.get(args.api_url, timeout=3, allow_redirects=False)
                api_status = response.status_code
            except requests.RequestException:
                api_status = 0
            api_latency_ms = (time.perf_counter() - started) * 1000
            consecutive_api_failures = (
                0 if api_status == 200 else consecutive_api_failures + 1
            )
            try:
                gpu = gpu_snapshot()
            except (OSError, ValueError, subprocess.SubprocessError):
                gpu = None
            try:
                docker_rows = docker_health(docker) if sample_index % 5 == 0 else None
            except (OSError, subprocess.SubprocessError):
                docker_rows = {}
            sample = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cpu_percent": cpu_percent,
                "available_ram_bytes": memory.available,
                "api_status": api_status,
                "api_latency_ms": round(api_latency_ms, 3),
                "gpu": gpu,
                "docker": docker_rows,
            }
            samples.append(sample)
            sample_index += 1

            if cpu_percent >= args.max_cpu_percent:
                abort_reason = f"CPU reached {cpu_percent:.1f} percent"
            elif memory.available < MIN_AVAILABLE_RAM_BYTES:
                abort_reason = "available RAM fell below 2 GiB"
            elif consecutive_api_failures >= 2:
                abort_reason = "two consecutive API healthcheck failures"
            elif gpu and gpu["temperature_c"] >= args.gpu_stop_temperature:
                abort_reason = f"GPU reached {gpu['temperature_c']:.1f} C"
            elif gpu and (
                gpu["software_thermal_slowdown"] == "Active"
                or gpu["hardware_thermal_slowdown"] == "Active"
            ):
                abort_reason = "GPU thermal slowdown became active"
            elif docker_rows is not None and (
                len(docker_rows) < 6
                or any("healthy" not in status for status in docker_rows.values())
            ):
                abort_reason = "Docker service health degraded"
            if abort_reason:
                break
    finally:
        stop_event.set()
        for process in processes:
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        session.close()

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["aborted"] = abort_reason is not None
    report["abort_reason"] = abort_reason
    report["summary"] = summarize(samples)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("label", "aborted", "abort_reason", "summary")}, indent=2))
    return 2 if abort_reason else 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
