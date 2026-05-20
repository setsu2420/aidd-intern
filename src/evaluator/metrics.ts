import type { Trace } from '../trace/types.js';
import type { TraceAnalysis } from '../trace/analyzer.js';
export interface MetricsReport { testCaseId: string; timestamp: string; performance: { firstEventLatencyMs: number; totalDurationMs: number; eventsPerSecond: number; p95LatencyMs: number }; reliability: { errorCount: number; compactionCount: number; doomLoopDetected: boolean; turnCompletionRate: number }; efficiency: { totalToolCalls: number; toolSuccessRate: number; uniqueToolsUsed: number; avgToolDurationMs: number; approvalRequests: number }; traceQualityScore: number; }
export function computeMetrics(id: string, trace: Trace, analysis: TraceAnalysis): MetricsReport {
  const atd = trace.toolCalls.length ? trace.toolCalls.reduce((s, t) => s + t.duration, 0) / trace.toolCalls.length : 0;
  const wr = trace.turns.filter(t => t.assistantResponse?.trim()).length;
  return { testCaseId: id, timestamp: new Date().toISOString(), performance: { firstEventLatencyMs: trace.metrics.avgFirstEventLatency, totalDurationMs: trace.metrics.totalDuration, eventsPerSecond: analysis.performance.eventsPerSecond, p95LatencyMs: analysis.performance.p95Latency }, reliability: { errorCount: trace.metrics.errorCount, compactionCount: trace.metrics.compactionCount, doomLoopDetected: trace.metrics.doomLoopDetected, turnCompletionRate: trace.turns.length ? wr / trace.turns.length : 1 }, efficiency: { totalToolCalls: trace.metrics.totalToolCalls, toolSuccessRate: trace.metrics.toolSuccessRate, uniqueToolsUsed: analysis.toolUsage.uniqueTools.length, avgToolDurationMs: atd, approvalRequests: trace.metrics.approvalRequests }, traceQualityScore: analysis.qualityScore };
}
export function aggregateMetrics(rs: MetricsReport[]) {
  if (!rs.length) return { count: 0, avgQuality: 0, avgDurationMs: 0, totalErrors: 0, avgToolSuccess: 0, doomLoops: 0 };
  const sum = (fn: (r: MetricsReport) => number) => rs.reduce((a, r) => a + fn(r), 0);
  return { count: rs.length, avgQuality: sum(r => r.traceQualityScore) / rs.length, avgDurationMs: sum(r => r.performance.totalDurationMs) / rs.length, totalErrors: sum(r => r.reliability.errorCount), avgToolSuccess: sum(r => r.efficiency.toolSuccessRate) / rs.length, doomLoops: rs.filter(r => r.reliability.doomLoopDetected).length };
}
