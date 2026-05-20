/**
 * Library entry — programmatic usage:
 *   import { AgentClient, TraceCollector, analyzeTrace } from 'aidd-intern';
 */
export { PACKAGE_DESCRIPTION, PACKAGE_NAME, PACKAGE_VERSION } from './manifest.js';
export { AgentClient, type AgentClientOptions } from './client/index.js';
export { parseSSEStream, collectSSEEvents } from './client/sse.js';
export type {
  ApiRoot,
  HealthResponse,
  LLMHealthResponse,
  SessionResponse,
  SessionInfo,
  SessionInfoList,
  ModelConfig,
  SSEEvent,
} from './client/types.js';
export { TraceCollector } from './trace/index.js';
export { analyzeTrace, type TraceAnalysis } from './trace/index.js';
export type { Trace, Turn, ToolCallRecord, TraceMetrics } from './trace/index.js';
export { evaluateTestCase, type EvalTestCase, type EvalResult } from './evaluator/index.js';
export { computeMetrics, aggregateMetrics, type MetricsReport } from './evaluator/metrics.js';
export { GENERAL_CAPABILITY_RUBRIC, PROTEIN_DESIGN_RUBRIC } from './evaluator/rubrics.js';
export {
  DEFAULT_BACKEND_URL,
  DEFAULT_JUDGE_MODEL,
  createLogger,
  loadEnv,
  printSuiteSummary,
  setLogLevel,
  summarize,
  type CheckResult,
  type CheckStatus,
  type CommandEnv,
  type RuntimeEnv,
} from './utils/index.js';
export {
  DEFAULT_EVAL_FIXTURE_PATH,
  loadEvalTestCases,
  runEval,
  runIntegration,
  runSmoke,
  type EvalEnv,
  type EvalOptions,
} from './commands/index.js';
