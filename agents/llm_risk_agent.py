"""LLM-enhanced Risk/Critic Agent — receives all agent outputs and uses Llama to
generate deeper challenges, spot hidden risks, and stress-test assumptions."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .base import Agent
from .llm_client import LLMClient

SYSTEM_PROMPT = """You are the Risk/Critic agent in a product-launch war room.

You receive analysis from the Data Analyst, PM, and Marketing agents. Your job is
to be the skeptic — challenge assumptions, find hidden risks, and make sure the
team isn't fooling itself.

Specifically:
1. Challenge at least 3 assumptions the other agents made.
2. Build a risk register with severity, evidence, and concrete mitigations.
3. Identify what data is MISSING that would materially change the decision.
4. Describe a realistic worst-case scenario if the team proceeds.
5. Give your own recommendation: proceed / pause / rollback.

Return ONLY valid JSON (no markdown fences):
{
  "agent": "risk_critic",
  "challenges": [
    {"assumption": "<what was assumed>", "challenge": "<why it might be wrong>", "evidence_needed": "<what would confirm/deny>"}
  ],
  "risk_register": [
    {"id": "R-XXX-01", "title": "<risk>", "severity": "high|medium|low", "evidence": "<data>", "mitigation": "<action>"}
  ],
  "missing_evidence": ["<what data is missing>"],
  "worst_case_scenario": "<what happens if we proceed and things get worse>",
  "risk_score": 0.0-1.0,
  "recommendation": "proceed|pause|rollback",
  "dissent_note": "<if disagreeing with the majority, explain why>"
}

Be rigorous. Reference specific numbers from other agents' analyses. Your job is
to prevent a bad decision, not to agree with the room."""


class LLMRiskAgent(Agent):
    name = "Risk_Critic"

    def __init__(self, tracer, llm: LLMClient):
        super().__init__(tracer)
        self.llm = llm

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "challenging assumptions and building risk register (LLM-enhanced)")

        data_report = context["data_report"]
        mkt_report = context["marketing_report"]
        pm_report = context["pm_report"]
        release_notes = context["release_notes"]

        # ── Build deterministic risk register as baseline ──
        risks: List[Dict] = []
        for agg in data_report["aggregates"]:
            d = agg["delta_pct"]
            pre, post = agg["pre_mean"], agg["post_mean"]
            if agg["metric"] == "crash_rate" and d > 50:
                risks.append({
                    "id": "R-CRASH-01", "title": "Crash-rate regression post-launch",
                    "severity": "high",
                    "evidence": f"crash_rate {d:+.0f}% (pre {pre*100:.1f}% -> post {post*100:.1f}%)",
                    "mitigation": "Flip feature flag off for older Android; collect crash traces.",
                })
            if agg["metric"] == "api_p95_ms" and d > 20:
                risks.append({
                    "id": "R-LAT-01", "title": "Latency regression in aggregation service",
                    "severity": "high",
                    "evidence": f"api_p95_ms {d:+.0f}% (pre {pre:.0f}ms -> post {post:.0f}ms)",
                    "mitigation": "Profile agg-svc hot path; add caching; consider reverting.",
                })
            if agg["metric"] == "payment_success_rate" and d < -1.0:
                risks.append({
                    "id": "R-PAY-01", "title": "Payment success dip",
                    "severity": "high",
                    "evidence": f"payment_success_rate {d:+.1f}% (pre {pre*100:.1f}% -> post {post*100:.1f}%)",
                    "mitigation": "Pin payments SDK back to v3.1.4 via remote config.",
                })

        sev_weight = {"high": 0.4, "medium": 0.2, "low": 0.1}
        base_risk_score = min(1.0, sum(sev_weight.get(r["severity"], 0.1) for r in risks))

        # ── LLM reasoning layer ──
        # Build a comprehensive context for the LLM
        user_msg = (
            f"=== Data Analyst Report ===\n"
            f"Metric severity: {data_report['metric_severity']}\n"
            f"Concerning: {json.dumps(data_report['concerning_metrics'])}\n"
            f"Aggregates: {json.dumps(data_report['aggregates'])}\n\n"
            f"=== PM Report ===\n"
            f"Frame: {pm_report['go_no_go_frame']}\n"
            f"Blocking violations: {json.dumps(pm_report['blocking_violations'])}\n\n"
            f"=== Marketing Report ===\n"
            f"Perception: {mkt_report['perception']}\n"
            f"Sentiment: {json.dumps(mkt_report['sentiment'])}\n"
            f"Top issues: {json.dumps(mkt_report['issue_themes'][:3])}\n\n"
            f"=== Release Notes ===\n{release_notes}\n\n"
            f"=== Deterministic Risk Register ===\n{json.dumps(risks, indent=2)}\n"
            f"Deterministic risk score: {base_risk_score}\n"
        )

        # Check if any agent provided LLM analysis
        for key in ["data_report", "marketing_report", "pm_report"]:
            report = context.get(key, {})
            if "llm_analysis" in report:
                agent_name = key.replace("_report", "")
                user_msg += f"\n=== {agent_name} LLM Analysis ===\n{json.dumps(report['llm_analysis'])}\n"

        self.log("LLM_CALL", "generating challenges and enhanced risk analysis")
        llm_analysis = self.llm.ask_json(SYSTEM_PROMPT, user_msg, max_tokens=3000)
        self.log("LLM_RESULT", {
            "recommendation": llm_analysis.get("recommendation", "?"),
            "risk_score": llm_analysis.get("risk_score", "?"),
            "num_challenges": len(llm_analysis.get("challenges", [])),
        })

        # Merge: use LLM risk register if richer, else fallback to deterministic
        llm_risks = llm_analysis.get("risk_register", [])
        final_risks = llm_risks if len(llm_risks) >= len(risks) else risks

        # Use LLM challenges and missing evidence (these are where LLM truly adds value)
        challenges_raw = llm_analysis.get("challenges", [])
        # Normalize: could be list of dicts or list of strings
        challenges = []
        for c in challenges_raw:
            if isinstance(c, dict):
                challenges.append(c.get("challenge", c.get("assumption", str(c))))
            else:
                challenges.append(str(c))
        if not challenges:
            challenges = [
                "Is the crash spike device-specific (Android <=12) or global?",
                "Is payment failure rate concentrated on one gateway or distributed?",
                "Could DAU growth be masking a retention drop among pre-existing users?",
                "How much of the negative sentiment is about the UI redesign vs actual defects?",
            ]

        missing = llm_analysis.get("missing_evidence", [
            "Per-device crash breakdown (Android version, OS).",
            "Payment failure reason codes by gateway.",
            "Cohort retention (new vs returning) for post-launch days.",
            "Server-side error logs from agg-svc for latency outliers.",
        ])

        final_risk_score = llm_analysis.get("risk_score", base_risk_score)
        if isinstance(final_risk_score, str):
            try:
                final_risk_score = float(final_risk_score)
            except ValueError:
                final_risk_score = base_risk_score

        self.log("RISK_SCORE", final_risk_score)

        result = {
            "risk_register": final_risks,
            "challenges": challenges,
            "missing_evidence": missing,
            "risk_score": round(final_risk_score, 3),
            "llm_analysis": llm_analysis,
        }
        self.log("DONE", f"{len(final_risks)} risks, score={final_risk_score}")
        return result
