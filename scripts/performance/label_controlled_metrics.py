#!/usr/bin/env python3
"""Label real-agent metrics captured during explicitly controlled load windows.

The command is dry-run by default. It accepts only reports carrying the
CONTROLLED_TEST marker and merges labels into existing metric metadata.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from inventory.models import Machine  # noqa: E402
from metrics.models import NormalizedMetric  # noqa: E402


def parse_timestamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def load_window(path, padding_before, padding_after):
    report_path = Path(path).resolve()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if payload.get("test_marker") != "CONTROLLED_TEST":
        raise ValueError(f"Rapport sans marqueur CONTROLLED_TEST: {report_path.name}")
    sample_times = [
        parse_timestamp(sample["timestamp"])
        for sample in payload.get("samples", [])
        if sample.get("timestamp")
    ]
    if not sample_times:
        raise ValueError(f"Rapport sans échantillon horodaté: {report_path.name}")
    started_at = parse_timestamp(payload.get("started_at") or min(sample_times))
    return {
        "label": str(payload.get("label") or report_path.stem),
        "report": report_path.name,
        "start": min(started_at, min(sample_times)) - timedelta(seconds=padding_before),
        "end": max(sample_times) + timedelta(seconds=padding_after),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--reports", nargs="+", required=True)
    parser.add_argument("--padding-before", type=int, default=30)
    parser.add_argument("--padding-after", type=int, default=60)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.padding_before <= 300 or not 0 <= args.padding_after <= 300:
        raise SystemExit("Les marges doivent être comprises entre 0 et 300 secondes.")

    machine = Machine.objects.get(pk=args.machine_id)
    windows = [
        load_window(path, args.padding_before, args.padding_after)
        for path in args.reports
    ]
    start = min(window["start"] for window in windows)
    end = max(window["end"] for window in windows)
    candidates = NormalizedMetric.objects.filter(
        machine=machine, timestamp__gte=start, timestamp__lte=end
    ).order_by("timestamp")
    updates = []
    matched_by_label = {window["label"]: 0 for window in windows}
    for metric in candidates.iterator(chunk_size=500):
        matching = [
            window for window in windows if window["start"] <= metric.timestamp <= window["end"]
        ]
        if not matching:
            continue
        metadata = dict(metric.metadata or {})
        labels = set(metadata.get("controlled_labels") or [])
        reports = set(metadata.get("controlled_reports") or [])
        for window in matching:
            labels.add(window["label"])
            reports.add(window["report"])
            matched_by_label[window["label"]] += 1
        metadata.update(
            test_marker="CONTROLLED_TEST",
            controlled_labels=sorted(labels),
            controlled_reports=sorted(reports),
        )
        metric.metadata = metadata
        updates.append(metric)

    if args.apply and updates:
        NormalizedMetric.objects.bulk_update(updates, ["metadata"], batch_size=500)
    print(
        json.dumps(
            {
                "mode": "APPLY" if args.apply else "DRY_RUN",
                "machine_id": str(machine.pk),
                "matched_metrics": len(updates),
                "matched_by_label": matched_by_label,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
