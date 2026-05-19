#!/usr/bin/env node
/**
 * aidd-intern — Node.js CLI for smoke tests, integration checks, and eval runs.
 */
import { Command } from 'commander';
import chalk from 'chalk';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { PACKAGE_DESCRIPTION, PACKAGE_NAME, PACKAGE_VERSION } from './manifest.js';
import { loadEnv, type CommandEnv } from './utils/env.js';
import { setLogLevel } from './utils/logger.js';

type CliOptions = {
  url?: string;
  token?: string;
  model?: string;
  verbose?: boolean;
  json?: boolean;
};

export function createProgram(): Command {
  const program = new Command();

  program
    .name(PACKAGE_NAME)
    .description(PACKAGE_DESCRIPTION)
    .version(PACKAGE_VERSION)
    .option('-u, --url <url>', 'Backend URL', 'http://[::1]:7860')
    .option('-t, --token <token>', 'HF authentication token')
    .option('-m, --model <model>', 'LLM model ID')
    .option('-v, --verbose', 'Debug logging')
    .option('--json', 'JSON output for CI')
    .showHelpAfterError(true)
    .showSuggestionAfterError(true)
    .hook('preAction', (command) => {
      const opts = command.opts<CliOptions>();
      if (opts.json) {
        setLogLevel('silent');
        return;
      }
      if (opts.verbose) {
        setLogLevel('debug');
      }
    });

  program
    .command('smoke')
    .description('Health check, session lifecycle, and model config')
    .action(async () => {
      const env = resolveEnv(program.opts<CliOptions>());
      await runCommand(env, async () => {
        const { runSmoke } = await import('./commands/smoke.js');
        return runSmoke(env);
      });
    });

  program
    .command('integration')
    .description('Chat flow, SSE streaming, and tool execution')
    .action(async () => {
      const env = resolveEnv(program.opts<CliOptions>());
      await runCommand(env, async () => {
        const { runIntegration } = await import('./commands/integration.js');
        return runIntegration(env);
      });
    });

  program
    .command('eval')
    .description('Agent capability benchmarks and trace quality analysis')
    .option('--judge', 'Enable LLM-as-judge scoring')
    .option('--fixtures <path>', 'Path to the evaluation fixture bundle')
    .option('--limit <number>', 'Limit the number of evaluation cases', (value: string) => {
      const parsed = Number.parseInt(value, 10);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new Error('--limit must be a positive integer');
      }
      return parsed;
    })
    .action(async (opts: { judge?: boolean; fixtures?: string; limit?: number }) => {
      const env = resolveEnv(program.opts<CliOptions>());
      await runCommand(env, async () => {
        const { runEval } = await import('./commands/eval.js');
        return runEval(env, {
          enableJudge: opts.judge ?? false,
          fixturesPath: opts.fixtures,
          limit: opts.limit,
        });
      });
    });

  return program;
}

async function main(): Promise<void> {
  const program = createProgram();
  try {
    await program.parseAsync(process.argv);
  } catch (error) {
    console.error(chalk.red(error instanceof Error ? error.message : String(error)));
    process.exitCode = 1;
  }
}

if (isMainModule()) {
  void main();
}

function resolveEnv(opts: CliOptions): CommandEnv {
  const fileEnv = loadEnv();
  return {
    backendUrl: opts.url ?? fileEnv.backendUrl,
    hfToken: opts.token ?? fileEnv.hfToken,
    testModel: opts.model ?? fileEnv.testModel,
    judgeModel: fileEnv.judgeModel,
    judgeApiKey: fileEnv.judgeApiKey,
    jsonOutput: opts.json ?? false,
  };
}

async function runCommand(env: CommandEnv, action: () => Promise<boolean>): Promise<void> {
  if (shouldShowBanner(env)) {
    printBanner();
  }

  try {
    const ok = await action();
    process.exitCode = ok ? 0 : 1;
  } catch (error) {
    process.exitCode = 1;
    console.error(chalk.red(error instanceof Error ? error.message : String(error)));
  }
}

function shouldShowBanner(env: CommandEnv): boolean {
  return process.stdout.isTTY && !env.jsonOutput;
}

function printBanner(): void {
  console.log('');
  console.log(chalk.bold.cyan('  ╔═══════════════════════════════════════╗'));
  console.log(chalk.bold.cyan('  ║') + chalk.bold.white(`   ${PACKAGE_NAME} `) + chalk.dim(`v${PACKAGE_VERSION}`) + chalk.bold.cyan('               ║'));
  console.log(chalk.bold.cyan('  ║') + chalk.dim('   Smoke • Integration • Eval     ') + chalk.bold.cyan('║'));
  console.log(chalk.bold.cyan('  ╚═══════════════════════════════════════╝'));
  console.log('');
}

function isMainModule(): boolean {
  if (!process.argv[1]) {
    return false;
  }

  return pathToFileURL(resolve(process.argv[1])).href === import.meta.url;
}
