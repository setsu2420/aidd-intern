import { afterEach, describe, expect, it } from 'vitest';
import { DEFAULT_BACKEND_URL, DEFAULT_JUDGE_MODEL, loadEnv } from '../../src/utils/env.js';
import { reportStep } from './test-output.js';

const trackedKeys = [
  'AIDD_INTERN_BACKEND_URL',
  'HARNESS_BACKEND_URL',
  'AIDD_INTERN_HF_TOKEN',
  'HARNESS_HF_TOKEN',
  'HF_TOKEN',
  'AIDD_INTERN_TEST_MODEL',
  'HARNESS_TEST_MODEL',
  'AIDD_INTERN_JUDGE_MODEL',
  'HARNESS_JUDGE_MODEL',
  'AIDD_INTERN_JUDGE_API_KEY',
  'HARNESS_JUDGE_API_KEY',
  'OPENAI_API_KEY',
] as const;

const originalEnv = new Map<string, string | undefined>(
  trackedKeys.map((key) => [key, process.env[key]]),
);

afterEach(() => {
  for (const key of trackedKeys) {
    const original = originalEnv.get(key);
    if (original === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = original;
    }
  }
});

describe('loadEnv', () => {
  it('prints explicit inputs through AIDD_INTERN variables first', () => {
    reportStep('loadEnv precedence', 'set both AIDD_INTERN and HARNESS values');
    process.env['AIDD_INTERN_BACKEND_URL'] = 'http://localhost:7860/';
    process.env['HARNESS_BACKEND_URL'] = 'http://should-not-win:7860';
    process.env['AIDD_INTERN_HF_TOKEN'] = 'hf-aidd-token';
    process.env['AIDD_INTERN_TEST_MODEL'] = 'openai/test-model';
    process.env['AIDD_INTERN_JUDGE_MODEL'] = 'openai/judge-model';
    process.env['AIDD_INTERN_JUDGE_API_KEY'] = 'judge-key';

    const env = loadEnv();
    reportStep('loadEnv precedence', 'observed resolved env', env);

    expect(env).toEqual({
      backendUrl: 'http://localhost:7860',
      hfToken: 'hf-aidd-token',
      testModel: 'openai/test-model',
      judgeModel: 'openai/judge-model',
      judgeApiKey: 'judge-key',
    });
  });

  it('falls back to legacy HARNESS variables and documented defaults', () => {
    reportStep('loadEnv fallback', 'clear tracked vars and set only a legacy token');
    for (const key of trackedKeys) {
      delete process.env[key];
    }
    process.env['HARNESS_HF_TOKEN'] = 'hf-legacy-token';

    const env = loadEnv();
    reportStep('loadEnv fallback', 'observed resolved env', env);

    expect(env.backendUrl).toBe(DEFAULT_BACKEND_URL);
    expect(env.hfToken).toBe('hf-legacy-token');
    expect(env.judgeModel).toBe(DEFAULT_JUDGE_MODEL);
  });
});
