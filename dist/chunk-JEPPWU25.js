import {
  createLogger
} from "./chunk-OA6CDQ5U.js";

// src/client/sse.ts
async function* parseSSEStream(response) {
  if (!response.body) {
    throw new Error("SSE response has no body");
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const event = parseBlock(part.trim());
        if (event) yield event;
      }
    }
    if (buffer.trim()) {
      const event = parseBlock(buffer.trim());
      if (event) yield event;
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
    }
    reader.releaseLock();
  }
}
async function collectSSEEvents(response, opts = {}) {
  const events = [];
  const maxEvents = opts.maxEvents ?? 500;
  const timeoutMs = opts.timeoutMs ?? 12e4;
  let timeoutId;
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`SSE timeout after ${timeoutMs}ms`)), timeoutMs);
  });
  const collectPromise = (async () => {
    for await (const event of parseSSEStream(response)) {
      events.push(event);
      if (opts.stopAfter && event.event_type === opts.stopAfter) {
        break;
      }
      if (events.length >= maxEvents) {
        break;
      }
    }
  })();
  try {
    await Promise.race([collectPromise, timeoutPromise]);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!message.startsWith("SSE timeout")) {
      throw error;
    }
    await response.body?.cancel().catch(() => void 0);
    if (events.length === 0) {
      throw error;
    }
  } finally {
    if (timeoutId !== void 0) {
      clearTimeout(timeoutId);
    }
  }
  return events;
}
function parseBlock(block) {
  if (!block) {
    return null;
  }
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  const data = dataLines.join("\n").trim();
  if (!data || data === "[DONE]") {
    return null;
  }
  try {
    const payload = JSON.parse(data);
    return {
      event_type: payload.event_type ?? "unknown",
      data: payload.data ?? payload,
      seq: payload.seq ?? null
    };
  } catch {
    return null;
  }
}

// src/client/types.ts
import * as z from "zod";
var ApiRootSchema = z.object({
  name: z.string(),
  version: z.string()
});
var HealthResponseSchema = z.object({
  status: z.string(),
  active_sessions: z.number(),
  max_sessions: z.number()
});
var LLMHealthResponseSchema = z.object({
  status: z.string(),
  model: z.string(),
  error: z.string().optional(),
  error_type: z.string().optional()
});
var SessionResponseSchema = z.object({
  session_id: z.string(),
  ready: z.boolean(),
  model: z.string()
});
var SessionInfoSchema = z.object({
  session_id: z.string(),
  is_active: z.boolean(),
  model: z.string(),
  turn_count: z.number(),
  runtime_state: z.string().optional(),
  title: z.string().nullable().optional(),
  pending_tools: z.array(z.record(z.unknown())).nullable().optional(),
  auto_approval: z.record(z.unknown()).optional()
});
var SessionInfoListSchema = z.array(SessionInfoSchema);
var ModelEntrySchema = z.object({
  id: z.string(),
  label: z.string(),
  provider: z.string(),
  tier: z.string(),
  recommended: z.boolean().optional()
});
var ModelConfigSchema = z.object({
  current: z.string(),
  available: z.array(ModelEntrySchema)
});

// src/client/index.ts
var log = createLogger("Client");
var AgentClient = class {
  baseUrl;
  hfToken;
  timeoutMs;
  constructor(opts) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.hfToken = opts.hfToken;
    this.timeoutMs = opts.timeoutMs ?? 3e4;
  }
  jsonHeaders(includeBody) {
    const h = { Accept: "application/json" };
    if (includeBody) {
      h["Content-Type"] = "application/json";
    }
    if (this.hfToken) h["Authorization"] = `Bearer ${this.hfToken}`;
    return h;
  }
  sseHeaders(includeBody) {
    const h = { Accept: "text/event-stream" };
    if (includeBody) {
      h["Content-Type"] = "application/json";
    }
    if (this.hfToken) h["Authorization"] = `Bearer ${this.hfToken}`;
    return h;
  }
  /** Generic JSON request with optional Zod validation. */
  async request(method, path, body, schema) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const hasBody = body !== void 0;
      const res = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.jsonHeaders(hasBody),
        body: hasBody ? JSON.stringify(body) : void 0,
        signal: ctrl.signal
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status} ${method} ${path}: ${txt.slice(0, 300)}`);
      }
      const raw = await res.text();
      if (!raw.trim()) {
        return void 0;
      }
      const json = JSON.parse(raw);
      if (schema) {
        const parsed = schema.safeParse(json);
        if (!parsed.success) {
          throw new Error(`Invalid ${method} ${path} response: ${parsed.error.message}`);
        }
        return parsed.data;
      }
      return json;
    } finally {
      clearTimeout(timer);
    }
  }
  /** Streaming request — no timeout (SSE collector handles it). */
  async stream(method, path, body) {
    const hasBody = body !== void 0;
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: this.sseHeaders(hasBody),
      body: hasBody ? JSON.stringify(body) : void 0
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${method} ${path}: ${txt.slice(0, 200)}`);
    }
    return res;
  }
  // ── Health (no auth) ──────────────────────────────────────────────
  async apiRoot() {
    return this.request("GET", "/api", void 0, ApiRootSchema);
  }
  async healthCheck() {
    return this.request("GET", "/api/health", void 0, HealthResponseSchema);
  }
  async llmHealthCheck() {
    return this.request("GET", "/api/health/llm", void 0, LLMHealthResponseSchema);
  }
  // ── Models ────────────────────────────────────────────────────────
  async getModelConfig() {
    return this.request("GET", "/api/config/model", void 0, ModelConfigSchema);
  }
  // ── Sessions ──────────────────────────────────────────────────────
  async createSession(model) {
    return this.request(
      "POST",
      "/api/session",
      model ? { model } : void 0,
      SessionResponseSchema
    );
  }
  async getSession(id) {
    return this.request("GET", `/api/session/${id}`, void 0, SessionInfoSchema);
  }
  async listSessions() {
    return this.request("GET", "/api/sessions", void 0, SessionInfoListSchema);
  }
  async deleteSession(id) {
    await this.request("DELETE", `/api/session/${id}`);
  }
  // ── Chat (SSE streaming) ──────────────────────────────────────────
  async *submitMessage(sessionId, text) {
    const res = await this.stream("POST", "/api/submit", { session_id: sessionId, text });
    yield* parseSSEStream(res);
  }
  async submitAndCollect(sessionId, text, opts) {
    log.info(`Submit \u2192 "${text.slice(0, 60)}\u2026"`);
    const res = await this.stream("POST", "/api/submit", { session_id: sessionId, text });
    const events = await collectSSEEvents(res, {
      stopAfter: "turn_complete",
      timeoutMs: opts?.timeoutMs ?? 12e4,
      maxEvents: opts?.maxEvents ?? 500
    });
    const tc = events.find((e) => e.event_type === "turn_complete");
    const response = tc?.data ? tc.data["final_response"] ?? null : null;
    return { events, response };
  }
  // ── Approvals ─────────────────────────────────────────────────────
  async *approveTools(sessionId, approvals) {
    const res = await this.stream("POST", "/api/approve", { session_id: sessionId, approvals });
    yield* parseSSEStream(res);
  }
};

export {
  parseSSEStream,
  collectSSEEvents,
  AgentClient
};
//# sourceMappingURL=chunk-JEPPWU25.js.map