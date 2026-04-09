"""Marketing/Comms Agent — sentiment, perception, messaging drafts."""
from __future__ import annotations

from typing import Any, Dict

from tools.feedback_tools import cluster_issues, summarize_sentiment

from .base import Agent


class MarketingAgent(Agent):
    name = "Marketing_Comms"

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log("START", "assessing user perception + drafting comms")
        feedback = context["feedback"]

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

        top_themes = [t["theme"] for t in issues["themes"][:3]]
        internal_msg = (
            f"War-room update: perception is {perception}. "
            f"Top themes: {', '.join(top_themes) if top_themes else 'none'}. "
            "Hold any outbound marketing pushes until engineering confirms stability."
        )
        external_msg = (
            "We're aware some users are experiencing issues with the latest update "
            "(crashes, slower performance, and payment retries for a subset of users). "
            "Our team is actively investigating and we'll share an update shortly. "
            "Thank you for your patience."
        )

        result = {
            "sentiment": sentiment,
            "issue_themes": issues["themes"],
            "perception": perception,
            "comms_draft": {
                "internal": internal_msg,
                "external": external_msg,
                "hold_marketing_push": neg_ratio >= 0.25,
            },
        }
        self.log("DONE", f"neg_ratio={neg_ratio}, themes={top_themes}")
        return result
