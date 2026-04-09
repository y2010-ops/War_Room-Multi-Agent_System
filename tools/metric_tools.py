"""Programmatic tools that agents call to analyze the metrics dashboard.

Each function is pure and deterministic so traces are reproducible.
"""
from __future__ import annotations

import csv
import math
from statistics import mean, pstdev
from typing import Dict, List


# Direction of "bad": for some metrics higher is worse, for others lower is worse.
METRIC_DIRECTION = {
    "activation_rate":     "higher_better",
    "dau":                 "higher_better",
    "d1_retention":        "higher_better",
    "crash_rate":          "lower_better",
    "api_p95_ms":          "lower_better",
    "payment_success_rate":"higher_better",
    "adoption_funnel":     "higher_better",
}


def load_metrics(path: str) -> List[Dict]:
    rows: List[Dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {"day": int(row["day"]), "phase": row["phase"]}
            for k, v in row.items():
                if k in ("day", "phase"):
                    continue
                parsed[k] = float(v)
            rows.append(parsed)
    return rows


def aggregate_metric(rows: List[Dict], metric: str) -> Dict:
    """Tool: aggregate_metric — pre/post launch baseline + delta."""
    pre = [r[metric] for r in rows if r["phase"] == "pre"]
    post = [r[metric] for r in rows if r["phase"] == "post"]
    pre_mean = mean(pre) if pre else 0.0
    post_mean = mean(post) if post else 0.0
    delta_pct = ((post_mean - pre_mean) / pre_mean * 100.0) if pre_mean else 0.0
    return {
        "metric": metric,
        "pre_mean": round(pre_mean, 4),
        "post_mean": round(post_mean, 4),
        "delta_pct": round(delta_pct, 2),
        "latest": round(post[-1] if post else pre[-1], 4),
    }


def trend(rows: List[Dict], metric: str) -> Dict:
    """Tool: trend — slope of post-launch values via least squares."""
    post = [(r["day"], r[metric]) for r in rows if r["phase"] == "post"]
    if len(post) < 2:
        return {"metric": metric, "slope": 0.0, "direction": "flat"}
    xs = [p[0] for p in post]
    ys = [p[1] for p in post]
    x_mean, y_mean = mean(xs), mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs) or 1.0
    slope = num / den
    direction = "rising" if slope > 0 else ("falling" if slope < 0 else "flat")
    return {"metric": metric, "slope": round(slope, 5), "direction": direction}


def detect_anomalies(rows: List[Dict], metric: str, z_threshold: float = 1.8) -> Dict:
    """Tool: detect_anomalies — z-score outliers across the full window."""
    values = [r[metric] for r in rows]
    mu = mean(values)
    sigma = pstdev(values) or 1e-9
    anomalies = []
    for r in rows:
        z = (r[metric] - mu) / sigma
        if abs(z) >= z_threshold:
            anomalies.append({"day": r["day"], "value": r[metric], "z": round(z, 2)})
    return {"metric": metric, "mean": round(mu, 4), "stdev": round(sigma, 4), "anomalies": anomalies}


def severity_for(metric: str, delta_pct: float) -> float:
    """Convert a pre/post delta into a 0..1 severity score given metric direction."""
    direction = METRIC_DIRECTION.get(metric, "higher_better")
    bad_pct = -delta_pct if direction == "higher_better" else delta_pct
    if bad_pct <= 0:
        return 0.0
    # Saturate at +100% bad change.
    return min(1.0, bad_pct / 100.0)


def overall_metric_severity(aggregates: List[Dict]) -> float:
    """Aggregate per-metric severities into a single 0..1 score (max-pooled + averaged)."""
    if not aggregates:
        return 0.0
    sevs = [severity_for(a["metric"], a["delta_pct"]) for a in aggregates]
    avg = sum(sevs) / len(sevs)
    peak = max(sevs)
    return round(0.5 * avg + 0.5 * peak, 3)
