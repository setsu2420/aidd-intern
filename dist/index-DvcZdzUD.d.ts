import { AgentClient } from './client/index.js';
import { a as Trace, b as TraceAnalysis } from './analyzer-DWhucvPg.js';

interface MetricsReport {
    testCaseId: string;
    timestamp: string;
    performance: {
        firstEventLatencyMs: number;
        totalDurationMs: number;
        eventsPerSecond: number;
        p95LatencyMs: number;
    };
    reliability: {
        errorCount: number;
        compactionCount: number;
        doomLoopDetected: boolean;
        turnCompletionRate: number;
    };
    efficiency: {
        totalToolCalls: number;
        toolSuccessRate: number;
        uniqueToolsUsed: number;
        avgToolDurationMs: number;
        approvalRequests: number;
    };
    traceQualityScore: number;
}
declare function computeMetrics(id: string, trace: Trace, analysis: TraceAnalysis): MetricsReport;
declare function aggregateMetrics(rs: MetricsReport[]): {
    count: number;
    avgQuality: number;
    avgDurationMs: number;
    totalErrors: number;
    avgToolSuccess: number;
    doomLoops: number;
};

interface Rubric {
    name: string;
    description: string;
    dimensions: {
        name: string;
        description: string;
        weight: number;
        criteria: string[];
    }[];
    maxScore: number;
}
declare const GENERAL_CAPABILITY_RUBRIC: Rubric;
declare const PROTEIN_DESIGN_RUBRIC: Rubric;

interface JudgeResult {
    overall: number;
    dimensions: Record<string, number>;
    reasoning: string;
    judgeModel: string;
    success: boolean;
    error?: string;
}
interface JudgeConfig {
    model: string;
    apiKey: string;
    apiBase?: string;
    temperature?: number;
}

interface EvalTestCase {
    id: string;
    name: string;
    prompt: string;
    expectedBehavior?: string;
    rubric?: Rubric;
    timeoutMs?: number;
}
interface EvalResult {
    testCase: EvalTestCase;
    trace: Trace;
    analysis: TraceAnalysis;
    metrics: MetricsReport;
    judgeResult: JudgeResult | null;
    passed: boolean;
}
declare function evaluateTestCase(client: AgentClient, sid: string, tc: EvalTestCase, opts?: {
    enableJudge?: boolean;
    judgeConfig?: JudgeConfig;
    minQualityScore?: number;
    defaultTimeoutMs?: number;
}): Promise<EvalResult>;

export { type EvalResult as E, GENERAL_CAPABILITY_RUBRIC as G, type MetricsReport as M, PROTEIN_DESIGN_RUBRIC as P, type EvalTestCase as a, aggregateMetrics as b, computeMetrics as c, evaluateTestCase as e };
