import type { SSEEvent } from '../client/types.js';
import type { Trace, Turn, ToolCallRecord, TraceMetrics } from './types.js';

export class TraceCollector {
  private readonly sid: string;
  private readonly t0 = Date.now();
  private turns: Turn[] = [];
  private allTC: ToolCallRecord[] = [];
  private allErr: { message: string; type: string; timestamp: number; turnIndex: number | null }[] = [];
  private compactions = 0;
  private cur: Partial<Turn> | null = null;
  private curStart = 0;
  private curN = 0;
  private curTC: ToolCallRecord[] = [];
  private pending = new Map<string, Partial<ToolCallRecord>>();
  private thk: string[] = [];
  private ast: string[] = [];

  constructor(sessionId: string) { this.sid = sessionId; }

  startTurn(msg: string) {
    if (this.cur) this.seal();
    this.cur = { index: this.turns.length, userMessage: msg, assistantResponse: null, toolCalls: [], thinkingContent: null, firstEventLatency: 0, totalDuration: 0, eventCount: 0 };
    this.curStart = Date.now(); this.curN = 0; this.curTC = []; this.pending.clear(); this.thk = []; this.ast = [];
  }

  addEvent(ev: SSEEvent) {
    const now = Date.now(); this.curN++;
    if (this.cur && this.curN === 1) this.cur.firstEventLatency = now - this.curStart;
    const d = ev.data ?? {};
    switch (ev.event_type) {
      case 'assistant_chunk': if (d['chunk']) this.ast.push(d['chunk'] as string); break;
      case 'assistant_message': if (d['content'] && this.cur) this.cur.assistantResponse = d['content'] as string; break;
      case 'thinking_chunk': if (d['chunk']) this.thk.push(d['chunk'] as string); break;
      case 'tool_call': { const id = d['tool_call_id'] as string, nm = d['tool'] as string; if (id && nm) this.pending.set(id, { toolCallId: id, toolName: nm, arguments: (d['arguments'] as Record<string, unknown>) ?? {}, output: null, success: false, approvalRequired: false, duration: 0, timestamp: now }); break; }
      case 'tool_output': { const id = d['tool_call_id'] as string, p = id ? this.pending.get(id) : undefined; if (p) { p.output = (d['output'] as string) ?? null; p.success = (d['success'] as boolean) ?? true; p.duration = now - (p.timestamp ?? now); this.curTC.push(p as ToolCallRecord); this.allTC.push(p as ToolCallRecord); this.pending.delete(id); } break; }
      case 'approval_required': { for (const t of ((d['tools'] as Array<Record<string, unknown>>) ?? [])) { const p = this.pending.get(t['tool_call_id'] as string); if (p) p.approvalRequired = true; } break; }
      case 'turn_complete': { if (this.cur) { const fr = d['final_response'] as string | undefined; if (fr) this.cur.assistantResponse = fr; else if (!this.cur.assistantResponse && this.ast.length) this.cur.assistantResponse = this.ast.join(''); this.cur.totalDuration = now - this.curStart; } break; }
      case 'error': this.allErr.push({ message: (d['error'] as string) ?? 'Unknown', type: (d['error_type'] as string) ?? 'unknown', timestamp: now, turnIndex: this.cur?.index ?? null }); break;
      case 'compacted': this.compactions++; break;
    }
  }

  finalize(): Trace {
    if (this.cur) this.seal();
    const end = Date.now();
    return { sessionId: this.sid, startTime: this.t0, endTime: end, turns: this.turns, toolCalls: this.allTC, errors: this.allErr, metrics: this.metrics(end) };
  }

  private seal() {
    if (!this.cur) return;
    if (this.thk.length) this.cur.thinkingContent = this.thk.join('');
    if (!this.cur.assistantResponse && this.ast.length) this.cur.assistantResponse = this.ast.join('');
    this.cur.toolCalls = [...this.curTC]; this.cur.eventCount = this.curN;
    this.turns.push(this.cur as Turn); this.cur = null;
  }

  private metrics(end: number): TraceMetrics {
    const dur = this.turns.map(t => t.totalDuration), avg = dur.length ? dur.reduce((a, b) => a + b, 0) / dur.length : 0;
    const ok = this.allTC.filter(t => t.success).length;
    const lat = this.turns.map(t => t.firstEventLatency).filter(l => l > 0), avgL = lat.length ? lat.reduce((a, b) => a + b, 0) / lat.length : 0;
    return { totalTurns: this.turns.length, totalDuration: end - this.t0, avgTurnDuration: avg, totalToolCalls: this.allTC.length, successfulToolCalls: ok, toolSuccessRate: this.allTC.length ? ok / this.allTC.length : 1, errorCount: this.allErr.length, doomLoopDetected: this.doom(), approvalRequests: this.allTC.filter(t => t.approvalRequired).length, compactionCount: this.compactions, avgFirstEventLatency: avgL, totalEvents: this.turns.reduce((s, t) => s + t.eventCount, 0) };
  }

  private doom(): boolean {
    if (this.allTC.length < 5) return false;
    let s = 1; for (let i = 1; i < this.allTC.length; i++) { s = this.allTC[i].toolName === this.allTC[i - 1].toolName ? s + 1 : 1; if (s >= 5) return true; } return false;
  }
}
