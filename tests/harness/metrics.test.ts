import { describe, it, expect } from 'vitest';
import { computeMetrics, aggregateMetrics } from '../../src/evaluator/metrics.js';
import { analyzeTrace } from '../../src/trace/analyzer.js';
import { TraceCollector } from '../../src/trace/collector.js';
import type { SSEEvent } from '../../src/client/types.js';
import { reportStep } from './test-output.js';

const ev = (type: string, data: Record<string, unknown> = {}): SSEEvent => ({ event_type: type, data, seq: null });

function simple() {
  const c = new TraceCollector('m'); c.startTurn('test');
  c.addEvent(ev('tool_call', { tool_call_id: 't1', tool: 'search' })); c.addEvent(ev('tool_output', { tool_call_id: 't1', output: 'ok', success: true }));
  c.addEvent(ev('turn_complete', { final_response: 'Answer.' }));
  return c.finalize();
}

describe('Metrics', () => {
  it('computes from trace', () => {
    reportStep('metrics compute', 'build a trace with one successful search tool call');
    const t = simple(), a = analyzeTrace(t), m = computeMetrics('t1', t, a);
    reportStep('metrics compute', 'observed metrics', m);
    expect(m.testCaseId).toBe('t1'); expect(m.efficiency.totalToolCalls).toBe(1); expect(m.efficiency.toolSuccessRate).toBe(1); expect(m.traceQualityScore).toBeGreaterThanOrEqual(90);
  });

  it('aggregates', () => {
    reportStep('metrics aggregate', 'aggregate two real metric reports from the same trace shape');
    const t = simple(), a = analyzeTrace(t);
    const agg = aggregateMetrics([computeMetrics('t1', t, a), computeMetrics('t2', t, a)]);
    reportStep('metrics aggregate', 'observed aggregate', agg);
    expect(agg.count).toBe(2); expect(agg.avgQuality).toBeGreaterThanOrEqual(90); expect(agg.doomLoops).toBe(0);
  });

  it('handles empty', () => {
    reportStep('metrics empty aggregate', 'aggregate an empty report list');
    expect(aggregateMetrics([]).count).toBe(0);
    reportStep('metrics empty aggregate', 'observed zero-count aggregate');
  });
});
