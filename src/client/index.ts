/**
 * AgentClient — type-safe HTTP + SSE client for aidd-intern backend.
 *
 * All public methods have explicit return types for safety even without
 * node_modules installed.
 */
import { type ZodType } from 'zod';
import { createLogger } from '../utils/logger.js';
import { parseSSEStream, collectSSEEvents } from './sse.js';
import {
  type ApiRoot,
  type HealthResponse,
  type LLMHealthResponse,
  type SessionResponse,
  type SessionInfo,
  type ModelConfig,
  type SSEEvent,
  type ApprovalItem,
  ApiRootSchema,
  HealthResponseSchema,
  LLMHealthResponseSchema,
  SessionResponseSchema,
  SessionInfoSchema,
  SessionInfoListSchema,
  ModelConfigSchema,
} from './types.js';

const log = createLogger('Client');

export interface AgentClientOptions {
  baseUrl: string;
  hfToken?: string;
  timeoutMs?: number;
}

export class AgentClient {
  readonly baseUrl: string;
  private readonly hfToken?: string;
  private readonly timeoutMs: number;

  constructor(opts: AgentClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, '');
    this.hfToken = opts.hfToken;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
  }

  private jsonHeaders(includeBody: boolean): Record<string, string> {
    const h: Record<string, string> = { Accept: 'application/json' };
    if (includeBody) {
      h['Content-Type'] = 'application/json';
    }
    if (this.hfToken) h['Authorization'] = `Bearer ${this.hfToken}`;
    return h;
  }

  private sseHeaders(includeBody: boolean): Record<string, string> {
    const h: Record<string, string> = { Accept: 'text/event-stream' };
    if (includeBody) {
      h['Content-Type'] = 'application/json';
    }
    if (this.hfToken) h['Authorization'] = `Bearer ${this.hfToken}`;
    return h;
  }

  /** Generic JSON request with optional Zod validation. */
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    schema?: ZodType<T>,
  ): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const hasBody = body !== undefined;
      const res = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.jsonHeaders(hasBody),
        body: hasBody ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status} ${method} ${path}: ${txt.slice(0, 300)}`);
      }
      const raw = await res.text();
      if (!raw.trim()) {
        return undefined as T;
      }
      const json: unknown = JSON.parse(raw);
      if (schema) {
        const parsed = schema.safeParse(json);
        if (!parsed.success) {
          throw new Error(`Invalid ${method} ${path} response: ${parsed.error.message}`);
        }
        return parsed.data;
      }
      return json as T;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Streaming request — no timeout (SSE collector handles it). */
  private async stream(method: string, path: string, body?: unknown): Promise<Response> {
    const hasBody = body !== undefined;
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: this.sseHeaders(hasBody),
      body: hasBody ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status} ${method} ${path}: ${txt.slice(0, 200)}`);
    }
    return res;
  }

  // ── Health (no auth) ──────────────────────────────────────────────

  async apiRoot(): Promise<ApiRoot> {
    return this.request<ApiRoot>('GET', '/api', undefined, ApiRootSchema);
  }

  async healthCheck(): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/api/health', undefined, HealthResponseSchema);
  }

  async llmHealthCheck(): Promise<LLMHealthResponse> {
    return this.request<LLMHealthResponse>('GET', '/api/health/llm', undefined, LLMHealthResponseSchema);
  }

  // ── Models ────────────────────────────────────────────────────────

  async getModelConfig(): Promise<ModelConfig> {
    return this.request<ModelConfig>('GET', '/api/config/model', undefined, ModelConfigSchema);
  }

  // ── Sessions ──────────────────────────────────────────────────────

  async createSession(model?: string): Promise<SessionResponse> {
    return this.request<SessionResponse>(
      'POST', '/api/session',
      model ? { model } : undefined,
      SessionResponseSchema,
    );
  }

  async getSession(id: string): Promise<SessionInfo> {
    return this.request<SessionInfo>('GET', `/api/session/${id}`, undefined, SessionInfoSchema);
  }

  async listSessions(): Promise<SessionInfo[]> {
    return this.request<SessionInfo[]>('GET', '/api/sessions', undefined, SessionInfoListSchema);
  }

  async deleteSession(id: string): Promise<void> {
    await this.request<unknown>('DELETE', `/api/session/${id}`);
  }

  // ── Chat (SSE streaming) ──────────────────────────────────────────

  async *submitMessage(sessionId: string, text: string): AsyncGenerator<SSEEvent> {
    const res = await this.stream('POST', '/api/submit', { session_id: sessionId, text });
    yield* parseSSEStream(res);
  }

  async submitAndCollect(
    sessionId: string,
    text: string,
    opts?: { timeoutMs?: number; maxEvents?: number },
  ): Promise<{ events: SSEEvent[]; response: string | null }> {
    log.info(`Submit → "${text.slice(0, 60)}…"`);
    const res = await this.stream('POST', '/api/submit', { session_id: sessionId, text });
    const events = await collectSSEEvents(res, {
      stopAfter: 'turn_complete',
      timeoutMs: opts?.timeoutMs ?? 120_000,
      maxEvents: opts?.maxEvents ?? 500,
    });
    const tc = events.find(e => e.event_type === 'turn_complete');
    const response = tc?.data
      ? (tc.data['final_response'] as string) ?? null
      : null;
    return { events, response };
  }

  // ── Approvals ─────────────────────────────────────────────────────

  async *approveTools(sessionId: string, approvals: ApprovalItem[]): AsyncGenerator<SSEEvent> {
    const res = await this.stream('POST', '/api/approve', { session_id: sessionId, approvals });
    yield* parseSSEStream(res);
  }
}
