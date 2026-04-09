"""Data Analyst Agent — calls metric tools, reports trends + anomalies + severity."""
from __future__ import annotations

from typing import Any, Dict, List

from tools.metric_tools import (
    aggregate_metric,
    detect_anomalies,
    overall_metric_severity,
    trend,
)

from .base import Agent


METRICS_TO_ANALYZE = [
    "activation_rate",
    "dau",
    "d1_retention",
    "crash_rate",
    "api_p95_ms",
    "payment_success_rate",
    "adoption_funnel",
]


class DataAnalystAgent(Agent):
    name = "Data_Analyst"

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "analyzing metric dashboard")
        rows = context["metric_rows"]

        aggregates: List[Dict] = []
        trends: List[Dict] = []
        anomalies: List[Dict] = []

        for m in METRICS_TO_ANALYZE:
            agg = aggregate_metric(rows, m)
            self.tool("aggregate_metric", {"metric": m}, agg)
            aggregates.append(agg)

            tr = trend(rows, m)
            self.tool("trend", {"metric": m}, tr)
            trends.append(tr)

            an = detect_anomalies(rows, m)
            self.tool("detect_anomalies", {"metric": m, "z_threshold": 1.8}, an)
            if an["anomalies"]:
                anomalies.append(an)

        severity = overall_metric_severity(aggregates)
        self.log("METRIC_SEVERITY", severity)

        # Identify the standout concerning metrics (rounded for display).
        concerning = []
        for agg in aggregates:
            m = agg["metric"]
            d = agg["delta_pct"]
            d_disp = f"{d:+.1f}%"
            if m in ("crash_rate", "api_p95_ms") and d > 15:
                concerning.append(f"{m} {d_disp} vs baseline")
            if m == "payment_success_rate" and d < -1.0:
                concerning.append(f"{m} {d_disp} vs baseline")
            if m == "d1_retention" and d < -1.5:
                concerning.append(f"{m} {d_disp} vs baseline")

        result = {
            "aggregates": aggregates,
            "trends": trends,
            "anomalies": anomalies,
            "metric_severity": severity,
            "concerning_metrics": concerning,
        }
        self.log("DONE", f"severity={severity}, concerning={len(concerning)}")
        return result
