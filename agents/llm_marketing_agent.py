"""LLM-enhanced Marketing/Comms Agent — same sentiment tools, plus LLM-generated
perception analysis and polished communication drafts."""
from __future__ import annotations

import json
from typing import Any, Dict

from tools.feedback_tools import cluster_issues, summarize_sentiment
from .base import Agent
from .llm_client import LLMClient

SYSTEM_PROMPT = """You are the Marketing/Comms agent in a product-launch war room.

You receive sentiment analysis results, issue clusters, and raw user feedback.
Your job:

1. Assess the overall customer perception and brand risk.
2. Identify any viral-risk signals (social media complaints gaining traction).
3. Draft a concise INTERNAL status update for the engineering team.
4. Draft a concise EXTERNAL customer-facing message (transparent, empathetic, specific).
5. Recommend: proceed / pause / rollback.

Return ONLY valid JSON (no markdown fences):
{
  "agent": "marketing_comms",
  "perception": "positive|mixed|mixed-negative|hostile",
  "brand_risk": "low|medium|high|critical",
  "brand_risk_reasoning": "<1-2 sentences>",
  "comms_draft": {
    "internal": "<2-3 sentence status update for engineering>",
    "external": "<3-4 sentence customer-facing message>",
    "hold_marketing_push": true/false
  },
  "recommendation": "proceed|pause|rollback",
  "recommendation_reasoning": "<2 sentences>"
}

Write the comms drafts in a natural, human tone — not corporate boilerplate."""


class LLMMarketingAgent(Agent):
    name = "Marketing_Comms"

    def __init__(self, tracer, llm: LLMClient):
        super().__init__(tracer)
        self.llm = llm

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "assessing user perception + drafting comms (LLM-enhanced)")
        feedback = context["feedback"]

        # ── Deterministic tools ──
        sentiment = summarize_sentiment(feedback)
        self.tool("summarize_sentiment", {"n": len(feedback)}, sentiment)

        issues = cluster_issues(feedback)
        self.tool("cluster_issues", {"n": len(feedback)}, {"themes": len(issues["themes"])})

        neg_ratio = sentiment["negative_ratio"]
        if neg_ratio >= 0.4:
            perception = "hostile"
        elif neg_ratio >= 0.25:
            perception = "mixed-negative"
        elif neg_ratio >= 0.15:
            perception = "mixed"
        else:
            perception = "positive"
        self.log("PERCEPTION", perception)

        # ── LLM reasoning layer ──
        # Give the LLM a sample of actual feedback text for richer comms
        feedback_sample = [e["text"] for e in feedback[:15]]
        user_msg = (
            f"Sentiment: {json.dumps(sentiment)}\n"
            f"Issue clusters: {json.dumps(issues['themes'][:5])}\n"
            f"Deterministic perception: {perception}\n\n"
            f"Sample feedback (first 15):\n" +
            "\n".join(f"  - {t}" for t in feedback_sample)
        )
        self.log("LLM_CALL", "generating perception analysis and comms drafts")
        llm_analysis = self.llm.ask_json(SYSTEM_PROMPT, user_msg)
        self.log("LLM_RESULT", {
            "recommendation": llm_analysis.get("recommendation", "?"),
            "perception": llm_analysis.get("perception", "?"),
        })

        # Use LLM comms if available, fallback to templates
        comms = llm_analysis.get("comms_draft", {})
        if not comms or comms.get("_parse_error"):
            top_themes = [t["theme"] for t in issues["themes"][:3]]
            comms = {
                "internal": (
                    f"War-room update: perception is {perception}. "
                    f"Top themes: {', '.join(top_themes)}. "
                    "Hold any outbound marketing pushes until engineering confirms stability."
                ),
                "external": (
                    "We're aware some users are experiencing issues with the latest update. "
                    "Our team is actively investigating and we'll share an update shortly."
                ),
                "hold_marketing_push": neg_ratio >= 0.25,
            }

        result = {
            "sentiment": sentiment,
            "issue_themes": issues["themes"],
            "perception": llm_analysis.get("perception", perception),
            "comms_draft": comms,
            "llm_analysis": llm_analysis,
        }
        self.log("DONE", f"neg_ratio={neg_ratio}")
        return result
