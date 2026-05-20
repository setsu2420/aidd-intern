import type { Trace } from '../trace/types.js';
import type { Rubric } from './rubrics.js';
import { formatRubricForPrompt } from './rubrics.js';
import { createLogger } from '../utils/logger.js';
const log = createLogger('Judge');
export interface JudgeResult { overall: number; dimensions: Record<string, number>; reasoning: string; judgeModel: string; success: boolean; error?: string; }
export interface JudgeConfig { model: string; apiKey: string; apiBase?: string; temperature?: number; }

export async function evaluateWithJudge(trace: Trace, rubric: Rubric, config: JudgeConfig): Promise<JudgeResult> {
  log.info(`Judging ${trace.sessionId} with ${config.model}`);
  try {
    const lines = [`Session: ${trace.sessionId}`, `Duration: ${(trace.metrics.totalDuration / 1000).toFixed(1)}s`, `Tools: ${trace.metrics.totalToolCalls}`, `Errors: ${trace.metrics.errorCount}`, ''];
    for (const t of trace.turns) { lines.push(`--- Turn ${t.index + 1} ---`, `User: ${t.userMessage.slice(0, 300)}`); if (t.toolCalls.length) lines.push(`Tools: ${t.toolCalls.map(c => `${c.toolName}(${c.success ? 'ok' : 'fail'})`).join(', ')}`); lines.push(`Assistant: ${(t.assistantResponse ?? '(none)').slice(0, 500)}`, ''); }
    const prompt = `Evaluate this agent trace:\n\n${lines.join('\n')}\n\n${formatRubricForPrompt(rubric)}\n\nJSON: {"dimensions": {${rubric.dimensions.map(d => `"${d.name}": <0-${rubric.maxScore}>`).join(', ')}}, "reasoning": "...", "overall": <weighted>}`;
    const base = config.apiBase ?? 'https://api.openai.com/v1';
    const res = await fetch(`${base}/chat/completions`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.apiKey}` }, body: JSON.stringify({ model: config.model.replace(/^openai\//, ''), messages: [{ role: 'system', content: 'Respond JSON only.' }, { role: 'user', content: prompt }], temperature: config.temperature ?? 0.1, max_tokens: 1024 }) });
    if (!res.ok) throw new Error(`Judge API ${res.status}`);
    const raw = ((await res.json()) as { choices: { message: { content: string } }[] }).choices[0]?.message?.content ?? '';
    let json = raw.trim(); const m = json.match(/```(?:json)?\s*([\s\S]*?)\s*```/); if (m) json = m[1];
    const p = JSON.parse(json) as { dimensions: Record<string, number>; reasoning: string };
    const dims: Record<string, number> = {}; let overall = 0;
    for (const d of rubric.dimensions) { dims[d.name] = Math.max(0, Math.min(rubric.maxScore, Number(p.dimensions?.[d.name] ?? 0))); overall += dims[d.name] * d.weight; }
    return { overall: Math.round(overall * 10) / 10, dimensions: dims, reasoning: p.reasoning ?? '', judgeModel: config.model, success: true };
  } catch (e) { const msg = e instanceof Error ? e.message : String(e); log.error(msg); return { overall: 0, dimensions: {}, reasoning: msg, judgeModel: config.model, success: false, error: msg }; }
}
