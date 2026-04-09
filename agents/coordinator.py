"""Coordinator / Orchestrator — drives the war-room workflow and produces final JSON.

Supports two modes:
  - Deterministic (default): rule-based agents, zero dependencies, instant.
  - LLM-enhanced (--llm):    same tools + Llama 3.3 reasoning layer via Groq.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Agent, TraceLogger
from .data_analyst import DataAnalystAgent
from .marketing_agent import MarketingAgent
from .pm_agent import ProductManagerAgent
from .risk_agent import RiskAgent


class Coordinator(Agent):
    name = "Coordinator"

    def __init__(self, tracer: TraceLogger, llm=None):
        super().__init__(tracer)
        self.llm = llm

        if llm is not None:
            # LLM-enhanced agents: same tools, richer reasoning.
            from .llm_data_analyst import LLMDataAnalystAgent
            from .llm_marketing_agent import LLMMarketingAgent
            from .llm_pm_agent import LLMProductManagerAgent
            from .llm_risk_agent import LLMRiskAgent
            self.data_analyst = LLMDataAnalystAgent(tracer, llm)
            self.marketing = LLMMarketingAgent(tracer, llm)
            self.pm = LLMProductManagerAgent(tracer, llm)
            self.risk = LLMRiskAgent(tracer, llm)
            self.log("MODE", "LLM-enhanced (Llama 3.3 via Groq)")
        else:
            # Deterministic agents: pure Python, no LLM calls.
            self.data_analyst = DataAnalystAgent(tracer)
            self.marketing = MarketingAgent(tracer)
            self.pm = ProductManagerAgent(tracer)
            self.risk = RiskAgent(tracer)
            self.log("MODE", "Deterministic (rule-based)")

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------
    @staticmethod
    def _decide(metric_sev: float, neg_ratio: float, risk_score: float, blocking: int) -> Dict[str, Any]:
        # Weighted composite 0..1.
        composite = 0.5 * metric_sev + 0.3 * neg_ratio + 0.2 * risk_score
        composite = round(composite, 3)

        # Hard rule: any must-hold violation auto-promotes severity.
        if blocking >= 2 or composite >= 0.65:
            decision = "Roll Back"
        elif blocking >= 1 or composite >= 0.35:
            decision = "Pause"
        else:
            decision = "Proceed"

        # Confidence: high when signals align, lower when they conflict.
        signals = [metric_sev, neg_ratio, risk_score]
        spread = max(signals) - min(signals)
        confidence = round(max(0.4, 1.0 - spread), 2)
        return {"decision": decision, "composite_score": composite, "confidence": confidence}

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("ORCHESTRATION_START", "war-room convened")

        # Step 1: Data Analyst profiles the dashboard.
        self.log("HANDOFF", "-> Data Analyst")
        data_report = self.data_analyst.run(context)

        # Step 2: PM frames go/no-go against success criteria (needs aggregates).
        self.log("HANDOFF", "Data Analyst -> PM")
        pm_report = self.pm.run({"aggregates": data_report["aggregates"]})

        # Step 3: Marketing assesses perception.
        self.log("HANDOFF", "PM -> Marketing/Comms")
        marketing_report = self.marketing.run(context)

        # Step 4: Risk/Critic challenges all reports.
        self.log("HANDOFF", "Marketing -> Risk/Critic")
        risk_report = self.risk.run({
            "data_report": data_report,
            "marketing_report": marketing_report,
            "pm_report": pm_report,
            "release_notes": context["release_notes"],
        })

        # Step 5: Coordinator computes the decision.
        self.log("HANDOFF", "Risk/Critic -> Coordinator (final synthesis)")
        decision = self._decide(
            metric_sev=data_report["metric_severity"],
            neg_ratio=marketing_report["sentiment"]["negative_ratio"],
            risk_score=risk_report["risk_score"],
            blocking=len(pm_report["blocking_violations"]),
        )
        self.log("DECISION", decision)

        # Step 6: Build 24-48h action plan.
        action_plan = self._build_action_plan(decision["decision"], data_report, risk_report)

        # Step 7: Rationale drivers.
        rationale = self._build_rationale(data_report, marketing_report, pm_report)

        final_output = {
            "decision": decision["decision"],
            "confidence_score": decision["confidence"],
            "composite_severity": decision["composite_score"],
            "rationale": rationale,
            "success_criteria_frame": pm_report["go_no_go_frame"],
            "blocking_violations": pm_report["blocking_violations"],
            "metric_summary": {
                "severity": data_report["metric_severity"],
                "concerning_metrics": data_report["concerning_metrics"],
                "aggregates": data_report["aggregates"],
                "anomalies": data_report["anomalies"],
            },
            "feedback_summary": {
                "sentiment": marketing_report["sentiment"],
                "perception": marketing_report["perception"],
                "top_issue_themes": marketing_report["issue_themes"][:5],
            },
            "risk_register": risk_report["risk_register"],
            "action_plan_24_48h": action_plan,
            "communication_plan": marketing_report["comms_draft"],
            "what_would_increase_confidence": risk_report["missing_evidence"],
            "critic_challenges": risk_report["challenges"],
        }

        # Include LLM agent reasoning when running in enhanced mode.
        if self.llm is not None:
            final_output["mode"] = "llm-enhanced"
            llm_insights = {}
            for label, report in [("data_analyst", data_report),
                                  ("pm", pm_report),
                                  ("marketing", marketing_report),
                                  ("risk_critic", risk_report)]:
                if "llm_analysis" in report:
                    llm_insights[label] = report["llm_analysis"]
            if llm_insights:
                final_output["llm_agent_reasoning"] = llm_insights
        else:
            final_output["mode"] = "deterministic"

        self.log("ORCHESTRATION_DONE", f"decision={decision['decision']}")
        return final_output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_rationale(data_report, marketing_report, pm_report):
        drivers = []
        for c in data_report["concerning_metrics"]:
            drivers.append({"type": "metric", "detail": c})
        for v in pm_report["blocking_violations"]:
            drivers.append({"type": "criterion", "detail": v["reason"]})
        drivers.append({
            "type": "feedback",
            "detail": (
                f"{marketing_report['sentiment']['negative']} negative / "
                f"{marketing_report['sentiment']['total']} entries; "
                f"perception={marketing_report['perception']}"
            ),
        })
        return drivers

    @staticmethod
    def _build_action_plan(decision: str, data_report, risk_report):
        actions = []
        if decision == "Roll Back":
            actions.append({
                "window": "0-2h", "owner": "Release Manager",
                "action": "Flip `smart_dashboard_v2` flag OFF globally and initiate rollback runbook.",
            })
        elif decision == "Pause":
            actions.append({
                "window": "0-4h", "owner": "Release Manager",
                "action": "Pause progressive rollout at current %; no new cohorts until metrics stabilize.",
            })
        else:
            actions.append({
                "window": "0-24h", "owner": "Release Manager",
                "action": "Continue rollout with tightened monitoring (1h SLO review cadence).",
            })

        # Always add investigation actions tied to the top risks.
        for r in risk_report["risk_register"][:4]:
            actions.append({
                "window": "0-24h",
                "owner": "Engineering Lead" if "LAT" in r["id"] or "DEP" in r["id"]
                         else ("Payments Team" if "PAY" in r["id"]
                               else ("Mobile Team" if "CRASH" in r["id"]
                                     else "On-call")),
                "action": f"{r['title']}: {r['mitigation']}",
            })

        actions.append({
            "window": "12-24h", "owner": "Data Team",
            "action": "Publish per-device crash breakdown and payment failure reason codes (identified as missing evidence).",
        })
        actions.append({
            "window": "24-48h", "owner": "Product Manager",
            "action": "Reconvene war room with refreshed dashboard + cohort retention to re-evaluate decision.",
        })
        return actions
