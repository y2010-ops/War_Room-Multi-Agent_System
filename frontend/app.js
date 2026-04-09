// ──────────────────────────────────────────────────────────────
// War-Room Visualizer — front-end controller
// Drives the SVG flowchart + log + panels from the trace stream.
// ──────────────────────────────────────────────────────────────

const runBtn        = document.getElementById("runBtn");
const traceLog      = document.getElementById("traceLog");
const banner        = document.getElementById("decisionBanner");
const badge         = document.getElementById("decisionBadge");
const confidenceVal = document.getElementById("confidenceVal");
const compositeVal  = document.getElementById("compositeVal");
const frameVal      = document.getElementById("frameVal");

// Flowchart DOM refs.
const NODE = {
  coord:    document.getElementById("node-coord"),
  inputs:   document.getElementById("node-inputs"),
  data:     document.getElementById("node-data"),
  pm:       document.getElementById("node-pm"),
  marketing:document.getElementById("node-marketing"),
  risk:     document.getElementById("node-risk"),
  decision: document.getElementById("node-decision"),
};
const ARROW = {
  inpDa:   document.getElementById("arr-inp-da"),
  daPm:    document.getElementById("arr-da-pm"),
  pmMk:    document.getElementById("arr-pm-mk"),
  mkRk:    document.getElementById("arr-mk-rk"),
  rkDc:    document.getElementById("arr-rk-dc"),
  orcDa:   document.getElementById("orc-da"),
  orcPm:   document.getElementById("orc-pm"),
  orcMk:   document.getElementById("orc-mk"),
  orcRk:   document.getElementById("orc-rk"),
  orcRet:  document.getElementById("orc-return"),
};
const flowDecisionVal   = document.getElementById("flowDecisionVal");
const flowConfidenceVal = document.getElementById("flowConfidenceVal");

// Map each agent-actor name → { node, incoming arrow, orchestration line }.
const ACTOR_MAP = {
  Data_Analyst:    { node: NODE.data,      orc: ARROW.orcDa, incoming: ARROW.inpDa, outgoing: ARROW.daPm },
  PM_Agent:        { node: NODE.pm,        orc: ARROW.orcPm, incoming: ARROW.daPm,  outgoing: ARROW.pmMk },
  Marketing_Comms: { node: NODE.marketing, orc: ARROW.orcMk, incoming: ARROW.pmMk,  outgoing: ARROW.mkRk },
  Risk_Critic:     { node: NODE.risk,      orc: ARROW.orcRk, incoming: ARROW.mkRk,  outgoing: ARROW.rkDc },
};

// Pause durations (ms) for the streaming animation.
const STEP_DELAY     = 260; // delay after a regular trace entry
const TOOL_DELAY     = 180; // delay after a tool call (we want these to feel rapid)
const HANDOFF_DELAY  = 380;

let charts = {}; // Chart.js instances keyed by canvas id

runBtn.addEventListener("click", runWarRoom);

// ──────────────────────────────────────────────────────────────
// MAIN ENTRY
// ──────────────────────────────────────────────────────────────
async function runWarRoom() {
  runBtn.disabled = true;
  runBtn.querySelector(".run-btn-label").textContent = "Running…";
  traceLog.innerHTML = "";
  banner.classList.add("hidden");

  resetFlow();

  let payload;
  try {
    const res = await fetch("/api/run");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload = await res.json();
  } catch (err) {
    traceLog.innerHTML = `<div class="trace-placeholder">Error: ${err.message}</div>`;
    runBtn.disabled = false;
    runBtn.querySelector(".run-btn-label").textContent = "Convene War Room";
    return;
  }

  const { decision, trace, metric_rows } = payload;

  // Stream the trace through BOTH the log panel AND the flowchart.
  await streamTraceAndFlow(trace);

  renderBanner(decision);
  renderCharts(metric_rows);
  renderSentiment(decision.feedback_summary);
  renderRisks(decision.risk_register);
  renderActions(decision.action_plan_24_48h);
  renderRationale(decision);
  renderComms(decision.communication_plan);

  // Finish: mark every node done, show final verdict in decision node.
  finalizeFlow(decision);

  runBtn.disabled = false;
  runBtn.querySelector(".run-btn-label").textContent = "Re-run Simulation";
}

// ──────────────────────────────────────────────────────────────
// FLOWCHART STATE MACHINE
// ──────────────────────────────────────────────────────────────
function resetFlow() {
  Object.values(NODE).forEach(n => {
    n.classList.remove("active", "done");
    const st = n.querySelector(".status-text");
    if (st) st.textContent = "idle";
  });
  Object.values(ARROW).forEach(a => a && a.classList.remove("active", "done"));
  document.querySelectorAll(".tool-chip").forEach(c => c.classList.remove("firing", "used"));

  flowDecisionVal.textContent = "—";
  flowDecisionVal.className = "decision-value";
  flowConfidenceVal.textContent = "confidence —";
}

function setNodeState(nodeEl, state) {
  if (!nodeEl) return;
  if (state === "active") {
    nodeEl.classList.remove("done");
    nodeEl.classList.add("active");
    const st = nodeEl.querySelector(".status-text");
    if (st) st.textContent = "running";
  } else if (state === "done") {
    nodeEl.classList.remove("active");
    nodeEl.classList.add("done");
    const st = nodeEl.querySelector(".status-text");
    if (st) st.textContent = "done";
  }
}

function setArrowState(arrow, state) {
  if (!arrow) return;
  if (state === "active") {
    arrow.classList.remove("done");
    arrow.classList.add("active");
  } else if (state === "done") {
    arrow.classList.remove("active");
    arrow.classList.add("done");
  }
}

function fireToolChip(agentNode, toolName) {
  if (!agentNode) return;
  const chip = agentNode.querySelector(`.tool-chip[data-tool="${toolName}"]`);
  if (!chip) return;
  chip.classList.remove("used");
  chip.classList.add("firing");
  setTimeout(() => {
    chip.classList.remove("firing");
    chip.classList.add("used");
  }, 420);
}

// Apply one trace entry to the flowchart. Returns the delay to wait afterwards.
function applyTraceEntryToFlow(entry) {
  const { actor, action, detail } = entry;

  // Coordinator events
  if (actor === "Coordinator") {
    if (action === "ORCHESTRATION_START") {
      setNodeState(NODE.coord, "active");
      setNodeState(NODE.inputs, "active");
      return STEP_DELAY;
    }
    if (action === "HANDOFF") {
      // First handoff implies inputs flow into the pipeline.
      const txt = typeof detail === "string" ? detail : "";
      if (txt.includes("Data Analyst")) {
        setNodeState(NODE.inputs, "done");
        setArrowState(ARROW.inpDa, "active");
        setArrowState(ARROW.orcDa, "active");
      }
      if (txt.includes("PM"))        setArrowState(ARROW.orcPm, "active");
      if (txt.includes("Marketing")) setArrowState(ARROW.orcMk, "active");
      if (txt.includes("Risk"))      setArrowState(ARROW.orcRk, "active");
      if (txt.includes("final synthesis")) setArrowState(ARROW.orcRet, "active");
      return HANDOFF_DELAY;
    }
    if (action === "DECISION") {
      setArrowState(ARROW.rkDc, "active");
      setNodeState(NODE.decision, "active");
      if (detail && detail.decision) {
        flowDecisionVal.textContent = detail.decision;
        flowDecisionVal.className = "decision-value " + decisionCls(detail.decision);
        flowConfidenceVal.textContent = `confidence ${detail.confidence}`;
      }
      return STEP_DELAY;
    }
    if (action === "ORCHESTRATION_DONE") {
      setNodeState(NODE.decision, "done");
      setArrowState(ARROW.rkDc, "done");
      setArrowState(ARROW.orcRet, "done");
      setNodeState(NODE.coord, "done");
      return STEP_DELAY;
    }
  }

  // Agent events
  const map = ACTOR_MAP[actor];
  if (map) {
    if (action === "START") {
      setNodeState(map.node, "active");
      setArrowState(map.orc, "active");
      if (map.incoming) setArrowState(map.incoming, "active");
      return STEP_DELAY;
    }
    if (typeof action === "string" && action.startsWith("TOOL_CALL::")) {
      const tool = action.replace("TOOL_CALL::", "");
      fireToolChip(map.node, tool);
      return TOOL_DELAY;
    }
    if (action === "DONE") {
      setNodeState(map.node, "done");
      if (map.incoming) setArrowState(map.incoming, "done");
      setArrowState(map.orc, "done");
      if (map.outgoing) setArrowState(map.outgoing, "active");
      return HANDOFF_DELAY;
    }
  }

  return STEP_DELAY;
}

function finalizeFlow(decision) {
  // In case any state wasn't closed out by the trace, finalize here.
  Object.values(ACTOR_MAP).forEach(m => setNodeState(m.node, "done"));
  setNodeState(NODE.coord, "done");
  setNodeState(NODE.decision, "done");
  [ARROW.inpDa, ARROW.daPm, ARROW.pmMk, ARROW.mkRk, ARROW.rkDc,
   ARROW.orcDa, ARROW.orcPm, ARROW.orcMk, ARROW.orcRk, ARROW.orcRet]
    .forEach(a => setArrowState(a, "done"));

  flowDecisionVal.textContent = decision.decision;
  flowDecisionVal.className = "decision-value " + decisionCls(decision.decision);
  flowConfidenceVal.textContent = `confidence ${decision.confidence_score}`;
}

function decisionCls(d) {
  if (d === "Proceed") return "proceed";
  if (d === "Pause")   return "pause";
  return "rollback";
}

// ──────────────────────────────────────────────────────────────
// TRACE LOG STREAMING
// ──────────────────────────────────────────────────────────────
async function streamTraceAndFlow(entries) {
  for (const e of entries) {
    appendTraceEntry(e);
    const delay = applyTraceEntryToFlow(e);
    await sleep(delay);
  }
}

function appendTraceEntry(e) {
  const div = document.createElement("div");
  div.className = `trace-entry ${e.actor}`;
  const isToolCall = typeof e.action === "string" && e.action.startsWith("TOOL_CALL::");
  let actionHtml;
  if (isToolCall) {
    const tool = e.action.replace("TOOL_CALL::", "");
    actionHtml = `<span class="tool">🔧 ${tool}</span>`;
  } else {
    actionHtml = `<span class="action">${escapeHtml(String(e.action))}</span>`;
  }
  const detailHtml = e.detail
    ? `<span class="detail">${escapeHtml(stringifyDetail(e.detail))}</span>`
    : "";
  div.innerHTML =
    `<span class="actor">${e.actor}</span> │ ${actionHtml}${detailHtml}`;
  traceLog.appendChild(div);
  traceLog.scrollTop = traceLog.scrollHeight;
}

function stringifyDetail(d) {
  if (d == null) return "";
  if (typeof d === "string") return d;
  try { return JSON.stringify(d); } catch { return String(d); }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ──────────────────────────────────────────────────────────────
// DECISION BANNER
// ──────────────────────────────────────────────────────────────
function renderBanner(decision) {
  banner.classList.remove("hidden");
  const d = decision.decision;
  badge.textContent = d;
  badge.className = "decision-badge " + decisionCls(d);
  confidenceVal.textContent = decision.confidence_score;
  compositeVal.textContent  = decision.composite_severity;
  frameVal.textContent      = decision.success_criteria_frame;
}

// ──────────────────────────────────────────────────────────────
// CHARTS
// ──────────────────────────────────────────────────────────────
function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

function makeLineChart(canvasId, label, days, values, color, yFormat) {
  destroyChart(canvasId);
  const ctx = document.getElementById(canvasId).getContext("2d");
  const launchDay = 8;
  const pointColors = days.map(d => d >= launchDay ? color : color + "80");
  charts[canvasId] = new Chart(ctx, {
    type: "line",
    data: {
      labels: days.map(d => `D${d}`),
      datasets: [{
        label,
        data: values,
        borderColor: color,
        backgroundColor: color + "22",
        fill: true,
        tension: 0.35,
        pointBackgroundColor: pointColors,
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2.5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#eef0fb", font: { size: 11, family: "Inter" } } },
        tooltip: { mode: "index", intersect: false, backgroundColor: "rgba(7,10,26,0.9)", borderColor: "#8b5cf6", borderWidth: 1 },
      },
      scales: {
        x: { ticks: { color: "#9ba4cf", font: { family: "JetBrains Mono", size: 10 } }, grid: { color: "rgba(139,120,220,0.12)" } },
        y: {
          ticks: {
            color: "#9ba4cf",
            font: { family: "JetBrains Mono", size: 10 },
            callback: (v) => yFormat ? yFormat(v) : v,
          },
          grid: { color: "rgba(139,120,220,0.12)" },
        },
      },
    },
  });
}

function renderCharts(rows) {
  const days = rows.map(r => r.day);
  makeLineChart("chartCrash",   "Crash Rate",           days, rows.map(r => r.crash_rate),           "#ef4444", v => (v * 100).toFixed(1) + "%");
  makeLineChart("chartLatency", "API p95 Latency (ms)", days, rows.map(r => r.api_p95_ms),           "#f59e0b", v => v + "ms");
  makeLineChart("chartPayment", "Payment Success",      days, rows.map(r => r.payment_success_rate), "#22c55e", v => (v * 100).toFixed(1) + "%");
  makeLineChart("chartDau",     "DAU",                  days, rows.map(r => r.dau),                  "#38bdf8", v => (v / 1000).toFixed(1) + "k");
}

// ──────────────────────────────────────────────────────────────
// SENTIMENT
// ──────────────────────────────────────────────────────────────
function renderSentiment(fs) {
  destroyChart("chartSentiment");
  const s = fs.sentiment;
  const ctx = document.getElementById("chartSentiment").getContext("2d");
  charts.chartSentiment = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Positive", "Neutral", "Negative"],
      datasets: [{
        data: [s.positive, s.neutral, s.negative],
        backgroundColor: ["#22c55e", "#6b749c", "#ef4444"],
        borderColor: "#0d1330",
        borderWidth: 3,
        hoverOffset: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: { position: "bottom", labels: { color: "#eef0fb", font: { size: 11, family: "Inter" }, padding: 14 } },
        tooltip: { backgroundColor: "rgba(7,10,26,0.9)", borderColor: "#8b5cf6", borderWidth: 1 },
      },
    },
  });

  const perceptionBox = document.getElementById("perceptionBox");
  perceptionBox.textContent = `Perception: ${fs.perception.toUpperCase()}`;
  const color = {
    positive: "#22c55e",
    mixed: "#38bdf8",
    "mixed-negative": "#f59e0b",
    hostile: "#ef4444",
  }[fs.perception] || "#a78bfa";
  perceptionBox.style.color = color;
  perceptionBox.style.borderLeftColor = color;

  const themes = fs.top_issue_themes || [];
  const themeList = document.getElementById("themeList");
  themeList.innerHTML = themes.map(t =>
    `<li><span>${escapeHtml(t.theme)}</span><span class="count">${t.count}</span></li>`
  ).join("") || "<li><span class='muted'>No themes detected</span></li>";
}

// ──────────────────────────────────────────────────────────────
// PANELS
// ──────────────────────────────────────────────────────────────
function renderRisks(risks) {
  document.getElementById("riskList").innerHTML = risks.map(r => `
    <div class="risk-card ${r.severity}">
      <div class="title">${escapeHtml(r.id)}: ${escapeHtml(r.title)} <span class="sev-tag">${r.severity}</span></div>
      <div class="evidence">${escapeHtml(r.evidence)}</div>
      <div class="mitigation"><b>Mitigation:</b> ${escapeHtml(r.mitigation)}</div>
    </div>
  `).join("");
}

function ownerTeamClass(owner) {
  const o = (owner || "").toLowerCase();
  if (o.includes("release"))     return "team-release";
  if (o.includes("mobile"))      return "team-mobile";
  if (o.includes("engineering")) return "team-engineering";
  if (o.includes("payment"))     return "team-payments";
  if (o.includes("on-call") || o.includes("oncall")) return "team-oncall";
  if (o.includes("data"))        return "team-data";
  if (o.includes("product"))     return "team-product";
  return "";
}

function renderActions(actions) {
  document.getElementById("actionList").innerHTML = actions.map(a => `
    <li class="${ownerTeamClass(a.owner)}">
      <span class="window">${escapeHtml(a.window)}</span>
      <span class="owner">${escapeHtml(a.owner)}</span>
      <span class="act">${escapeHtml(a.action)}</span>
    </li>
  `).join("");
}

function renderRationale(decision) {
  document.getElementById("rationaleList").innerHTML =
    (decision.rationale || []).map(r => `<li><b>${escapeHtml(r.type)}:</b> ${escapeHtml(r.detail)}</li>`).join("");
  document.getElementById("challengeList").innerHTML =
    (decision.critic_challenges || []).map(c => `<li>${escapeHtml(c)}</li>`).join("");
  document.getElementById("missingList").innerHTML =
    (decision.what_would_increase_confidence || []).map(m => `<li>${escapeHtml(m)}</li>`).join("");
}

function renderComms(comms) {
  document.getElementById("internalMsg").textContent = comms.internal;
  document.getElementById("externalMsg").textContent = comms.external;
}
