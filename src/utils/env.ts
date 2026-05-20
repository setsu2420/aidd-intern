import { config as loadDotenv } from 'dotenv';

export const DEFAULT_BACKEND_URL = 'http://[::1]:7860';
export const DEFAULT_JUDGE_MODEL = 'openai/gpt-4.1-mini';

let dotenvLoaded = false;

export interface RuntimeEnv {
  backendUrl: string;
  hfToken: string | undefined;
  testModel: string | undefined;
  judgeModel: string;
  judgeApiKey: string | undefined;
}

export interface CommandEnv extends RuntimeEnv {
  jsonOutput: boolean;
}

export function loadEnv(): RuntimeEnv {
  ensureDotenvLoaded();

  return {
    backendUrl: normalizeUrl(readEnv('AIDD_INTERN_BACKEND_URL', 'HARNESS_BACKEND_URL') ?? DEFAULT_BACKEND_URL),
    hfToken: readEnv('AIDD_INTERN_HF_TOKEN', 'HARNESS_HF_TOKEN', 'HF_TOKEN'),
    testModel: readEnv('AIDD_INTERN_TEST_MODEL', 'HARNESS_TEST_MODEL'),
    judgeModel: readEnv('AIDD_INTERN_JUDGE_MODEL', 'HARNESS_JUDGE_MODEL') ?? DEFAULT_JUDGE_MODEL,
    judgeApiKey: readEnv('AIDD_INTERN_JUDGE_API_KEY', 'HARNESS_JUDGE_API_KEY', 'OPENAI_API_KEY'),
  };
}

function ensureDotenvLoaded(): void {
  if (dotenvLoaded) {
    return;
  }

  loadDotenv();
  dotenvLoaded = true;
}

function readEnv(...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = process.env[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  return undefined;
}

function normalizeUrl(value: string): string {
  return value.replace(/\/+$/, '');
}
