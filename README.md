# War-Room — Multi-Agent Launch Decision System

A **multi-agent system** that simulates a cross-functional "war room" during a
product launch. It ingests a mock metrics dashboard and user feedback, runs
coordinated agents (each calling programmatic tools), and produces a structured
launch decision — **Proceed / Pause / Roll Back** — with rationale, risk
register, 24–48 h action plan, and communication plan.

The system ships with **two execution modes**, toggled by a single flag:

| Mode | Flag | Dependencies | Speed | Best for |
|---|---|---|---|---|
| **Deterministic** | *(default)* | Python 3.9+ stdlib only | Instant (~50 ms) | Production alerting, auditable decisions, reproducibility |
| **LLM-Enhanced** | `--llm` | + `openai` + Groq API key | ~15–30 s | Richer reasoning, natural-language comms drafts, deeper risk analysis |

Both modes use the **same deterministic tools** for metric analysis and
sentiment classification. The LLM layer (Llama 3.3 70B via Groq) adds an
interpretation and reasoning step on top — it does not replace the analytical
pipeline. If the LLM is unavailable, the system falls back to deterministic
mode gracefully.

---

## Architecture

```
                  ┌────────────────────┐
                  │    Coordinator     │  orchestrates workflow + final decision
                  └─────────┬──────────┘
              ┌─────────────┼─────────────────┬──────────────┐
              ▼             ▼                 ▼              ▼
       Data Analyst       PM Agent      Marketing/Comms   Risk/Critic
              │             │                 │              │
              ▼             ▼                 ▼              ▼
   metric_tools.py     (uses aggs)    feedback_tools.py   (critiques all)
   • aggregate_metric                 • summarize_sentiment
   • trend (least sq.)                • cluster_issues
   • detect_anomalies (z)
```

### Agent Interaction Flow

1. **Coordinator** dispatches agents in sequence with explicit handoffs.
2. **Data Analyst** calls 3 metric tools (aggregate, trend, anomaly) for each of 7 metrics → produces severity score.
3. **PM Agent** evaluates metric aggregates against predefined success criteria → frames go/no-go.
4. **Marketing/Comms** calls 2 feedback tools (sentiment, clustering) → classifies perception, drafts communications.
5. **Risk/Critic** receives ALL prior reports → challenges assumptions, builds risk register, identifies missing evidence.
6. **Coordinator** applies weighted decision rule → synthesizes final JSON output.

### Agents

| Agent | Responsibility | Tools Called |
|---|---|---|
| **Data Analyst** | Quantitative analysis: baselines, trends, anomalies, severity scoring | `aggregate_metric`, `trend`, `detect_anomalies` |
| **PM** | Success criteria definition, threshold violations, go/no-go framing | *(consumes Data Analyst aggregates)* |
| **Marketing/Comms** | Sentiment analysis, perception classification, comms drafting | `summarize_sentiment`, `cluster_issues` |
| **Risk/Critic** | Assumption challenges, risk register, missing evidence, worst-case scenarios | *(consumes all prior outputs)* |
| **Coordinator** | Orchestration, weighted decision rule, action plan generation | *(orchestrates all agents)* |

### Tools (Called Programmatically by Agents)

All tools are **pure, deterministic functions** — no LLM involved. They return structured data that agents consume.

| # | Tool | Module | What It Does |
|---|---|---|---|
| 1 | `aggregate_metric` | `tools/metric_tools.py` | Pre/post-launch baselines + delta % |
| 2 | `trend` | `tools/metric_tools.py` | Least-squares slope across post-launch window |
| 3 | `detect_anomalies` | `tools/metric_tools.py` | Z-score outlier detection (threshold=1.8σ) |
| 4 | `summarize_sentiment` | `tools/feedback_tools.py` | Keyword-based positive/neutral/negative classification |
| 5 | `cluster_issues` | `tools/feedback_tools.py` | Groups complaints into themes (crashes, latency, payments, etc.) |

### Decision Rule

```
composite = 0.5 × metric_severity + 0.3 × negative_ratio + 0.2 × risk_score
```

- `composite ≥ 0.65` **or** ≥ 2 must-hold violations → **Roll Back**
- `composite ≥ 0.35` **or** ≥ 1 must-hold violation  → **Pause**
- otherwise → **Proceed**

Confidence is derived from how tightly the three signals agree (high agreement = high confidence).

---

## Inputs (Mock Dashboard)

| File | Description |
|---|---|
| `data/metrics.csv` | 14 days × 7 metrics. Days 1–7 pre-launch baseline; days 8–14 post-launch. Includes: activation rate, DAU, D1 retention, crash rate, API p95 latency, payment success rate, feature adoption funnel. |
| `data/feedback.json` | 30 user feedback entries — positive/neutral/negative mix with repeated crash, payment, and latency complaints. |
| `data/release_notes.md` | Feature change description ("Smart Dashboard 2.0"), architecture changes, known risks at launch, and rollback plan. |

---

## Setup & Run

### Prerequisites

- Python **3.9+** (deterministic mode: stdlib only, nothing to install)
- For LLM mode: `pip install openai` + a free [Groq API key](https://console.groq.com)

### Option 1 — Deterministic Mode (default)

```bash
cd war-room-agents
python main.py
```

That's it. No dependencies, no API keys. Output lands in `output/`.

### Option 2 — LLM-Enhanced Mode

```bash
# Install the openai package (only dependency)
pip install openai

# Set your Groq API key (free at https://console.groq.com)
export GROQ_API_KEY=your_key_here

# Run with LLM enhancement
python main.py --llm
```

Alternative providers:
```bash
python main.py --llm --provider together    # Together AI
python main.py --llm --provider openrouter  # OpenRouter
```

### Option 3 — Visual Dashboard (either mode)

```bash
python server.py
# Open http://127.0.0.1:8765 in a browser
# Click "Convene War Room"
```

The dashboard streams the agent trace live, then renders metric charts
(Chart.js), sentiment donut, risk register, action plan, rationale, and
communication plan. No build step — pure HTML/CSS/JS.

### Custom Paths

```bash
python main.py \
  --metrics   data/metrics.csv \
  --feedback  data/feedback.json \
  --notes     data/release_notes.md \
  --out       output/decision.json \
  --trace-out output/trace.json
```

---

## Outputs

| File | Contents |
|---|---|
| `output/decision.json` | Final structured launch decision (see schema below) |
| `output/trace.json` | Full machine-readable trace of every agent step and tool call |
| Console | Human-readable trace (`[TRACE] …`) printed live |

### Output Schema (`decision.json`)

```json
{
  "decision":            "Proceed | Pause | Roll Back",
  "confidence_score":    0.53,
  "composite_severity":  0.667,
  "mode":                "deterministic | llm-enhanced",
  "rationale":           [{"type": "metric|criterion|feedback", "detail": "..."}],
  "success_criteria_frame": "NO-GO (at least one must-hold criterion violated)",
  "blocking_violations": [{"metric": "...", "must_hold": true, "reason": "..."}],
  "metric_summary":      {"severity": 0.614, "concerning_metrics": [...], "aggregates": [...]},
  "feedback_summary":    {"sentiment": {...}, "perception": "hostile", "top_issue_themes": [...]},
  "risk_register":       [{"id": "R-CRASH-01", "title": "...", "severity": "high", "evidence": "...", "mitigation": "..."}],
  "action_plan_24_48h":  [{"window": "0-2h", "owner": "Release Manager", "action": "..."}],
  "communication_plan":  {"internal": "...", "external": "...", "hold_marketing_push": true},
  "what_would_increase_confidence": ["Per-device crash breakdown", "..."],
  "critic_challenges":   ["Is the crash spike device-specific?", "..."],
  "llm_agent_reasoning": {"data_analyst": {...}, "pm": {...}, ...}
}
```

The `llm_agent_reasoning` field is only present in LLM-enhanced mode and
contains the full LLM-generated analysis from each agent.

---

## Traceability

Every agent step and tool call is logged in two formats:

1. **Console** — human-readable `[TRACE]` lines printed live during execution:
   ```
   [TRACE] Coordinator       | HANDOFF :: -> Data Analyst
   [TRACE] Data_Analyst      | TOOL_CALL::aggregate_metric :: {args: ..., result: ...}
   [TRACE] Data_Analyst      | LLM_CALL :: interpreting tool outputs    (LLM mode only)
   ```

2. **`output/trace.json`** — machine-readable array of timestamped events:
   ```json
   {"t": 1775658823.256, "actor": "Coordinator", "action": "HANDOFF", "detail": "-> Data Analyst"}
   ```

In LLM-enhanced mode, additional `LLM_CALL` and `LLM_RESULT` entries appear
in the trace showing exactly what was sent to and received from the LLM.

---

## Design Decisions

**Why two modes?** Production decision systems need deterministic, auditable,
instant responses. But LLMs genuinely add value for nuanced interpretation,
natural-language communication drafts, and creative risk analysis. Rather than
choosing one, the system supports both — the deterministic pipeline runs as the
analytical backbone, and the LLM layer adds reasoning on top when available.

**Why not LangGraph / CrewAI / AutoGen?** The orchestration here is a simple
sequential pipeline with explicit handoffs. Adding a framework would introduce
dependencies and complexity without proportional benefit. The `Coordinator`
class achieves the same agent dispatch pattern in ~80 lines of clear Python.

**Why Groq + Llama 3.3?** Free tier, fast inference (~1–2s per call), and
OpenAI-compatible API so switching providers is a one-line change. The system is
not locked to any specific LLM.

**Why rule-based sentiment instead of a transformer?** For a mock dataset of
30 entries, a keyword classifier is transparent and auditable. The tool
interface is abstracted — swapping in a FinBERT or VADER classifier would
require changing only the `summarize_sentiment` function.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Only for `--llm` mode | Free API key from [console.groq.com](https://console.groq.com) |
| `TOGETHER_API_KEY` | Only if using `--provider together` | API key from [together.xyz](https://api.together.xyz) |
| `OPENROUTER_API_KEY` | Only if using `--provider openrouter` | API key from [openrouter.ai](https://openrouter.ai) |

No environment variables are required for deterministic mode.

---

## Project Layout

```
war-room-agents/
├── main.py                       # CLI entry (--llm flag toggles mode)
├── server.py                     # stdlib HTTP server for visual dashboard
├── requirements.txt              # openai (only needed for LLM mode)
├── .env.example                  # API key template
├── .gitignore
├── README.md
├── agents/
│   ├── base.py                   # Agent base class + TraceLogger
│   ├── coordinator.py            # Orchestrator (supports both modes)
│   ├── data_analyst.py           # Deterministic Data Analyst
│   ├── pm_agent.py               # Deterministic PM
│   ├── marketing_agent.py        # Deterministic Marketing/Comms
│   ├── risk_agent.py             # Deterministic Risk/Critic
│   ├── llm_client.py             # LLM wrapper (Groq/Together/OpenRouter)
│   ├── llm_data_analyst.py       # LLM-enhanced Data Analyst
│   ├── llm_pm_agent.py           # LLM-enhanced PM
│   ├── llm_marketing_agent.py    # LLM-enhanced Marketing/Comms
│   └── llm_risk_agent.py         # LLM-enhanced Risk/Critic
├── tools/
│   ├── metric_tools.py           # aggregate / trend / anomalies (deterministic)
│   └── feedback_tools.py         # sentiment / clustering (deterministic)
├── frontend/                     # Visual dashboard (served by server.py)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   ├── metrics.csv               # 14-day mock metrics (7 pre + 7 post launch)
│   ├── feedback.json             # 30 user feedback entries
│   └── release_notes.md          # Feature description + known risks
└── output/                       # Generated at runtime
    ├── decision.json             # Final structured decision
    └── trace.json                # Full agent + tool trace
```
