import * as z from 'zod';

export const ApiRootSchema = z.object({
  name: z.string(),
  version: z.string(),
});
export type ApiRoot = z.infer<typeof ApiRootSchema>;

export const HealthResponseSchema = z.object({
  status: z.string(),
  active_sessions: z.number(),
  max_sessions: z.number(),
});
export type HealthResponse = z.infer<typeof HealthResponseSchema>;

export const LLMHealthResponseSchema = z.object({
  status: z.string(),
  model: z.string(),
  error: z.string().optional(),
  error_type: z.string().optional(),
});
export type LLMHealthResponse = z.infer<typeof LLMHealthResponseSchema>;

export const SessionResponseSchema = z.object({
  session_id: z.string(),
  ready: z.boolean(),
  model: z.string(),
});
export type SessionResponse = z.infer<typeof SessionResponseSchema>;

export const SessionInfoSchema = z.object({
  session_id: z.string(),
  is_active: z.boolean(),
  model: z.string(),
  turn_count: z.number(),
  runtime_state: z.string().optional(),
  title: z.string().nullable().optional(),
  pending_tools: z.array(z.record(z.unknown())).nullable().optional(),
  auto_approval: z.record(z.unknown()).optional(),
});
export type SessionInfo = z.infer<typeof SessionInfoSchema>;

export const SessionInfoListSchema = z.array(SessionInfoSchema);
export type SessionInfoList = z.infer<typeof SessionInfoListSchema>;

export const ModelEntrySchema = z.object({
  id: z.string(),
  label: z.string(),
  provider: z.string(),
  tier: z.string(),
  recommended: z.boolean().optional(),
});
export const ModelConfigSchema = z.object({
  current: z.string(),
  available: z.array(ModelEntrySchema),
});
export type ModelConfig = z.infer<typeof ModelConfigSchema>;

export interface SSEEvent {
  event_type: string;
  data: Record<string, unknown> | null;
  seq: number | null;
}

export interface ApprovalItem {
  tool_call_id: string;
  approved: boolean;
}
