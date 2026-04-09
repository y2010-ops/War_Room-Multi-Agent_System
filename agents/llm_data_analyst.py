"""LLM-enhanced Data Analyst — calls the same deterministic tools, then uses
Llama to interpret the results and produce a richer narrative analysis."""
from __future__ import annotations

import json
from typing import Any, Dict

from tools.metric_tools import aggregate_metric, detect_anomalies, trend, overall_metric_severity
from .base import Agent
from .llm_client import LLMClient

METRICS_TO_ANALYZE = [
    "activation_rate", "dau", "d1_retention", "crash_rate",
    "api_p95_ms", "payment_success_rate", "adoption_funnel",
]

SYSTEM_PROMPT = """You are the Data Analyst agent in a product-launch war room.

You have been given the results of three deterministic tools (aggregate_metric,
trend, detect_anomalies) for every tracked metric. Your job:

1. Summarize the quantitative health of each metric in 1-2 sentences.
2. Identify the 2-3 most concerning trends and explain WHY they matter.
3. State your confidence level (low/medium/high) in the data quality.
4. Give a clear recommendation: proceed / pause / rollback.

Return ONLY a valid JSON object with this structure (no markdown fences):
{
  "agent": "data_analyst",
  "metric_health": [
    {"metric": "<name>", "status": "healthy|degraded|critical", "detail": "<1-2 sentences>"}
  ],
  "critical_findings": ["<finding1>", "<finding2>"],
  "confidence": "low|medium|high",
  "confidence_reasoning": "<why>",
  "recommendation": "proceed|pause|rollback",
  "recommendation_reasoning": "<2-3 sentences>"
}

Be precise with numbers. Reference actual values from the tool outputs."""


class LLMDataAnalystAgent(Agent):
    name = "Data_Analyst"

    def __init__(self, tracer, llm: LLMClient):
        super().__init__(tracer)
        self.llm = llm

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "analyzing metric dashboard (LLM-enhanced)")
        rows = context["metric_rows"]

        aggregates, trends, anomalies = [], [], []
        tool_context_parts = []

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

            tool_context_parts.append(
                f"--- {m} ---\n"
                f"Aggregate: pre={agg['pre_mean']}, post={agg['post_mean']}, delta={agg['delta_pct']}%\n"
                f"Trend: slope={tr['slope']}, direction={tr['direction']}\n"
                f"Anomalies: {len(an['anomalies'])} found"
            )

        severity = overall_metric_severity(aggregates)
        self.tool("overall_metric_severity", {}, severity)

        # ── LLM interpretation ──
        user_msg = (
            f"Overall metric severity score: {severity} (0=healthy, 1=critical)\n\n"
            + "\n\n".join(tool_context_parts)
        )
        self.log("LLM_CALL", "interpreting tool outputs")
        llm_analysis = self.llm.ask_json(SYSTEM_PROMPT, user_msg)
        self.log("LLM_RESULT", {
            "recommendation": llm_analysis.get("recommendation", "?"),
            "confidence": llm_analysis.get("confidence", "?"),
        })

        # Merge deterministic + LLM outputs
        concerning = []
        for agg in aggregates:
            m, d = agg["metric"], agg["delta_pct"]
            if m in ("crash_rate", "api_p95_ms") and d > 15:
                concerning.append(f"{m} {d:+.1f}% vs baseline")
            if m == "payment_success_rate" and d < -1.0:
                concerning.append(f"{m} {d:+.1f}% vs baseline")
            if m == "d1_retention" and d < -1.5:
                concerning.append(f"{m} {d:+.1f}% vs baseline")

        result = {
            "aggregates": aggregates,
            "trends": trends,
            "anomalies": anomalies,
            "metric_severity": severity,
            "concerning_metrics": concerning,
            "llm_analysis": llm_analysis,
        }
        self.log("DONE", f"severity={severity}, concerning={len(concerning)}")
        return result
