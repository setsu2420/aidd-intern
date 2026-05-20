// src/trace/collector.ts
var TraceCollector = class {
  sid;
  t0 = Date.now();
  turns = [];
  allTC = [];
  allErr = [];
  compactions = 0;
  cur = null;
  curStart = 0;
  curN = 0;
  curTC = [];
  pending = /* @__PURE__ */ new Map();
  thk = [];
  ast = [];
  constructor(sessionId) {
    this.sid = sessionId;
  }
  startTurn(msg) {
    if (this.cur) this.seal();
    this.cur = { index: this.turns.length, userMessage: msg, assistantResponse: null, toolCalls: [], thinkingContent: null, firstEventLatency: 0, totalDuration: 0, eventCount: 0 };
    this.curStart = Date.now();
    this.curN = 0;
    this.curTC = [];
    this.pending.clear();
    this.thk = [];
    this.ast = [];
  }
  addEvent(ev) {
    const now = Date.now();
    this.curN++;
    if (this.cur && this.curN === 1) this.cur.firstEventLatency = now - this.curStart;
    const d = ev.data ?? {};
    switch (ev.event_type) {
      case "assistant_chunk":
        if (d["chunk"]) this.ast.push(d["chunk"]);
        break;
      case "assistant_message":
        if (d["content"] && this.cur) this.cur.assistantResponse = d["content"];
        break;
      case "thinking_chunk":
        if (d["chunk"]) this.thk.push(d["chunk"]);
        break;
      case "tool_call": {
        const id = d["tool_call_id"], nm = d["tool"];
        if (id && nm) this.pending.set(id, { toolCallId: id, toolName: nm, arguments: d["arguments"] ?? {}, output: null, success: false, approvalRequired: false, duration: 0, timestamp: now });
        break;
      }
      case "tool_output": {
        const id = d["tool_call_id"], p = id ? this.pending.get(id) : void 0;
        if (p) {
          p.output = d["output"] ?? null;
          p.success = d["success"] ?? true;
          p.duration = now - (p.timestamp ?? now);
          this.curTC.push(p);
          this.allTC.push(p);
          this.pending.delete(id);
        }
        break;
      }
      case "approval_required": {
        for (const t of d["tools"] ?? []) {
          const p = this.pending.get(t["tool_call_id"]);
          if (p) p.approvalRequired = true;
        }
        break;
      }
      case "turn_complete": {
        if (this.cur) {
          const fr = d["final_response"];
          if (fr) this.cur.assistantResponse = fr;
          else if (!this.cur.assistantResponse && this.ast.length) this.cur.assistantResponse = this.ast.join("");
          this.cur.totalDuration = now - this.curStart;
        }
        break;
      }
      case "error":
        this.allErr.push({ message: d["error"] ?? "Unknown", type: d["error_type"] ?? "unknown", timestamp: now, turnIndex: this.cur?.index ?? null });
        break;
      case "compacted":
        this.compactions++;
        break;
    }
  }
  finalize() {
    if (this.cur) this.seal();
    const end = Date.now();
    return { sessionId: this.sid, startTime: this.t0, endTime: end, turns: this.turns, toolCalls: this.allTC, errors: this.allErr, metrics: this.metrics(end) };
  }
  seal() {
    if (!this.cur) return;
    if (this.thk.length) this.cur.thinkingContent = this.thk.join("");
    if (!this.cur.assistantResponse && this.ast.length) this.cur.assistantResponse = this.ast.join("");
    this.cur.toolCalls = [...this.curTC];
    this.cur.eventCount = this.curN;
    this.turns.push(this.cur);
    this.cur = null;
  }
  metrics(end) {
    const dur = this.turns.map((t) => t.totalDuration), avg = dur.length ? dur.reduce((a, b) => a + b, 0) / dur.length : 0;
    const ok = this.allTC.filter((t) => t.success).length;
    const lat = this.turns.map((t) => t.firstEventLatency).filter((l) => l > 0), avgL = lat.length ? lat.reduce((a, b) => a + b, 0) / lat.length : 0;
    return { totalTurns: this.turns.length, totalDuration: end - this.t0, avgTurnDuration: avg, totalToolCalls: this.allTC.length, successfulToolCalls: ok, toolSuccessRate: this.allTC.length ? ok / this.allTC.length : 1, errorCount: this.allErr.length, doomLoopDetected: this.doom(), approvalRequests: this.allTC.filter((t) => t.approvalRequired).length, compactionCount: this.compactions, avgFirstEventLatency: avgL, totalEvents: this.turns.reduce((s, t) => s + t.eventCount, 0) };
  }
  doom() {
    if (this.allTC.length < 5) return false;
    let s = 1;
    for (let i = 1; i < this.allTC.length; i++) {
      s = this.allTC[i].toolName === this.allTC[i - 1].toolName ? s + 1 : 1;
      if (s >= 5) return true;
    }
    return false;
  }
};

// src/trace/analyzer.ts
function analyzeTrace(trace) {
  const issues = [], strengths = [];
  if (trace.metrics.doomLoopDetected) issues.push({ severity: "critical", category: "doom_loop", message: "Same tool called 5+ consecutive times" });
  if (trace.errors.length > 0) issues.push({ severity: trace.errors.length > 3 ? "critical" : "warning", category: "errors", message: `${trace.errors.length} error(s)` });
  const tc = /* @__PURE__ */ new Map(), fs = /* @__PURE__ */ new Set();
  for (const t of trace.toolCalls) {
    tc.set(t.toolName, (tc.get(t.toolName) ?? 0) + 1);
    if (!t.success) fs.add(t.toolName);
  }
  const sr = trace.toolCalls.length ? trace.toolCalls.filter((t) => t.success).length / trace.toolCalls.length : 1;
  if (sr < 0.5 && trace.toolCalls.length > 2) issues.push({ severity: "critical", category: "tool_failure", message: `Low success: ${(sr * 100).toFixed(1)}%` });
  reps(trace.toolCalls, issues);
  const lat = trace.turns.map((t) => t.firstEventLatency).filter((l) => l > 0).sort((a, b) => a - b);
  const avgL = lat.length ? lat.reduce((a, b) => a + b, 0) / lat.length : 0;
  const p95 = lat[Math.max(0, Math.ceil(lat.length * 0.95) - 1)] ?? 0;
  const dur = trace.turns.map((t) => t.totalDuration), avgD = dur.length ? dur.reduce((a, b) => a + b, 0) / dur.length : 0;
  if (avgL > 1e4) issues.push({ severity: "warning", category: "latency", message: `High avg latency: ${(avgL / 1e3).toFixed(1)}s` });
  if (sr >= 0.9 && trace.toolCalls.length > 0) strengths.push(`High tool success: ${(sr * 100).toFixed(0)}%`);
  if (trace.errors.length === 0) strengths.push("Zero errors");
  if (avgL > 0 && avgL < 3e3) strengths.push(`Fast: ${(avgL / 1e3).toFixed(1)}s`);
  if (trace.turns.some((t) => t.assistantResponse && t.assistantResponse.length > 100)) strengths.push("Substantive responses");
  let most = null, mx = 0;
  for (const [n, c] of tc) {
    if (c > mx) {
      mx = c;
      most = n;
    }
  }
  let score = 100;
  for (const i of issues) score -= i.severity === "critical" ? 25 : i.severity === "warning" ? 10 : 2;
  if (!trace.turns.some((t) => t.assistantResponse?.trim())) score -= 30;
  if (sr >= 0.9 && trace.toolCalls.length > 0) score += 5;
  score = Math.max(0, Math.min(100, score));
  const totalSec = trace.metrics.totalDuration / 1e3;
  return { qualityScore: score, issues, strengths, performance: { avgLatency: avgL, p95Latency: p95, avgTurnDuration: avgD, maxTurnDuration: dur.length ? Math.max(...dur) : 0, eventsPerSecond: totalSec > 0 ? trace.metrics.totalEvents / totalSec : 0 }, toolUsage: { uniqueTools: [...tc.keys()], mostUsed: most, successRate: sr, failedTools: [...fs] } };
}
function reps(calls, issues) {
  let s = 1;
  for (let i = 1; i < calls.length; i++) {
    if (calls[i].toolName === calls[i - 1].toolName) {
      s++;
      if (s === 3) issues.push({ severity: "warning", category: "repeated_tool", message: `"${calls[i].toolName}" called 3+ times` });
    } else s = 1;
  }
}

export {
  TraceCollector,
  analyzeTrace
};
//# sourceMappingURL=chunk-5V6SUACB.js.map