"""CLI entry point for the War-Room Multi-Agent System.

Usage:
    python main.py                          # deterministic mode (default)
    python main.py --llm                    # LLM-enhanced mode (Llama 3.3 via Groq)
    python main.py --llm --provider groq    # explicit provider
    python main.py --metrics data/metrics.csv --feedback data/feedback.json \
                   --notes data/release_notes.md --out output/decision.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make project root importable when run from any cwd.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.base import TraceLogger  # noqa: E402
from agents.coordinator import Coordinator  # noqa: E402
from tools.feedback_tools import load_feedback  # noqa: E402
from tools.metric_tools import load_metrics  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PurpleMerit War-Room Multi-Agent System")
    p.add_argument("--metrics", default="data/metrics.csv")
    p.add_argument("--feedback", default="data/feedback.json")
    p.add_argument("--notes", default="data/release_notes.md")
    p.add_argument("--out", default="output/decision.json")
    p.add_argument("--trace-out", default="output/trace.json")

    # LLM mode
    p.add_argument(
        "--llm", action="store_true",
        help="Enable LLM-enhanced mode (requires GROQ_API_KEY env var)",
    )
    p.add_argument(
        "--provider", default="groq", choices=["groq", "together", "openrouter"],
        help="LLM provider (default: groq)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    mode_label = "LLM-Enhanced (Llama 3.3)" if args.llm else "Deterministic"

    print()
    print("=" * 72)
    print("  PurpleMerit War-Room — Multi-Agent Launch Decision System")
    print(f"  Mode: {mode_label}")
    print("=" * 72)
    print()

    metrics_path = ROOT / args.metrics
    feedback_path = ROOT / args.feedback
    notes_path = ROOT / args.notes
    out_path = ROOT / args.out
    trace_path = ROOT / args.trace_out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    metric_rows = load_metrics(str(metrics_path))
    feedback = load_feedback(str(feedback_path))
    release_notes = notes_path.read_text(encoding="utf-8")

    tracer = TraceLogger()

    # Initialize LLM client if --llm flag is set.
    llm = None
    if args.llm:
        try:
            from agents.llm_client import LLMClient
            llm = LLMClient(provider=args.provider)
            print(f"  LLM: {llm.model} via {args.provider}")
            print()
        except (ImportError, EnvironmentError) as e:
            print(f"\n  !! {e}")
            print("  Falling back to deterministic mode.\n")
            llm = None

    coordinator = Coordinator(tracer, llm=llm)

    context = {
        "metric_rows": metric_rows,
        "feedback": feedback,
        "release_notes": release_notes,
    }

    final = coordinator.run(context)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2)
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(tracer.entries, f, indent=2)

    print()
    print("=" * 72)
    print(f"  DECISION : {final['decision']}")
    print(f"  CONFIDENCE: {final['confidence_score']}")
    print(f"  COMPOSITE SEVERITY: {final['composite_severity']}")
    print(f"  MODE: {final.get('mode', 'deterministic')}")
    print("=" * 72)
    print(f"  Full structured output -> {out_path}")
    print(f"  Full trace log         -> {trace_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
