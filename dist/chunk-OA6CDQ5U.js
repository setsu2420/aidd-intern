// src/utils/logger.ts
import chalk from "chalk";
var PRIORITY = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 };
var minLevel = "info";
function setLogLevel(level) {
  minLevel = level;
}
var ts = () => (/* @__PURE__ */ new Date()).toISOString().slice(11, 23);
function createLogger(scope) {
  const write = (level, icon, style, message, ...args) => {
    if (PRIORITY[level] < PRIORITY[minLevel]) return;
    const sink = level === "error" ? console.error : level === "warn" ? console.warn : console.log;
    sink(
      `${chalk.dim(ts())} ${icon} ${style(`[${level.toUpperCase()}]`)} ${chalk.magenta(`[${scope}]`)} ${message}`,
      ...args
    );
  };
  return {
    debug: (message, ...args) => write("debug", "\u{1F50D}", chalk.gray, message, ...args),
    info: (message, ...args) => write("info", "\u{1F4CB}", chalk.cyan, message, ...args),
    warn: (message, ...args) => write("warn", "\u26A0\uFE0F", chalk.yellow, message, ...args),
    error: (message, ...args) => write("error", "\u274C", chalk.red, message, ...args),
    success: (message) => {
      if (PRIORITY.info >= PRIORITY[minLevel]) {
        console.log(`${chalk.dim(ts())} \u2705 ${chalk.green(message)}`);
      }
    },
    step: (step, description) => {
      if (PRIORITY.info >= PRIORITY[minLevel]) {
        console.log(`
${chalk.blue(`\u2501\u2501\u2501 Step ${step}: ${description} \u2501\u2501\u2501`)}`);
      }
    },
    ok: (message) => {
      if (PRIORITY.info >= PRIORITY[minLevel]) {
        console.log(`${chalk.dim(ts())} \u2705 ${chalk.green(message)}`);
      }
    },
    fail: (message) => {
      if (PRIORITY.error >= PRIORITY[minLevel]) {
        console.error(`${chalk.dim(ts())} \u{1F4A5} ${chalk.red.bold(message)}`);
      }
    }
  };
}

export {
  setLogLevel,
  createLogger
};
//# sourceMappingURL=chunk-OA6CDQ5U.js.map