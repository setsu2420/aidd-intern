import chalk from 'chalk';

export type Level = 'debug' | 'info' | 'warn' | 'error' | 'silent';

const PRIORITY: Record<Level, number> = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 };
let minLevel: Level = 'info';

export function setLogLevel(level: Level): void {
  minLevel = level;
}

const ts = () => new Date().toISOString().slice(11, 23);

export function createLogger(scope: string) {
  const write = (level: Exclude<Level, 'silent'>, icon: string, style: (s: string) => string, message: string, ...args: unknown[]) => {
    if (PRIORITY[level] < PRIORITY[minLevel]) return;
    const sink = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
    sink(
      `${chalk.dim(ts())} ${icon} ${style(`[${level.toUpperCase()}]`)} ${chalk.magenta(`[${scope}]`)} ${message}`,
      ...args,
    );
  };
  return {
    debug: (message: string, ...args: unknown[]) => write('debug', '🔍', chalk.gray, message, ...args),
    info: (message: string, ...args: unknown[]) => write('info', '📋', chalk.cyan, message, ...args),
    warn: (message: string, ...args: unknown[]) => write('warn', '⚠️', chalk.yellow, message, ...args),
    error: (message: string, ...args: unknown[]) => write('error', '❌', chalk.red, message, ...args),
    success: (message: string) => {
      if (PRIORITY.info >= PRIORITY[minLevel]) {
        console.log(`${chalk.dim(ts())} ✅ ${chalk.green(message)}`);
      }
    },
    step: (step: number, description: string) => {
      if (PRIORITY.info >= PRIORITY[minLevel]) {
        console.log(`\n${chalk.blue(`━━━ Step ${step}: ${description} ━━━`)}`);
      }
    },
    ok: (message: string) => {
      if (PRIORITY.info >= PRIORITY[minLevel]) {
        console.log(`${chalk.dim(ts())} ✅ ${chalk.green(message)}`);
      }
    },
    fail: (message: string) => {
      if (PRIORITY.error >= PRIORITY[minLevel]) {
        console.error(`${chalk.dim(ts())} 💥 ${chalk.red.bold(message)}`);
      }
    },
  };
}
export type Logger = ReturnType<typeof createLogger>;
