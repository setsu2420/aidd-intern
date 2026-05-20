import type { Trace, ToolCallRecord } from './types.js';

export interface TraceAnalysis {
  qualityScore: number;
  issues: { severity: 'critical' | 'warning' | 'info'; category: string; message: string }[];
  strengths: string[];
  performance: { avgLatency: number; p95Latency: number; avgTurnDuration: number; maxTurnDuration: number; eventsPerSecond: number };
  toolUsage: { uniqueTools: string[]; mostUsed: string | null; successRate: number; failedTools: string[] };
}

export function analyzeTrace(trace: Trace): TraceAnalysis {
  const issues: TraceAnalysis['issues'] = [], strengths: string[] = [];
  if (trace.metrics.doomLoopDetected) issues.push({ severity: 'critical', category: 'doom_loop', message: 'Same tool called 5+ consecutive times' });
  if (trace.errors.length > 0) issues.push({ severity: trace.errors.length > 3 ? 'critical' : 'warning', category: 'errors', message: `${trace.errors.length} error(s)` });
  const tc = new Map<string, number>(), fs = new Set<string>();
  for (const t of trace.toolCalls) { tc.set(t.toolName, (tc.get(t.toolName) ?? 0) + 1); if (!t.success) fs.add(t.toolName); }
  const sr = trace.toolCalls.length ? trace.toolCalls.filter(t => t.success).length / trace.toolCalls.length : 1;
  if (sr < 0.5 && trace.toolCalls.length > 2) issues.push({ severity: 'critical', category: 'tool_failure', message: `Low success: ${(sr * 100).toFixed(1)}%` });
  reps(trace.toolCalls, issues);
  const lat = trace.turns.map(t => t.firstEventLatency).filter(l => l > 0).sort((a, b) => a - b);
  const avgL = lat.length ? lat.reduce((a, b) => a + b, 0) / lat.length : 0;
  const p95 = lat[Math.max(0, Math.ceil(lat.length * 0.95) - 1)] ?? 0;
  const dur = trace.turns.map(t => t.totalDuration), avgD = dur.length ? dur.reduce((a, b) => a + b, 0) / dur.length : 0;
  if (avgL > 10_000) issues.push({ severity: 'warning', category: 'latency', message: `High avg latency: ${(avgL / 1000).toFixed(1)}s` });
  if (sr >= 0.9 && trace.toolCalls.length > 0) strengths.push(`High tool success: ${(sr * 100).toFixed(0)}%`);
  if (trace.errors.length === 0) strengths.push('Zero errors');
  if (avgL > 0 && avgL < 3000) strengths.push(`Fast: ${(avgL / 1000).toFixed(1)}s`);
  if (trace.turns.some(t => t.assistantResponse && t.assistantResponse.length > 100)) strengths.push('Substantive responses');
  let most: string | null = null, mx = 0; for (const [n, c] of tc) { if (c > mx) { mx = c; most = n; } }
  let score = 100;
  for (const i of issues) score -= i.severity === 'critical' ? 25 : i.severity === 'warning' ? 10 : 2;
  if (!trace.turns.some(t => t.assistantResponse?.trim())) score -= 30;
  if (sr >= 0.9 && trace.toolCalls.length > 0) score += 5;
  score = Math.max(0, Math.min(100, score));
  const totalSec = trace.metrics.totalDuration / 1000;
  return { qualityScore: score, issues, strengths, performance: { avgLatency: avgL, p95Latency: p95, avgTurnDuration: avgD, maxTurnDuration: dur.length ? Math.max(...dur) : 0, eventsPerSecond: totalSec > 0 ? trace.metrics.totalEvents / totalSec : 0 }, toolUsage: { uniqueTools: [...tc.keys()], mostUsed: most, successRate: sr, failedTools: [...fs] } };
}

function reps(calls: ToolCallRecord[], issues: TraceAnalysis['issues']) {
  let s = 1; for (let i = 1; i < calls.length; i++) { if (calls[i].toolName === calls[i - 1].toolName) { s++; if (s === 3) issues.push({ severity: 'warning', category: 'repeated_tool', message: `"${calls[i].toolName}" called 3+ times` }); } else s = 1; }
}
