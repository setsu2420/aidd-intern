#!/usr/bin/env node
import {
  getNpmUpdateNotice
} from "./chunk-ZXBZNQLM.js";
import {
  PACKAGE_DESCRIPTION,
  PACKAGE_NAME,
  PACKAGE_VERSION
} from "./chunk-NHH2YBMB.js";
import {
  loadEnv
} from "./chunk-REGUV7MI.js";
import "./chunk-Y2QTMBPQ.js";
import {
  setLogLevel,
  source_default
} from "./chunk-4WEICLE4.js";

// src/cli.ts
import { Command } from "commander";
import { realpathSync } from "fs";
import { resolve } from "path";
import { pathToFileURL } from "url";
function createProgram() {
  const program = new Command();
  program.name(PACKAGE_NAME).description(PACKAGE_DESCRIPTION).version(PACKAGE_VERSION).option("-u, --url <url>", "Backend URL", "http://[::1]:7860").option("-t, --token <token>", "HF authentication token").option("-m, --model <model>", "LLM model ID").option("-v, --verbose", "Debug logging").option("--json", "JSON output for CI").showHelpAfterError(true).showSuggestionAfterError(true).hook("preAction", (command) => {
    const opts = command.opts();
    if (opts.json) {
      setLogLevel("silent");
      return;
    }
    if (opts.verbose) {
      setLogLevel("debug");
    }
  });
  program.command("smoke").description("Health check, session lifecycle, and model config").action(async () => {
    const env = resolveEnv(program.opts());
    await runCommand(env, async () => {
      const { runSmoke } = await import("./smoke-QZSZF6ZG.js");
      return runSmoke(env);
    });
  });
  program.command("update").description("Update the globally installed npm package or this source checkout").option("--check", "Check the globally installed npm package for available updates").option("--dry-run", "Print update commands without executing them").option("--checkout", "Update this source checkout with scripts/update-local.sh").option("--with-frontend", "When used with --checkout, also refresh frontend dependencies").action(async (opts) => {
    const env = resolveEnv(program.opts());
    await runCommand(env, async () => {
      const { runUpdate } = await import("./update-YRJOAWHF.js");
      return runUpdate({
        check: opts.check ?? false,
        dryRun: opts.dryRun ?? false,
        checkout: opts.checkout ?? false,
        withFrontend: opts.withFrontend ?? false
      });
    });
  });
  program.command("configure-llm").description("Print provider-specific LLM environment setup steps").argument("[provider]", "openrouter, openai, anthropic, siliconflow, or local").action(async (provider) => {
    const env = resolveEnv(program.opts());
    await runCommand(env, async () => {
      const { runConfigureLlm } = await import("./configure-llm-7X4MRG3Z.js");
      return runConfigureLlm(provider);
    });
  });
  program.command("integration").description("Chat flow, SSE streaming, and tool execution").action(async () => {
    const env = resolveEnv(program.opts());
    await runCommand(env, async () => {
      const { runIntegration } = await import("./integration-OHRFVCKL.js");
      return runIntegration(env);
    });
  });
  program.command("eval").description("Agent capability benchmarks and trace quality analysis").option("--judge", "Enable LLM-as-judge scoring").option("--fixtures <path>", "Path to the evaluation fixture bundle").option("--limit <number>", "Limit the number of evaluation cases", (value) => {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      throw new Error("--limit must be a positive integer");
    }
    return parsed;
  }).action(async (opts) => {
    const env = resolveEnv(program.opts());
    await runCommand(env, async () => {
      const { runEval } = await import("./eval-TBBNGN54.js");
      return runEval(env, {
        enableJudge: opts.judge ?? false,
        fixturesPath: opts.fixtures,
        limit: opts.limit
      });
    });
  });
  return program;
}
async function main() {
  const program = createProgram();
  try {
    await program.parseAsync(process.argv);
  } catch (error) {
    console.error(source_default.red(error instanceof Error ? error.message : String(error)));
    process.exitCode = 1;
  }
}
if (isMainModule()) {
  void main();
}
function resolveEnv(opts) {
  const fileEnv = loadEnv();
  return {
    backendUrl: opts.url ?? fileEnv.backendUrl,
    hfToken: opts.token ?? fileEnv.hfToken,
    testModel: opts.model ?? fileEnv.testModel,
    judgeModel: fileEnv.judgeModel,
    judgeApiKey: fileEnv.judgeApiKey,
    jsonOutput: opts.json ?? false
  };
}
async function runCommand(env, action) {
  if (shouldShowBanner(env)) {
    printBanner();
    await maybePrintUpdateNotice();
  }
  try {
    const ok = await action();
    process.exitCode = ok ? 0 : 1;
  } catch (error) {
    process.exitCode = 1;
    console.error(source_default.red(error instanceof Error ? error.message : String(error)));
  }
}
function shouldShowBanner(env) {
  return process.stdout.isTTY && !env.jsonOutput;
}
function printBanner() {
  console.log("");
  console.log(source_default.bold.cyan("  \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557"));
  console.log(source_default.bold.cyan("  \u2551") + source_default.bold.white(`   ${PACKAGE_NAME} `) + source_default.dim(`v${PACKAGE_VERSION}`) + source_default.bold.cyan("               \u2551"));
  console.log(source_default.bold.cyan("  \u2551") + source_default.dim("   Smoke \u2022 Integration \u2022 Eval     ") + source_default.bold.cyan("\u2551"));
  console.log(source_default.bold.cyan("  \u255A\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255D"));
  console.log("");
}
async function maybePrintUpdateNotice() {
  if (process.argv.includes("update")) {
    return;
  }
  try {
    const notice = await getNpmUpdateNotice();
    if (notice) {
      console.log(source_default.yellow(notice));
      console.log("");
    }
  } catch {
  }
}
function isMainModule() {
  if (!process.argv[1]) {
    return false;
  }
  return pathToFileURL(realpathSync(resolve(process.argv[1]))).href === import.meta.url;
}
export {
  createProgram
};
//# sourceMappingURL=cli.js.map