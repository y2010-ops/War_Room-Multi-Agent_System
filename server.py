"""Tiny stdlib HTTP server that powers the war-room visualization.

Endpoints:
    GET  /             -> frontend/index.html
    GET  /style.css    -> frontend/style.css
    GET  /app.js       -> frontend/app.js
    GET  /api/run      -> runs the Coordinator in-process and returns JSON:
                          { "decision": <final output>, "trace": <trace entries> }
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.base import TraceLogger  # noqa: E402
from agents.coordinator import Coordinator  # noqa: E402
from tools.feedback_tools import load_feedback  # noqa: E402
from tools.metric_tools import load_metrics  # noqa: E402

FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"

STATIC_FILES = {
    "/":            ("frontend/index.html", "text/html; charset=utf-8"),
    "/index.html":  ("frontend/index.html", "text/html; charset=utf-8"),
    "/style.css":   ("frontend/style.css",  "text/css; charset=utf-8"),
    "/app.js":      ("frontend/app.js",     "application/javascript; charset=utf-8"),
}


def run_simulation(use_llm: bool = False) -> dict:
    """Execute the full war-room workflow and return final decision + trace."""
    metric_rows = load_metrics(str(DATA_DIR / "metrics.csv"))
    feedback = load_feedback(str(DATA_DIR / "feedback.json"))
    release_notes = (DATA_DIR / "release_notes.md").read_text(encoding="utf-8")

    llm = None
    if use_llm:
        try:
            from agents.llm_client import LLMClient
            llm = LLMClient()
        except (ImportError, EnvironmentError):
            llm = None  # fallback to deterministic

    tracer = TraceLogger()
    coordinator = Coordinator(tracer, llm=llm)
    context = {
        "metric_rows": metric_rows,
        "feedback": feedback,
        "release_notes": release_notes,
    }
    decision = coordinator.run(context)
    return {
        "decision": decision,
        "trace": tracer.entries,
        "metric_rows": metric_rows,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep console clean
        sys.stderr.write("[HTTP] " + (fmt % args) + "\n")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, rel_path: str, content_type: str) -> None:
        fp = ROOT / rel_path
        if not fp.exists():
            self.send_error(404, f"Not found: {rel_path}")
            return
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/api/run":
            use_llm = "llm=1" in self.path or "llm=true" in self.path.lower()
            try:
                result = run_simulation(use_llm=use_llm)
                self._send_json(200, result)
            except Exception as exc:  # pragma: no cover
                self._send_json(500, {"error": str(exc)})
            return

        if path in STATIC_FILES:
            rel, ctype = STATIC_FILES[path]
            self._send_file(rel, ctype)
            return

        self.send_error(404, f"Not found: {path}")


def main() -> int:
    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), Handler)
    print("=" * 72)
    print(f"  War-Room Visualizer running at  http://{host}:{port}")
    print("  Open that URL in a browser and click 'Convene War Room'")
    print("  Press Ctrl+C to stop.")
    print("=" * 72)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
