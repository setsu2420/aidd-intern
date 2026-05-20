import { A as ApiRoot, H as HealthResponse, L as LLMHealthResponse, M as ModelConfig, d as SessionResponse, b as SessionInfo, S as SSEEvent, a as ApprovalItem } from '../types-CDvLvuOf.js';
import 'zod';

interface AgentClientOptions {
    baseUrl: string;
    hfToken?: string;
    timeoutMs?: number;
}
declare class AgentClient {
    readonly baseUrl: string;
    private readonly hfToken?;
    private readonly timeoutMs;
    constructor(opts: AgentClientOptions);
    private jsonHeaders;
    private sseHeaders;
    /** Generic JSON request with optional Zod validation. */
    private request;
    /** Streaming request — no timeout (SSE collector handles it). */
    private stream;
    apiRoot(): Promise<ApiRoot>;
    healthCheck(): Promise<HealthResponse>;
    llmHealthCheck(): Promise<LLMHealthResponse>;
    getModelConfig(): Promise<ModelConfig>;
    createSession(model?: string): Promise<SessionResponse>;
    getSession(id: string): Promise<SessionInfo>;
    listSessions(): Promise<SessionInfo[]>;
    deleteSession(id: string): Promise<void>;
    submitMessage(sessionId: string, text: string): AsyncGenerator<SSEEvent>;
    submitAndCollect(sessionId: string, text: string, opts?: {
        timeoutMs?: number;
        maxEvents?: number;
    }): Promise<{
        events: SSEEvent[];
        response: string | null;
    }>;
    approveTools(sessionId: string, approvals: ApprovalItem[]): AsyncGenerator<SSEEvent>;
}

export { AgentClient, type AgentClientOptions };
