import * as z from 'zod';

declare const ApiRootSchema: z.ZodObject<{
    name: z.ZodString;
    version: z.ZodString;
}, "strip", z.ZodTypeAny, {
    name: string;
    version: string;
}, {
    name: string;
    version: string;
}>;
type ApiRoot = z.infer<typeof ApiRootSchema>;
declare const HealthResponseSchema: z.ZodObject<{
    status: z.ZodString;
    active_sessions: z.ZodNumber;
    max_sessions: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    status: string;
    active_sessions: number;
    max_sessions: number;
}, {
    status: string;
    active_sessions: number;
    max_sessions: number;
}>;
type HealthResponse = z.infer<typeof HealthResponseSchema>;
declare const LLMHealthResponseSchema: z.ZodObject<{
    status: z.ZodString;
    model: z.ZodString;
    error: z.ZodOptional<z.ZodString>;
    error_type: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    status: string;
    model: string;
    error?: string | undefined;
    error_type?: string | undefined;
}, {
    status: string;
    model: string;
    error?: string | undefined;
    error_type?: string | undefined;
}>;
type LLMHealthResponse = z.infer<typeof LLMHealthResponseSchema>;
declare const SessionResponseSchema: z.ZodObject<{
    session_id: z.ZodString;
    ready: z.ZodBoolean;
    model: z.ZodString;
}, "strip", z.ZodTypeAny, {
    model: string;
    session_id: string;
    ready: boolean;
}, {
    model: string;
    session_id: string;
    ready: boolean;
}>;
type SessionResponse = z.infer<typeof SessionResponseSchema>;
declare const SessionInfoSchema: z.ZodObject<{
    session_id: z.ZodString;
    is_active: z.ZodBoolean;
    model: z.ZodString;
    turn_count: z.ZodNumber;
    runtime_state: z.ZodOptional<z.ZodString>;
    title: z.ZodOptional<z.ZodNullable<z.ZodString>>;
    pending_tools: z.ZodOptional<z.ZodNullable<z.ZodArray<z.ZodRecord<z.ZodString, z.ZodUnknown>, "many">>>;
    auto_approval: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodUnknown>>;
}, "strip", z.ZodTypeAny, {
    model: string;
    session_id: string;
    is_active: boolean;
    turn_count: number;
    runtime_state?: string | undefined;
    title?: string | null | undefined;
    pending_tools?: Record<string, unknown>[] | null | undefined;
    auto_approval?: Record<string, unknown> | undefined;
}, {
    model: string;
    session_id: string;
    is_active: boolean;
    turn_count: number;
    runtime_state?: string | undefined;
    title?: string | null | undefined;
    pending_tools?: Record<string, unknown>[] | null | undefined;
    auto_approval?: Record<string, unknown> | undefined;
}>;
type SessionInfo = z.infer<typeof SessionInfoSchema>;
declare const SessionInfoListSchema: z.ZodArray<z.ZodObject<{
    session_id: z.ZodString;
    is_active: z.ZodBoolean;
    model: z.ZodString;
    turn_count: z.ZodNumber;
    runtime_state: z.ZodOptional<z.ZodString>;
    title: z.ZodOptional<z.ZodNullable<z.ZodString>>;
    pending_tools: z.ZodOptional<z.ZodNullable<z.ZodArray<z.ZodRecord<z.ZodString, z.ZodUnknown>, "many">>>;
    auto_approval: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodUnknown>>;
}, "strip", z.ZodTypeAny, {
    model: string;
    session_id: string;
    is_active: boolean;
    turn_count: number;
    runtime_state?: string | undefined;
    title?: string | null | undefined;
    pending_tools?: Record<string, unknown>[] | null | undefined;
    auto_approval?: Record<string, unknown> | undefined;
}, {
    model: string;
    session_id: string;
    is_active: boolean;
    turn_count: number;
    runtime_state?: string | undefined;
    title?: string | null | undefined;
    pending_tools?: Record<string, unknown>[] | null | undefined;
    auto_approval?: Record<string, unknown> | undefined;
}>, "many">;
type SessionInfoList = z.infer<typeof SessionInfoListSchema>;
declare const ModelConfigSchema: z.ZodObject<{
    current: z.ZodString;
    available: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        label: z.ZodString;
        provider: z.ZodString;
        tier: z.ZodString;
        recommended: z.ZodOptional<z.ZodBoolean>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        label: string;
        provider: string;
        tier: string;
        recommended?: boolean | undefined;
    }, {
        id: string;
        label: string;
        provider: string;
        tier: string;
        recommended?: boolean | undefined;
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    current: string;
    available: {
        id: string;
        label: string;
        provider: string;
        tier: string;
        recommended?: boolean | undefined;
    }[];
}, {
    current: string;
    available: {
        id: string;
        label: string;
        provider: string;
        tier: string;
        recommended?: boolean | undefined;
    }[];
}>;
type ModelConfig = z.infer<typeof ModelConfigSchema>;
interface SSEEvent {
    event_type: string;
    data: Record<string, unknown> | null;
    seq: number | null;
}
interface ApprovalItem {
    tool_call_id: string;
    approved: boolean;
}

export type { ApiRoot as A, HealthResponse as H, LLMHealthResponse as L, ModelConfig as M, SSEEvent as S, ApprovalItem as a, SessionInfo as b, SessionInfoList as c, SessionResponse as d };
