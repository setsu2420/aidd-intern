interface Trace {
    sessionId: string;
    startTime: number;
    endTime: number;
    turns: Turn[];
    toolCalls: ToolCallRecord[];
    errors: ErrorRecord[];
    metrics: TraceMetrics;
}
interface Turn {
    index: number;
    userMessage: string;
    assistantResponse: string | null;
    toolCalls: ToolCallRecord[];
    thinkingContent: string | null;
    firstEventLatency: number;
    totalDuration: number;
    eventCount: number;
}
interface ToolCallRecord {
    toolCallId: string;
    toolName: string;
    arguments: Record<string, unknown>;
    output: string | null;
    success: boolean;
    approvalRequired: boolean;
    duration: number;
    timestamp: number;
}
interface ErrorRecord {
    message: string;
    type: string;
    timestamp: number;
    turnIndex: number | null;
}
interface TraceMetrics {
    totalTurns: number;
    totalDuration: number;
    avgTurnDuration: number;
    totalToolCalls: number;
    successfulToolCalls: number;
    toolSuccessRate: number;
    errorCount: number;
    doomLoopDetected: boolean;
    approvalRequests: number;
    compactionCount: number;
    avgFirstEventLatency: number;
    totalEvents: number;
}

interface TraceAnalysis {
    qualityScore: number;
    issues: {
        severity: 'critical' | 'warning' | 'info';
        category: string;
        message: string;
    }[];
    strengths: string[];
    performance: {
        avgLatency: number;
        p95Latency: number;
        avgTurnDuration: number;
        maxTurnDuration: number;
        eventsPerSecond: number;
    };
    toolUsage: {
        uniqueTools: string[];
        mostUsed: string | null;
        successRate: number;
        failedTools: string[];
    };
}
declare function analyzeTrace(trace: Trace): TraceAnalysis;

export { type ToolCallRecord as T, type Trace as a, type TraceAnalysis as b, type TraceMetrics as c, type Turn as d, analyzeTrace as e };
