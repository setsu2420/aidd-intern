// src/utils/env.ts
import { config as loadDotenv } from "dotenv";
var DEFAULT_BACKEND_URL = "http://[::1]:7860";
var DEFAULT_JUDGE_MODEL = "openai/gpt-4.1-mini";
var dotenvLoaded = false;
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
  if (dotenvLoaded) {
    return;
  }
  loadDotenv();
  dotenvLoaded = true;
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
//# sourceMappingURL=chunk-V5UBAFI5.js.map