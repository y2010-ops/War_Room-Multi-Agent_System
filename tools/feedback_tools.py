"""Tools for feedback sentiment and issue clustering. Pure-Python keyword approach."""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Dict, List


POSITIVE_WORDS = {
    "love", "great", "nice", "smooth", "clean", "modern", "intuitive",
    "beautiful", "saved", "thanks", "good", "improvements", "working",
}
NEGATIVE_WORDS = {
    "crash", "crashed", "crashes", "slow", "slower", "freeze", "froze",
    "fail", "failed", "failure", "error", "unusable", "timeout", "timeouts",
    "abandon", "lost", "confusing", "unacceptable", "broken", "logout",
}

ISSUE_BUCKETS = {
    "crashes":      {"crash", "crashed", "crashes", "froze", "freeze", "force-close"},
    "latency":      {"slow", "slower", "latency", "timeout", "timeouts", "loading", "spinning", "loader"},
    "payments":     {"payment", "gateway", "visa", "checkout", "purchase"},
    "auth_session": {"logout", "session"},
    "ux_confusion": {"confusing", "cannot", "find"},
}


def load_feedback(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z\-]+", text.lower())


def summarize_sentiment(entries: List[Dict]) -> Dict:
    """Tool: summarize_sentiment — counts + ratio."""
    pos = neu = neg = 0
    for e in entries:
        toks = set(_tokenize(e["text"]))
        has_pos = bool(toks & POSITIVE_WORDS)
        has_neg = bool(toks & NEGATIVE_WORDS)
        if has_neg and not has_pos:
            neg += 1
        elif has_pos and not has_neg:
            pos += 1
        else:
            neu += 1
    total = max(1, len(entries))
    return {
        "total": len(entries),
        "positive": pos,
        "neutral": neu,
        "negative": neg,
        "negative_ratio": round(neg / total, 3),
        "positive_ratio": round(pos / total, 3),
    }


def cluster_issues(entries: List[Dict]) -> Dict:
    """Tool: cluster_issues — bucket complaints into themes with example quotes."""
    counts: Counter = Counter()
    examples: Dict[str, List[str]] = {k: [] for k in ISSUE_BUCKETS}
    for e in entries:
        toks = set(_tokenize(e["text"]))
        for bucket, keywords in ISSUE_BUCKETS.items():
            if toks & keywords:
                counts[bucket] += 1
                if len(examples[bucket]) < 2:
                    examples[bucket].append(e["text"])
    ranked = [
        {"theme": k, "count": c, "examples": examples[k]}
        for k, c in counts.most_common()
    ]
    return {"themes": ranked}
