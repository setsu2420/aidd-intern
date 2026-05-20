import chalk from 'chalk';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AgentClient } from '../client/index.js';
import { evaluateTestCase, type EvalTestCase, type EvalResult } from '../evaluator/index.js';
import { aggregateMetrics } from '../evaluator/metrics.js';
import type { CommandEnv } from '../utils/env.js';
import { createLogger } from '../utils/logger.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
export const DEFAULT_EVAL_FIXTURE_PATH = resolve(__dirname, '../../fixtures/prompts.json');
const log = createLogger('Eval');

type Env = CommandEnv;

interface EvalOptions {
  enableJudge: boolean;
  fixturesPath?: string;
  limit?: number;
}

export function loadEvalTestCases(fixturePath = DEFAULT_EVAL_FIXTURE_PATH, limit?: number): EvalTestCase[] {
  const raw = readFileSync(fixturePath, 'utf-8');
  const parsed = JSON.parse(raw) as { testCases?: unknown };

  if (!Array.isArray(parsed.testCases) || parsed.testCases.length === 0) {
    throw new Error(`No eval test cases found in ${fixturePath}`);
  }

  const testCases = parsed.testCases.map((value, index) => normalizeTestCase(value, index, fixturePath));
  return typeof limit === 'number' && limit > 0 ? testCases.slice(0, limit) : testCases;
}

export async function runEval(env: Env, opts: EvalOptions): Promise<boolean> {
  const client = new AgentClient({
    baseUrl: env.backendUrl,
    hfToken: env.hfToken,
    timeoutMs: 60_000,
  });
  const testCases = loadEvalTestCases(opts.fixturesPath, opts.limit);

  log.step(0, 'Create eval session');
  let sessionId: string;
  try {
    const session = await client.createSession(env.testModel);
    sessionId = session.session_id;
    log.info(`${sessionId} (${session.model})`);
  } catch (error) {
    log.fail(String(error));
    return false;
  }

  const results: EvalResult[] = [];
  let failedCount = 0;
  const judgeConfig = opts.enableJudge && env.judgeApiKey
    ? {
        model: env.judgeModel,
        apiKey: env.judgeApiKey,
      }
    : undefined;

  if (opts.enableJudge && !judgeConfig) {
    log.warn('LLM-as-judge requested, but no judge API key is configured. Skipping judge scoring.');
  }

  try {
    for (let index = 0; index < testCases.length; index++) {
      const testCase = testCases[index];
      log.step(index + 1, testCase.name);

      try {
        const result = await evaluateTestCase(client, sessionId, testCase, {
          enableJudge: !!judgeConfig,
          judgeConfig,
          minQualityScore: 40,
          defaultTimeoutMs: 180_000,
        });
        results.push(result);

        log.info(
          `Quality: ${result.analysis.qualityScore}/100, Duration: ${(result.trace.metrics.totalDuration / 1000).toFixed(1)}s`,
        );
        result.passed
          ? log.ok(`${testCase.name} PASSED`)
          : log.fail(`${testCase.name} FAILED`);
      } catch (error) {
        failedCount += 1;
        log.fail(`${testCase.name}: ${String(error)}`);
      }
    }
  } finally {
    try {
      await client.deleteSession(sessionId);
    } catch {
      // Best-effort cleanup only.
    }
  }

  printEvalSummary(results, env.jsonOutput, failedCount);
  return results.length > 0 && failedCount === 0 && results.every((result) => result.passed);
}

function printEvalSummary(results: EvalResult[], json: boolean, failedCount: number): void {
  if (json) {
    const summary = aggregateMetrics(results.map((result) => result.metrics));
    const passed = results.filter((result) => result.passed).length;

    console.log(
      JSON.stringify(
        {
          suite: 'EVAL',
          summary: {
            ...summary,
            passed,
            failedCases: failedCount,
            failed: failedCount,
          },
          results: results.map((result) => ({
            id: result.testCase.id,
            name: result.testCase.name,
            passed: result.passed,
            quality: result.analysis.qualityScore,
            durationMs: result.trace.metrics.totalDuration,
            issues: result.analysis.issues,
            judgeResult: result.judgeResult,
          })),
        },
        null,
        2,
      ),
    );
    return;
  }

  console.log(`\n${chalk.bold.blue('═══ EVAL ═══')}`);
  for (const result of results) {
    const icon = result.passed ? chalk.green('✅') : chalk.red('❌');
    console.log(
      `  ${icon} ${result.testCase.name} — q=${result.analysis.qualityScore}/100, ${(result.trace.metrics.totalDuration / 1000).toFixed(1)}s`,
    );
    if (result.judgeResult?.success) {
      console.log(`     Judge: ${result.judgeResult.overall}/10`);
    }
    for (const issue of result.analysis.issues.slice(0, 2)) {
      console.log(
        `     ${issue.severity === 'critical' ? '🔴' : '🟡'} ${issue.message.slice(0, 120)}`,
      );
    }
  }
  const passed = results.filter((result) => result.passed).length;
  console.log(`\n  ${chalk.bold(`${passed}/${results.length} passed, ${failedCount} failed`)}\n`);
}

function normalizeTestCase(value: unknown, index: number, fixturePath: string): EvalTestCase {
  if (!value || typeof value !== 'object') {
    throw new Error(`Invalid test case #${index + 1} in ${fixturePath}: expected an object`);
  }

  const candidate = value as Partial<EvalTestCase>;
  if (typeof candidate.id !== 'string' || typeof candidate.name !== 'string' || typeof candidate.prompt !== 'string') {
    throw new Error(`Invalid test case #${index + 1} in ${fixturePath}: id, name, and prompt are required strings`);
  }

  return {
    id: candidate.id,
    name: candidate.name,
    prompt: candidate.prompt,
    expectedBehavior: typeof candidate.expectedBehavior === 'string' ? candidate.expectedBehavior : undefined,
    rubric: candidate.rubric,
    timeoutMs: typeof candidate.timeoutMs === 'number' ? candidate.timeoutMs : undefined,
  };
}

export type { Env as EvalEnv, EvalOptions };
