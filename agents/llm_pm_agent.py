"""LLM-enhanced Product Manager Agent — same threshold checks, plus LLM-generated
user-impact assessment and go/no-go reasoning."""
from __future__ import annotations

import json
from typing import Any, Dict

from .base import Agent
from .llm_client import LLMClient
from .pm_agent import SUCCESS_CRITERIA  # reuse the same criteria

SYSTEM_PROMPT = """You are the Product Manager agent in a product-launch war room.

You receive metric aggregates and a list of success-criteria violations. Your job:

1. Assess user impact: who is affected, how severely, and what's the blast radius.
2. Frame the go/no-go decision with clear product reasoning (not just numbers).
3. Identify what users are losing if we roll back vs what they suffer if we continue.
4. Recommend: proceed / pause / rollback.

Return ONLY valid JSON (no markdown fences):
{
  "agent": "product_manager",
  "user_impact": {
    "severity": "low|medium|high|critical",
    "affected_segments": ["<who>"],
    "description": "<2-3 sentences>"
  },
  "go_no_go_reasoning": "<3-4 sentences explaining the product decision>",
  "tradeoff": "<what we lose by rolling back vs continuing>",
  "recommendation": "proceed|pause|rollback"
}"""


class LLMProductManagerAgent(Agent):
    name = "PM_Agent"

    def __init__(self, tracer, llm: LLMClient):
        super().__init__(tracer)
        self.llm = llm

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "defining success criteria and go/no-go frame (LLM-enhanced)")
        aggregates = context["aggregates"]

        # ── Deterministic threshold checks (same as base PM) ──
        violations = []
        for agg in aggregates:
            m = agg["metric"]
            crit = SUCCESS_CRITERIA.get(m)
            if not crit:
                continue
            violated, reason = False, ""
            post, pre = agg["post_mean"], agg["pre_mean"]
            if m == "crash_rate" and post > 1.5 * pre:
                violated, reason = True, f"post crash rate {post*100:.1f}% > 1.5x baseline {pre*100:.1f}%"
            elif m == "api_p95_ms" and post > 1.25 * pre:
                violated, reason = True, f"p95 latency {post:.0f}ms > 1.25x baseline {pre:.0f}ms"
            elif m == "payment_success_rate" and post < 0.98:
                violated, reason = True, f"payment success {post*100:.1f}% below 98.0% target"
            elif m == "activation_rate" and post < pre:
                violated, reason = True, "activation dropped post-launch"
            elif m == "d1_retention" and post < pre - 0.02:
                violated, reason = True, "D1 retention dropped >2pp"
            elif m == "adoption_funnel" and agg["latest"] < 0.50:
                violated, reason = True, f"adoption funnel only {agg['latest']*100:.0f}% at day 14"
            if violated:
                violations.append({"metric": m, "must_hold": crit["must_hold"], "reason": reason})

        blocking = [v for v in violations if v["must_hold"]]
        frame = "NO-GO (at least one must-hold criterion violated)" if blocking else "GO (criteria largely intact)"
        self.log("FRAME_DECISION", frame)

        # ── LLM reasoning layer ──
        user_msg = (
            f"Success criteria frame: {frame}\n"
            f"Blocking violations: {json.dumps(blocking)}\n"
            f"All violations: {json.dumps(violations)}\n"
            f"Aggregates: {json.dumps(aggregates)}\n"
        )
        self.log("LLM_CALL", "generating user-impact assessment and reasoning")
        llm_analysis = self.llm.ask_json(SYSTEM_PROMPT, user_msg)
        self.log("LLM_RESULT", {
            "recommendation": llm_analysis.get("recommendation", "?"),
            "severity": llm_analysis.get("user_impact", {}).get("severity", "?"),
        })

        result = {
            "success_criteria": SUCCESS_CRITERIA,
            "violations": violations,
            "blocking_violations": blocking,
            "go_no_go_frame": frame,
            "llm_analysis": llm_analysis,
        }
        self.log("DONE", f"{len(violations)} violations, {len(blocking)} blocking")
        return result
