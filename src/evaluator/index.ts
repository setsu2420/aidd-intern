import { AgentClient } from '../client/index.js';
import { TraceCollector } from '../trace/collector.js';
import { analyzeTrace, type TraceAnalysis } from '../trace/analyzer.js';
import { computeMetrics, type MetricsReport } from './metrics.js';
import { evaluateWithJudge, type JudgeConfig, type JudgeResult } from './judge.js';
import { GENERAL_CAPABILITY_RUBRIC, type Rubric } from './rubrics.js';
import type { Trace } from '../trace/types.js';
import { createLogger } from '../utils/logger.js';
const log = createLogger('Evaluator');

export interface EvalTestCase { id: string; name: string; prompt: string; expectedBehavior?: string; rubric?: Rubric; timeoutMs?: number; }
export interface EvalResult { testCase: EvalTestCase; trace: Trace; analysis: TraceAnalysis; metrics: MetricsReport; judgeResult: JudgeResult | null; passed: boolean; }

export async function evaluateTestCase(client: AgentClient, sid: string, tc: EvalTestCase, opts: { enableJudge?: boolean; judgeConfig?: JudgeConfig; minQualityScore?: number; defaultTimeoutMs?: number } = {}): Promise<EvalResult> {
  log.info(`Evaluating: ${tc.name}`);
  const col = new TraceCollector(sid); col.startTurn(tc.prompt);
  const { events } = await client.submitAndCollect(sid, tc.prompt, { timeoutMs: tc.timeoutMs ?? opts.defaultTimeoutMs ?? 120_000, maxEvents: 500 });
  for (const ev of events) col.addEvent(ev);
  const trace = col.finalize(), analysis = analyzeTrace(trace), metrics = computeMetrics(tc.id, trace, analysis);
  let jr: JudgeResult | null = null;
  if (opts.enableJudge && opts.judgeConfig) jr = await evaluateWithJudge(trace, tc.rubric ?? GENERAL_CAPABILITY_RUBRIC, opts.judgeConfig);
  const passed = analysis.qualityScore >= (opts.minQualityScore ?? 50);
  log.info(`${passed ? '✅ PASS' : '❌ FAIL'} quality=${analysis.qualityScore}/100`);
  return { testCase: tc, trace, analysis, metrics, judgeResult: jr, passed };
}
