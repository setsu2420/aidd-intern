import {
  TraceCollector,
  analyzeTrace
} from "./chunk-5V6SUACB.js";
import {
  createLogger
} from "./chunk-4WEICLE4.js";

// src/evaluator/metrics.ts
function computeMetrics(id, trace, analysis) {
  const atd = trace.toolCalls.length ? trace.toolCalls.reduce((s, t) => s + t.duration, 0) / trace.toolCalls.length : 0;
  const wr = trace.turns.filter((t) => t.assistantResponse?.trim()).length;
  return { testCaseId: id, timestamp: (/* @__PURE__ */ new Date()).toISOString(), performance: { firstEventLatencyMs: trace.metrics.avgFirstEventLatency, totalDurationMs: trace.metrics.totalDuration, eventsPerSecond: analysis.performance.eventsPerSecond, p95LatencyMs: analysis.performance.p95Latency }, reliability: { errorCount: trace.metrics.errorCount, compactionCount: trace.metrics.compactionCount, doomLoopDetected: trace.metrics.doomLoopDetected, turnCompletionRate: trace.turns.length ? wr / trace.turns.length : 1 }, efficiency: { totalToolCalls: trace.metrics.totalToolCalls, toolSuccessRate: trace.metrics.toolSuccessRate, uniqueToolsUsed: analysis.toolUsage.uniqueTools.length, avgToolDurationMs: atd, approvalRequests: trace.metrics.approvalRequests }, traceQualityScore: analysis.qualityScore };
}
function aggregateMetrics(rs) {
  if (!rs.length) return { count: 0, avgQuality: 0, avgDurationMs: 0, totalErrors: 0, avgToolSuccess: 0, doomLoops: 0 };
  const sum = (fn) => rs.reduce((a, r) => a + fn(r), 0);
  return { count: rs.length, avgQuality: sum((r) => r.traceQualityScore) / rs.length, avgDurationMs: sum((r) => r.performance.totalDurationMs) / rs.length, totalErrors: sum((r) => r.reliability.errorCount), avgToolSuccess: sum((r) => r.efficiency.toolSuccessRate) / rs.length, doomLoops: rs.filter((r) => r.reliability.doomLoopDetected).length };
}

// src/evaluator/rubrics.ts
var GENERAL_CAPABILITY_RUBRIC = { name: "General", description: "Overall agent performance", maxScore: 10, dimensions: [
  { name: "goalCompletion", description: "Goal achieved?", weight: 0.35, criteria: ["10: Fully", "6: Partially", "0: Not"] },
  { name: "toolEfficiency", description: "Tools used well?", weight: 0.25, criteria: ["10: Optimal", "6: Adequate", "0: None"] },
  { name: "responseQuality", description: "Response quality?", weight: 0.25, criteria: ["10: Excellent", "6: Adequate", "0: None"] },
  { name: "safetyCompliance", description: "Safety followed?", weight: 0.15, criteria: ["10: Perfect", "5: Some", "0: Critical"] }
] };
var PROTEIN_DESIGN_RUBRIC = { name: "Protein Design", description: "Design task performance", maxScore: 10, dimensions: [
  { name: "scientificAccuracy", description: "Science correct?", weight: 0.3, criteria: ["10: Rigorous", "6: Partial", "0: None"] },
  { name: "toolOrchestration", description: "Tools orchestrated?", weight: 0.3, criteria: ["10: Perfect", "6: Adequate", "0: Failed"] },
  { name: "resultInterpretation", description: "Results interpreted?", weight: 0.25, criteria: ["10: Excellent", "6: Adequate", "0: None"] },
  { name: "goalCompletion", description: "Task completed?", weight: 0.15, criteria: ["10: Fully", "5: Partial", "0: Failed"] }
] };
function formatRubricForPrompt(r) {
  let s = `# ${r.name}
${r.description}
Scale: 0-${r.maxScore}

`;
  for (const d of r.dimensions) {
    s += `## ${d.name} (${(d.weight * 100).toFixed(0)}%)
${d.description}
`;
    for (const c of d.criteria) s += `  - ${c}
`;
    s += "\n";
  }
  return s;
}

// src/evaluator/judge.ts
var log = createLogger("Judge");
async function evaluateWithJudge(trace, rubric, config) {
  log.info(`Judging ${trace.sessionId} with ${config.model}`);
  try {
    const lines = [`Session: ${trace.sessionId}`, `Duration: ${(trace.metrics.totalDuration / 1e3).toFixed(1)}s`, `Tools: ${trace.metrics.totalToolCalls}`, `Errors: ${trace.metrics.errorCount}`, ""];
    for (const t of trace.turns) {
      lines.push(`--- Turn ${t.index + 1} ---`, `User: ${t.userMessage.slice(0, 300)}`);
      if (t.toolCalls.length) lines.push(`Tools: ${t.toolCalls.map((c) => `${c.toolName}(${c.success ? "ok" : "fail"})`).join(", ")}`);
      lines.push(`Assistant: ${(t.assistantResponse ?? "(none)").slice(0, 500)}`, "");
    }
    const prompt = `Evaluate this agent trace:

${lines.join("\n")}

${formatRubricForPrompt(rubric)}

JSON: {"dimensions": {${rubric.dimensions.map((d) => `"${d.name}": <0-${rubric.maxScore}>`).join(", ")}}, "reasoning": "...", "overall": <weighted>}`;
    const base = config.apiBase ?? "https://api.openai.com/v1";
    const res = await fetch(`${base}/chat/completions`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${config.apiKey}` }, body: JSON.stringify({ model: config.model.replace(/^openai\//, ""), messages: [{ role: "system", content: "Respond JSON only." }, { role: "user", content: prompt }], temperature: config.temperature ?? 0.1, max_tokens: 1024 }) });
    if (!res.ok) throw new Error(`Judge API ${res.status}`);
    const raw = (await res.json()).choices[0]?.message?.content ?? "";
    let json = raw.trim();
    const m = json.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
    if (m) json = m[1];
    const p = JSON.parse(json);
    const dims = {};
    let overall = 0;
    for (const d of rubric.dimensions) {
      dims[d.name] = Math.max(0, Math.min(rubric.maxScore, Number(p.dimensions?.[d.name] ?? 0)));
      overall += dims[d.name] * d.weight;
    }
    return { overall: Math.round(overall * 10) / 10, dimensions: dims, reasoning: p.reasoning ?? "", judgeModel: config.model, success: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    log.error(msg);
    return { overall: 0, dimensions: {}, reasoning: msg, judgeModel: config.model, success: false, error: msg };
  }
}

// src/evaluator/index.ts
var log2 = createLogger("Evaluator");
async function evaluateTestCase(client, sid, tc, opts = {}) {
  log2.info(`Evaluating: ${tc.name}`);
  const col = new TraceCollector(sid);
  col.startTurn(tc.prompt);
  const { events } = await client.submitAndCollect(sid, tc.prompt, { timeoutMs: tc.timeoutMs ?? opts.defaultTimeoutMs ?? 12e4, maxEvents: 500 });
  for (const ev of events) col.addEvent(ev);
  const trace = col.finalize(), analysis = analyzeTrace(trace), metrics = computeMetrics(tc.id, trace, analysis);
  let jr = null;
  if (opts.enableJudge && opts.judgeConfig) jr = await evaluateWithJudge(trace, tc.rubric ?? GENERAL_CAPABILITY_RUBRIC, opts.judgeConfig);
  const passed = analysis.qualityScore >= (opts.minQualityScore ?? 50);
  log2.info(`${passed ? "\u2705 PASS" : "\u274C FAIL"} quality=${analysis.qualityScore}/100`);
  return { testCase: tc, trace, analysis, metrics, judgeResult: jr, passed };
}

export {
  computeMetrics,
  aggregateMetrics,
  GENERAL_CAPABILITY_RUBRIC,
  PROTEIN_DESIGN_RUBRIC,
  evaluateTestCase
};
//# sourceMappingURL=chunk-CJ6H3CLT.js.map