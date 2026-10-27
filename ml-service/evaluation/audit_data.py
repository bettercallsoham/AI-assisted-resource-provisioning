"""Read-only provenance and quality summary for the existing telemetry CSVs."""

import argparse
import csv
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path


FIELDS = ("request_rate", "cpu_utilization", "memory_utilization", "network_throughput", "response_latency")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def audit(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"timestamp", *FIELDS}.issubset(reader.fieldnames):
            raise ValueError(f"{path}: required columns missing")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: empty dataset")
    missing = {field: 0 for field in ("timestamp", *FIELDS)}
    values = {field: [] for field in FIELDS}
    timestamps = []
    invalid = 0
    for row in rows:
        try:
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamps.append(timestamp.astimezone(timezone.utc))
        except (TypeError, ValueError):
            missing["timestamp"] += 1
        for field in FIELDS:
            try:
                value = float(row[field])
                if not math.isfinite(value):
                    raise ValueError
                values[field].append(value)
            except (TypeError, ValueError):
                missing[field] += 1
                invalid += 1
    ordered = sorted(timestamps)
    intervals = [(later - earlier).total_seconds() for earlier, later in zip(ordered, ordered[1:])]
    original_intervals = [(later - earlier).total_seconds()
                          for earlier, later in zip(timestamps, timestamps[1:])]
    metrics = {}
    for field, series in values.items():
        if not series:
            continue
        metrics[field] = {
            "min": min(series), "median": statistics.median(series), "max": max(series),
            "mean": statistics.mean(series), "p75": percentile(series, 0.75),
            "zeros": sum(value == 0 for value in series), "unique": len(set(series)),
            "negative": sum(value < 0 for value in series),
        }
        if field in ("cpu_utilization", "memory_utilization"):
            metrics[field]["above_100_percent"] = sum(value > 100 for value in series)
    segments = {}
    if len(rows) >= 100 and all(len(series) == len(rows) for series in values.values()):
        train_end = int(len(rows) * 0.7)
        validation_end = train_end + int(len(rows) * 0.15)
        for label, start, end in (("train", 0, train_end),
                                  ("validation", train_end, validation_end),
                                  ("test", validation_end, len(rows))):
            segments[label] = {
                field: {"median": statistics.median(series[start:end]),
                        "above_train_p75": sum(
                            value >= percentile(series[:train_end], 0.75)
                            for value in series[start:end])}
                for field, series in values.items()
            }
    return {
        "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows), "columns": reader.fieldnames, "invalid_numeric_cells": invalid,
        "missing_or_nonfinite": missing, "duplicate_timestamps": len(timestamps) - len(set(timestamps)),
        "out_of_order_adjacent_timestamps": sum(item <= 0 for item in original_intervals),
        "first_utc": ordered[0].isoformat() if ordered else None,
        "last_utc": ordered[-1].isoformat() if ordered else None,
        "interval_seconds": ({"min": min(intervals), "median": statistics.median(intervals),
                              "max": max(intervals), "near_5s": sum(4 <= item <= 6 for item in intervals)}
                             if intervals else None),
        "metrics": metrics,
        "chronological_segments": segments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.paths], indent=2))


if __name__ == "__main__":
    main()
