import {
  aggregateMetrics,
  evaluateTestCase
} from "./chunk-4XWDWTMQ.js";
import {
  AgentClient
} from "./chunk-JEPPWU25.js";
import {
  createLogger
} from "./chunk-OA6CDQ5U.js";

// src/commands/eval.ts
import chalk from "chalk";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
var __dirname = dirname(fileURLToPath(import.meta.url));
var DEFAULT_EVAL_FIXTURE_PATH = resolve(__dirname, "../../fixtures/prompts.json");
var log = createLogger("Eval");
function loadEvalTestCases(fixturePath = DEFAULT_EVAL_FIXTURE_PATH, limit) {
  const raw = readFileSync(fixturePath, "utf-8");
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed.testCases) || parsed.testCases.length === 0) {
    throw new Error(`No eval test cases found in ${fixturePath}`);
  }
  const testCases = parsed.testCases.map((value, index) => normalizeTestCase(value, index, fixturePath));
  return typeof limit === "number" && limit > 0 ? testCases.slice(0, limit) : testCases;
}
async function runEval(env, opts) {
  const client = new AgentClient({
    baseUrl: env.backendUrl,
    hfToken: env.hfToken,
    timeoutMs: 6e4
  });
  const testCases = loadEvalTestCases(opts.fixturesPath, opts.limit);
  log.step(0, "Create eval session");
  let sessionId;
  try {
    const session = await client.createSession(env.testModel);
    sessionId = session.session_id;
    log.info(`${sessionId} (${session.model})`);
  } catch (error) {
    log.fail(String(error));
    return false;
  }
  const results = [];
  let failedCount = 0;
  const judgeConfig = opts.enableJudge && env.judgeApiKey ? {
    model: env.judgeModel,
    apiKey: env.judgeApiKey
  } : void 0;
  if (opts.enableJudge && !judgeConfig) {
    log.warn("LLM-as-judge requested, but no judge API key is configured. Skipping judge scoring.");
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
          defaultTimeoutMs: 18e4
        });
        results.push(result);
        log.info(
          `Quality: ${result.analysis.qualityScore}/100, Duration: ${(result.trace.metrics.totalDuration / 1e3).toFixed(1)}s`
        );
        result.passed ? log.ok(`${testCase.name} PASSED`) : log.fail(`${testCase.name} FAILED`);
      } catch (error) {
        failedCount += 1;
        log.fail(`${testCase.name}: ${String(error)}`);
      }
    }
  } finally {
    try {
      await client.deleteSession(sessionId);
    } catch {
    }
  }
  printEvalSummary(results, env.jsonOutput, failedCount);
  return results.length > 0 && failedCount === 0 && results.every((result) => result.passed);
}
function printEvalSummary(results, json, failedCount) {
  if (json) {
    const summary = aggregateMetrics(results.map((result) => result.metrics));
    const passed2 = results.filter((result) => result.passed).length;
    console.log(
      JSON.stringify(
        {
          suite: "EVAL",
          summary: {
            ...summary,
            passed: passed2,
            failedCases: failedCount,
            failed: failedCount
          },
          results: results.map((result) => ({
            id: result.testCase.id,
            name: result.testCase.name,
            passed: result.passed,
            quality: result.analysis.qualityScore,
            durationMs: result.trace.metrics.totalDuration,
            issues: result.analysis.issues,
            judgeResult: result.judgeResult
          }))
        },
        null,
        2
      )
    );
    return;
  }
  console.log(`
${chalk.bold.blue("\u2550\u2550\u2550 EVAL \u2550\u2550\u2550")}`);
  for (const result of results) {
    const icon = result.passed ? chalk.green("\u2705") : chalk.red("\u274C");
    console.log(
      `  ${icon} ${result.testCase.name} \u2014 q=${result.analysis.qualityScore}/100, ${(result.trace.metrics.totalDuration / 1e3).toFixed(1)}s`
    );
    if (result.judgeResult?.success) {
      console.log(`     Judge: ${result.judgeResult.overall}/10`);
    }
    for (const issue of result.analysis.issues.slice(0, 2)) {
      console.log(
        `     ${issue.severity === "critical" ? "\u{1F534}" : "\u{1F7E1}"} ${issue.message.slice(0, 120)}`
      );
    }
  }
  const passed = results.filter((result) => result.passed).length;
  console.log(`
  ${chalk.bold(`${passed}/${results.length} passed, ${failedCount} failed`)}
`);
}
function normalizeTestCase(value, index, fixturePath) {
  if (!value || typeof value !== "object") {
    throw new Error(`Invalid test case #${index + 1} in ${fixturePath}: expected an object`);
  }
  const candidate = value;
  if (typeof candidate.id !== "string" || typeof candidate.name !== "string" || typeof candidate.prompt !== "string") {
    throw new Error(`Invalid test case #${index + 1} in ${fixturePath}: id, name, and prompt are required strings`);
  }
  return {
    id: candidate.id,
    name: candidate.name,
    prompt: candidate.prompt,
    expectedBehavior: typeof candidate.expectedBehavior === "string" ? candidate.expectedBehavior : void 0,
    rubric: candidate.rubric,
    timeoutMs: typeof candidate.timeoutMs === "number" ? candidate.timeoutMs : void 0
  };
}

export {
  DEFAULT_EVAL_FIXTURE_PATH,
  loadEvalTestCases,
  runEval
};
//# sourceMappingURL=chunk-CSFIBZNH.js.map