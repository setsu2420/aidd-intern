import { S as SSEEvent } from '../types-CDvLvuOf.js';
import { a as Trace } from '../analyzer-DWhucvPg.js';
export { T as ToolCallRecord, b as TraceAnalysis, c as TraceMetrics, d as Turn, e as analyzeTrace } from '../analyzer-DWhucvPg.js';
import 'zod';

declare class TraceCollector {
    private readonly sid;
    private readonly t0;
    private turns;
    private allTC;
    private allErr;
    private compactions;
    private cur;
    private curStart;
    private curN;
    private curTC;
    private pending;
    private thk;
    private ast;
    constructor(sessionId: string);
    startTurn(msg: string): void;
    addEvent(ev: SSEEvent): void;
    finalize(): Trace;
    private seal;
    private metrics;
    private doom;
}

export { Trace, TraceCollector };
