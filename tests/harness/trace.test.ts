import { describe, it, expect } from 'vitest';
import { TraceCollector } from '../../src/trace/collector.js';
import { analyzeTrace } from '../../src/trace/analyzer.js';
import type { SSEEvent } from '../../src/client/types.js';
import { reportStep } from './test-output.js';

const ev = (type: string, data: Record<string, unknown> = {}): SSEEvent => ({ event_type: type, data, seq: null });

describe('TraceCollector', () => {
  it('builds trace from simple events', () => {
    reportStep('trace simple events', 'collect processing, assistant chunks, and turn_complete');
    const c = new TraceCollector('s1'); c.startTurn('Hello');
    c.addEvent(ev('processing')); c.addEvent(ev('assistant_chunk', { chunk: 'Hi ' })); c.addEvent(ev('assistant_chunk', { chunk: 'there!' })); c.addEvent(ev('turn_complete', { final_response: 'Hi there!' }));
    const t = c.finalize();
    reportStep('trace simple events', 'observed trace metrics', t.metrics);
    expect(t.turns).toHaveLength(1); expect(t.turns[0].assistantResponse).toBe('Hi there!'); expect(t.turns[0].eventCount).toBe(4); expect(t.metrics.doomLoopDetected).toBe(false);
  });

  it('tracks tool calls', () => {
    reportStep('trace tool calls', 'collect a search tool_call and matching tool_output');
    const c = new TraceCollector('s1'); c.startTurn('Search');
    c.addEvent(ev('tool_call', { tool_call_id: 't1', tool: 'search', arguments: { q: 'x' } })); c.addEvent(ev('tool_output', { tool_call_id: 't1', output: 'ok', success: true })); c.addEvent(ev('turn_complete', {}));
    const t = c.finalize();
    reportStep('trace tool calls', 'observed tool calls', t.toolCalls);
    expect(t.toolCalls).toHaveLength(1); expect(t.toolCalls[0].toolName).toBe('search'); expect(t.metrics.toolSuccessRate).toBe(1);
  });

  it('detects doom loop', () => {
    reportStep('trace doom loop', 'collect repeated same-tool calls');
    const c = new TraceCollector('s1'); c.startTurn('loop');
    for (let i = 0; i < 6; i++) { c.addEvent(ev('tool_call', { tool_call_id: `t${i}`, tool: 'same' })); c.addEvent(ev('tool_output', { tool_call_id: `t${i}`, success: true })); }
    c.addEvent(ev('turn_complete', {}));
    const trace = c.finalize();
    reportStep('trace doom loop', 'observed doomLoopDetected flag', trace.metrics.doomLoopDetected);
    expect(trace.metrics.doomLoopDetected).toBe(true);
  });

  it('no doom loop with varied tools', () => {
    reportStep('trace varied tools', 'collect alternating tool names');
    const c = new TraceCollector('s1'); c.startTurn('varied');
    ['a', 'b', 'c', 'a', 'b'].forEach((t, i) => { c.addEvent(ev('tool_call', { tool_call_id: `t${i}`, tool: t })); c.addEvent(ev('tool_output', { tool_call_id: `t${i}`, success: true })); });
    c.addEvent(ev('turn_complete', {}));
    const trace = c.finalize();
    reportStep('trace varied tools', 'observed doomLoopDetected flag', trace.metrics.doomLoopDetected);
    expect(trace.metrics.doomLoopDetected).toBe(false);
  });

  it('tracks errors', () => {
    reportStep('trace errors', 'collect one runtime error event');
    const c = new TraceCollector('s1'); c.startTurn('fail');
    c.addEvent(ev('error', { error: 'Oops', error_type: 'runtime' })); c.addEvent(ev('turn_complete', {}));
    const t = c.finalize();
    reportStep('trace errors', 'observed errors', t.errors);
    expect(t.errors).toHaveLength(1); expect(t.metrics.errorCount).toBe(1);
  });
});

describe('TraceAnalyzer', () => {
  it('high score for clean trace', () => {
    reportStep('trace analyzer clean', 'analyze a completed single-turn trace');
    const c = new TraceCollector('s1'); c.startTurn('Hi');
    c.addEvent(ev('turn_complete', { final_response: 'Hello! How can I help you today?' }));
    const analysis = analyzeTrace(c.finalize());
    reportStep('trace analyzer clean', 'observed quality score', analysis.qualityScore);
    expect(analysis.qualityScore).toBeGreaterThanOrEqual(90);
  });

  it('penalizes doom loops', () => {
    reportStep('trace analyzer doom loop', 'analyze repeated same-tool calls');
    const c = new TraceCollector('s1'); c.startTurn('loop');
    for (let i = 0; i < 5; i++) { c.addEvent(ev('tool_call', { tool_call_id: `t${i}`, tool: 'x' })); c.addEvent(ev('tool_output', { tool_call_id: `t${i}`, success: true })); }
    c.addEvent(ev('turn_complete', { final_response: 'Done' }));
    const a = analyzeTrace(c.finalize());
    reportStep('trace analyzer doom loop', 'observed issues', a.issues);
    expect(a.qualityScore).toBeLessThan(80); expect(a.issues.some(i => i.category === 'doom_loop')).toBe(true);
  });
});
