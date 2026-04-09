"""Product Manager Agent — defines success criteria and frames go/no-go."""
from __future__ import annotations

from typing import Any, Dict

from .base import Agent


# Launch success criteria (targets the feature needs to uphold).
SUCCESS_CRITERIA = {
    "activation_rate":      {"target": ">= pre baseline", "must_hold": True},
    "crash_rate":           {"target": "<= 1.5x pre baseline", "must_hold": True},
    "api_p95_ms":           {"target": "<= 1.25x pre baseline", "must_hold": True},
    "payment_success_rate": {"target": ">= 0.98", "must_hold": True},
    "adoption_funnel":      {"target": ">= 0.50 by day 14", "must_hold": False},
    "d1_retention":         {"target": ">= pre baseline - 0.02", "must_hold": False},
}


class ProductManagerAgent(Agent):
    name = "PM_Agent"

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "defining success criteria and go/no-go frame")
        aggregates = context["aggregates"]  # produced earlier by Data Analyst? No — PM declares thresholds first.

        violations = []
        for agg in aggregates:
            m = agg["metric"]
            crit = SUCCESS_CRITERIA.get(m)
            if not crit:
                continue
            violated = False
            reason = ""
            post, pre = agg["post_mean"], agg["pre_mean"]
            if m == "crash_rate":
                if post > 1.5 * pre:
                    violated, reason = True, f"post crash rate {post*100:.1f}% > 1.5x baseline {pre*100:.1f}%"
            elif m == "api_p95_ms":
                if post > 1.25 * pre:
                    violated, reason = True, f"p95 latency {post:.0f}ms > 1.25x baseline {pre:.0f}ms"
            elif m == "payment_success_rate":
                if post < 0.98:
                    violated, reason = True, f"payment success {post*100:.1f}% below 98.0% target"
            elif m == "activation_rate":
                if post < pre:
                    violated, reason = True, "activation dropped post-launch"
            elif m == "d1_retention":
                if post < pre - 0.02:
                    violated, reason = True, "D1 retention dropped >2pp"
            elif m == "adoption_funnel":
                if agg["latest"] < 0.50:
                    violated, reason = True, f"adoption funnel only {agg['latest']*100:.0f}% at day 14"

            if violated:
                violations.append({"metric": m, "must_hold": crit["must_hold"], "reason": reason})

        blocking = [v for v in violations if v["must_hold"]]
        frame = "NO-GO (at least one must-hold criterion violated)" if blocking else "GO (criteria largely intact)"

        self.log("FRAME_DECISION", frame)
        result = {
            "success_criteria": SUCCESS_CRITERIA,
            "violations": violations,
            "blocking_violations": blocking,
            "go_no_go_frame": frame,
        }
        self.log("DONE", f"{len(violations)} violations, {len(blocking)} blocking")
        return result
