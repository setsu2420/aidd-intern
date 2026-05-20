// src/utils/env.ts
import { existsSync, readFileSync } from "fs";
import { resolve } from "path";
var DEFAULT_BACKEND_URL = "http://[::1]:7860";
var DEFAULT_JUDGE_MODEL = "openai/gpt-4.1-mini";
var loadedEnvFiles = /* @__PURE__ */ new Set();
function loadEnv() {
  ensureDotenvLoaded();
  return {
    backendUrl: normalizeUrl(readEnv("AIDD_INTERN_BACKEND_URL", "HARNESS_BACKEND_URL") ?? DEFAULT_BACKEND_URL),
    hfToken: readEnv("AIDD_INTERN_HF_TOKEN", "HARNESS_HF_TOKEN", "HF_TOKEN"),
    testModel: readEnv("AIDD_INTERN_TEST_MODEL", "HARNESS_TEST_MODEL"),
    judgeModel: readEnv("AIDD_INTERN_JUDGE_MODEL", "HARNESS_JUDGE_MODEL") ?? DEFAULT_JUDGE_MODEL,
    judgeApiKey: readEnv("AIDD_INTERN_JUDGE_API_KEY", "HARNESS_JUDGE_API_KEY", "OPENAI_API_KEY")
  };
}
function ensureDotenvLoaded() {
  const envPath = resolve(process.cwd(), ".env");
  if (loadedEnvFiles.has(envPath)) {
    return;
  }
  loadEnvFile(envPath);
  loadedEnvFiles.add(envPath);
}
function loadEnvFile(path) {
  if (!existsSync(path)) {
    return;
  }
  const content = readFileSync(path, "utf8");
  for (const line of content.split(/\r?\n/)) {
    const parsed = parseEnvLine(line);
    if (!parsed || process.env[parsed.key] !== void 0) {
      continue;
    }
    process.env[parsed.key] = parsed.value;
  }
}
function parseEnvLine(line) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) {
    return void 0;
  }
  const normalized = trimmed.startsWith("export ") ? trimmed.slice("export ".length).trimStart() : trimmed;
  const separatorIndex = normalized.indexOf("=");
  if (separatorIndex <= 0) {
    return void 0;
  }
  const key = normalized.slice(0, separatorIndex).trim();
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
    return void 0;
  }
  const rawValue = normalized.slice(separatorIndex + 1).trim();
  return { key, value: unquoteEnvValue(rawValue) };
}
function unquoteEnvValue(value) {
  if (value.length < 2) {
    return value;
  }
  const quote = value[0];
  const last = value[value.length - 1];
  if (quote !== '"' && quote !== "'" && quote !== "`" || last !== quote) {
    return value;
  }
  const inner = value.slice(1, -1);
  if (quote !== '"') {
    return inner;
  }
  return inner.replace(/\\n/g, "\n").replace(/\\r/g, "\r").replace(/\\t/g, "	").replace(/\\"/g, '"').replace(/\\\\/g, "\\");
}
function readEnv(...keys) {
  for (const key of keys) {
    const value = process.env[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return void 0;
}
function normalizeUrl(value) {
  return value.replace(/\/+$/, "");
}

export {
  DEFAULT_BACKEND_URL,
  DEFAULT_JUDGE_MODEL,
  loadEnv
};
//# sourceMappingURL=chunk-REGUV7MI.js.map