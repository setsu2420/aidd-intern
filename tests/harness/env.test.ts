import { afterEach, describe, expect, it } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
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
const originalCwd = process.cwd();

afterEach(() => {
  process.chdir(originalCwd);
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

  it('loads missing values from .env without overriding shell variables', () => {
    reportStep('loadEnv dotenv file', 'create an isolated .env file');
    for (const key of trackedKeys) {
      delete process.env[key];
    }
    process.env['AIDD_INTERN_BACKEND_URL'] = 'http://shell-value:7860/';

    const workspace = mkdtempSync(join(tmpdir(), 'aidd-env-'));
    try {
      writeFileSync(
        join(workspace, '.env'),
        [
          'AIDD_INTERN_BACKEND_URL=http://file-value:7860',
          'AIDD_INTERN_HF_TOKEN="hf-from-file"',
          'AIDD_INTERN_TEST_MODEL=openai/from-env-file',
          'export AIDD_INTERN_JUDGE_API_KEY=judge-from-file',
        ].join('\n'),
      );
      process.chdir(workspace);

      const env = loadEnv();
      reportStep('loadEnv dotenv file', 'observed resolved env', env);

      expect(env.backendUrl).toBe('http://shell-value:7860');
      expect(env.hfToken).toBe('hf-from-file');
      expect(env.testModel).toBe('openai/from-env-file');
      expect(env.judgeApiKey).toBe('judge-from-file');
    } finally {
      rmSync(workspace, { recursive: true, force: true });
    }
  });
});
