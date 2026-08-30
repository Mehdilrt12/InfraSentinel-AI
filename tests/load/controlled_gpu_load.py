#!/usr/bin/env python3
"""Strictly bounded CUDA compute or VRAM validation for the local RTX laptop."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests


MAX_COMPUTE_DURATION = 30
MAX_VRAM_DURATION = 10
MAX_VRAM_FRACTION = 0.50
MIN_AVAILABLE_RAM_BYTES = 2 * 1024**3


def smi_snapshot() -> dict[str, float | str]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        raise RuntimeError("nvidia-smi is unavailable")
    fields = (
        "temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,"
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
    values = [value.strip() for value in output.split(",")]
    return {
        "temperature_c": float(values[0]),
        "utilization_percent": float(values[1]),
        "memory_used_mib": float(values[2]),
        "memory_total_mib": float(values[3]),
        "power_w": float(values[4]),
        "software_thermal_slowdown": values[5],
        "hardware_thermal_slowdown": values[6],
    }


def docker_is_healthy(docker: str) -> bool:
    output = subprocess.check_output(
        [
            docker,
            "ps",
            "--filter",
            "name=infrasentinel-ai-",
            "--format",
            "{{.Status}}",
        ],
        text=True,
        timeout=5,
    )
    statuses = output.splitlines()
    return len(statuses) >= 6 and all("healthy" in status for status in statuses)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("compute", "vram"), required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--duty-cycle", type=float, default=0.40)
    parser.add_argument("--vram-fraction", type=float, default=0.25)
    parser.add_argument("--matrix-size", type=int, default=3072)
    parser.add_argument("--stop-temperature", type=float, default=78.0)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/health/")
    return parser.parse_args()


def validate(args: argparse.Namespace) -> None:
    target = urlparse(args.api_url)
    if target.scheme != "http" or target.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise SystemExit("The healthcheck target must be loopback HTTP.")
    maximum_duration = (
        MAX_COMPUTE_DURATION if args.mode == "compute" else MAX_VRAM_DURATION
    )
    if not 5 <= args.duration <= maximum_duration:
        raise SystemExit(f"Duration must be between 5 and {maximum_duration} seconds.")
    if not 0.10 <= args.duty_cycle <= 0.75:
        raise SystemExit("Compute duty cycle must be between 0.10 and 0.75.")
    if not 0.05 <= args.vram_fraction <= MAX_VRAM_FRACTION:
        raise SystemExit("VRAM fraction must be between 0.05 and 0.50.")
    if not 1024 <= args.matrix_size <= 4096:
        raise SystemExit("Matrix size must be between 1024 and 4096.")
    if not 65 <= args.stop_temperature <= 85:
        raise SystemExit("GPU stop temperature must be between 65 and 85 C.")
    if "CONTROLLED_TEST" not in args.label:
        raise SystemExit("The label must contain CONTROLLED_TEST.")


def main() -> int:
    args = parse_args()
    validate(args)
    try:
        import torch
    except ImportError as exc:
        raise SystemExit("PyTorch is unavailable; GPU test was not run.") from exc
    if not torch.cuda.is_available():
        raise SystemExit("PyTorch CUDA is unavailable; GPU test was not run.")
    docker = shutil.which("docker.exe") or shutil.which("docker")
    if not docker:
        raise SystemExit("Docker CLI is unavailable.")

    baseline = []
    for _ in range(3):
        snapshot = smi_snapshot()
        baseline.append(snapshot)
        if snapshot["temperature_c"] > 60 or snapshot["utilization_percent"] > 5:
            raise SystemExit("Refusing test: GPU is not cool and idle.")
        time.sleep(1)

    session = requests.Session()
    session.trust_env = False
    samples: list[dict] = []
    abort_reason = None
    tensors = []
    iterations = 0
    deadline = time.monotonic() + args.duration
    report = {
        "test_marker": "CONTROLLED_TEST",
        "label": args.label,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "device": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "configuration": {
            "mode": args.mode,
            "duration_seconds": args.duration,
            "duty_cycle": args.duty_cycle if args.mode == "compute" else None,
            "vram_fraction": args.vram_fraction if args.mode == "vram" else None,
            "matrix_size": args.matrix_size if args.mode == "compute" else None,
            "stop_temperature_c": args.stop_temperature,
        },
        "baseline": baseline,
        "samples": samples,
    }

    try:
        torch.set_grad_enabled(False)
        if args.mode == "compute":
            size = args.matrix_size
            tensors = [
                torch.randn((size, size), device="cuda"),
                torch.randn((size, size), device="cuda"),
                torch.empty((size, size), device="cuda"),
            ]
        else:
            total_bytes = torch.cuda.get_device_properties(0).total_memory
            element_count = int(total_bytes * args.vram_fraction / 4)
            tensors = [torch.empty(element_count, dtype=torch.float32, device="cuda")]
            tensors[0].fill_(1.0)
            torch.cuda.synchronize()

        last_sample = 0.0
        while time.monotonic() < deadline:
            if args.mode == "compute":
                compute_started = time.monotonic()
                torch.mm(tensors[0], tensors[1], out=tensors[2])
                torch.cuda.synchronize()
                compute_elapsed = time.monotonic() - compute_started
                iterations += 1
                sleep_seconds = compute_elapsed * (1 / args.duty_cycle - 1)
                if sleep_seconds > 0:
                    time.sleep(min(sleep_seconds, max(0, deadline - time.monotonic())))
            else:
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))

            now = time.monotonic()
            if now - last_sample < 0.5:
                continue
            gpu = smi_snapshot()
            memory = psutil.virtual_memory()
            started = time.perf_counter()
            try:
                api_status = session.get(
                    args.api_url, timeout=3, allow_redirects=False
                ).status_code
            except requests.RequestException:
                api_status = 0
            sample = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gpu": gpu,
                "available_ram_bytes": memory.available,
                "api_status": api_status,
                "api_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
            samples.append(sample)
            last_sample = now
            if gpu["temperature_c"] >= args.stop_temperature:
                abort_reason = f"GPU reached {gpu['temperature_c']:.1f} C"
            elif (
                gpu["software_thermal_slowdown"] == "Active"
                or gpu["hardware_thermal_slowdown"] == "Active"
            ):
                abort_reason = "GPU thermal slowdown became active"
            elif memory.available < MIN_AVAILABLE_RAM_BYTES:
                abort_reason = "available RAM fell below 2 GiB"
            elif api_status != 200:
                abort_reason = f"API healthcheck returned {api_status}"
            elif len(samples) == 1 or len(samples) % 5 == 0:
                if not docker_is_healthy(docker):
                    abort_reason = "Docker service health degraded"
            if abort_reason:
                break
    finally:
        tensors.clear()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        session.close()

    time.sleep(1)
    post_release = smi_snapshot()
    gpu_samples = [sample["gpu"] for sample in samples]
    report.update(
        finished_at=datetime.now(timezone.utc).isoformat(),
        iterations=iterations,
        aborted=abort_reason is not None,
        abort_reason=abort_reason,
        post_release=post_release,
        summary={
            "sample_count": len(samples),
            "max_utilization_percent": max(
                (sample["utilization_percent"] for sample in gpu_samples),
                default=0,
            ),
            "max_memory_used_mib": max(
                (sample["memory_used_mib"] for sample in gpu_samples), default=0
            ),
            "max_temperature_c": max(
                (sample["temperature_c"] for sample in gpu_samples), default=0
            ),
            "max_power_w": max(
                (sample["power_w"] for sample in gpu_samples), default=0
            ),
            "api_success_count": sum(
                sample["api_status"] == 200 for sample in samples
            ),
        },
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "label": report["label"],
                "aborted": report["aborted"],
                "abort_reason": report["abort_reason"],
                "summary": report["summary"],
                "post_release": report["post_release"],
            },
            indent=2,
        )
    )
    return 2 if abort_reason else 0


if __name__ == "__main__":
    raise SystemExit(main())
