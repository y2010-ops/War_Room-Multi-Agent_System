"""Base agent + shared trace logger used by the orchestrator."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TraceLogger:
    """Append-only log capturing every agent step and tool call."""
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, actor: str, action: str, detail: Any = None) -> None:
        entry = {
            "t": round(time.time(), 3),
            "actor": actor,
            "action": action,
            "detail": detail,
        }
        self.entries.append(entry)
        # Human-readable console trace (also required by the spec).
        detail_str = "" if detail is None else f" :: {detail}"
        print(f"[TRACE] {actor:<18} | {action}{detail_str}")

    def tool_call(self, actor: str, tool: str, args: Dict[str, Any], result_summary: Any) -> None:
        self.log(actor, f"TOOL_CALL::{tool}", {"args": args, "result": result_summary})


class Agent:
    """Minimal base class. Every agent exposes a `run(context)` method."""

    name: str = "Agent"

    def __init__(self, tracer: TraceLogger):
        self.tracer = tracer

    def log(self, action: str, detail: Any = None) -> None:
        self.tracer.log(self.name, action, detail)

    def tool(self, tool_name: str, args: Dict[str, Any], result: Any) -> None:
        # Keep the result summary compact so traces stay readable.
        if isinstance(result, dict):
            summary = {k: result[k] for k in list(result.keys())[:4]}
        elif isinstance(result, list):
            summary = {"len": len(result)}
        else:
            summary = result
        self.tracer.tool_call(self.name, tool_name, args, summary)

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - override
        raise NotImplementedError
