"""Risk/Critic Agent — challenges assumptions and builds the risk register."""
from __future__ import annotations

from typing import Any, Dict, List

from .base import Agent


class RiskAgent(Agent):
    name = "Risk_Critic"

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "challenging assumptions and building risk register")

        data_report = context["data_report"]
        mkt_report = context["marketing_report"]
        pm_report = context["pm_report"]
        release_notes = context["release_notes"]

        risks: List[Dict] = []

        # Risk 1: crash rate regression.
        for agg in data_report["aggregates"]:
            d = agg["delta_pct"]
            pre, post = agg["pre_mean"], agg["post_mean"]
            if agg["metric"] == "crash_rate" and d > 50:
                risks.append({
                    "id": "R-CRASH-01",
                    "title": "Crash-rate regression post-launch",
                    "severity": "high",
                    "evidence": f"crash_rate {d:+.0f}% (pre {pre*100:.1f}% → post {post*100:.1f}%)",
                    "mitigation": "Flip feature flag `smart_dashboard_v2` off for older Android; collect fresh crash traces.",
                })
            if agg["metric"] == "api_p95_ms" and d > 20:
                risks.append({
                    "id": "R-LAT-01",
                    "title": "Latency regression in new aggregation service",
                    "severity": "high",
                    "evidence": f"api_p95_ms {d:+.0f}% (pre {pre:.0f}ms → post {post:.0f}ms)",
                    "mitigation": "Profile `agg-svc` hot path; add caching layer; consider reverting to legacy aggregator.",
                })
            if agg["metric"] == "payment_success_rate" and d < -1.0:
                risks.append({
                    "id": "R-PAY-01",
                    "title": "Payment success dip correlates with new SDK",
                    "severity": "high",
                    "evidence": f"payment_success_rate {d:+.1f}% (pre {pre*100:.1f}% → post {post*100:.1f}%)",
                    "mitigation": "Pin payments SDK back to v3.1.4 via remote config; add synthetic checks on gateway.",
                })
            if agg["metric"] == "d1_retention" and d < -2.0:
                risks.append({
                    "id": "R-RET-01",
                    "title": "D1 retention eroding",
                    "severity": "medium",
                    "evidence": f"d1_retention {d:+.1f}% vs baseline",
                    "mitigation": "Cross-check with perception: negative sentiment may be causing drop-off in first session.",
                })

        # Risk 2: sentiment-driven risk.
        if mkt_report["perception"] in ("hostile", "mixed-negative"):
            risks.append({
                "id": "R-COMMS-01",
                "title": f"User perception is {mkt_report['perception']}",
                "severity": "medium",
                "evidence": f"negative ratio {mkt_report['sentiment']['negative_ratio']} across {mkt_report['sentiment']['total']} entries",
                "mitigation": "Hold marketing push; publish a transparent status update; monitor social channels.",
            })

        # Risk 3: known release risks still unmitigated.
        if "agg-svc" in release_notes:
            risks.append({
                "id": "R-DEP-01",
                "title": "New `agg-svc` is serving prod traffic without full load test",
                "severity": "medium",
                "evidence": "release notes flag agg-svc as first-time prod workload",
                "mitigation": "Run load test against day-14 traffic profile; size up cluster; add circuit breaker.",
            })

        # Challenge list — things the war-room should not assume.
        challenges = [
            "Is the crash spike device-specific (Android <=12) or global? We lack per-device breakdown.",
            "Is payment failure rate concentrated on one gateway or distributed?",
            "Could DAU growth be masking a retention drop among pre-existing users?",
            "How much of the negative sentiment is about the UI redesign vs actual defects?",
        ]

        # Missing-evidence list — what would materially change the decision.
        missing_evidence = [
            "Per-device crash breakdown (Android version, OS).",
            "Payment failure reason codes by gateway.",
            "Cohort retention (new vs returning) for post-launch days.",
            "Server-side error logs from `agg-svc` for latency outliers.",
        ]

        # Risk score (0..1).
        sev_weight = {"high": 0.4, "medium": 0.2, "low": 0.1}
        risk_score = min(1.0, sum(sev_weight.get(r["severity"], 0.1) for r in risks))
        self.log("RISK_SCORE", risk_score)

        result = {
            "risk_register": risks,
            "challenges": challenges,
            "missing_evidence": missing_evidence,
            "risk_score": round(risk_score, 3),
        }
        self.log("DONE", f"{len(risks)} risks identified, score={risk_score}")
        return result
