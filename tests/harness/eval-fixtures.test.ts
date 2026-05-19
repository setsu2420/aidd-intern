import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DEFAULT_EVAL_FIXTURE_PATH, loadEvalTestCases } from '../../src/commands/eval.js';
import { reportStep } from './test-output.js';

const fixturePath = resolve(process.cwd(), 'fixtures/prompts.json');

describe('evaluation fixtures', () => {
  it('loads the packaged fixture file without placeholder fallback cases', () => {
    reportStep('eval fixtures load', 'load shipped prompt fixture', fixturePath);
    const testCases = loadEvalTestCases(fixturePath);
    reportStep('eval fixtures load', 'observed fixture ids', testCases.map((testCase) => testCase.id));

    expect(DEFAULT_EVAL_FIXTURE_PATH.endsWith('fixtures/prompts.json')).toBe(true);
    expect(testCases.length).toBeGreaterThan(0);
    expect(testCases.every((testCase) => testCase.id && testCase.name && testCase.prompt)).toBe(true);
    expect(testCases.some((testCase) => testCase.id === 'basic-chat')).toBe(false);
  });

  it('applies --limit while preserving fixture order', () => {
    reportStep('eval fixtures limit', 'load full fixture and limited fixture');
    const allCases = loadEvalTestCases(fixturePath);
    const firstTwo = loadEvalTestCases(fixturePath, 2);
    reportStep('eval fixtures limit', 'observed limited ids', firstTwo.map((testCase) => testCase.id));

    expect(firstTwo).toHaveLength(2);
    expect(firstTwo.map((testCase) => testCase.id)).toEqual(allCases.slice(0, 2).map((testCase) => testCase.id));
  });

  it('uses unique IDs so evaluation output can be joined across runs', () => {
    reportStep('eval fixtures ids', 'validate uniqueness of fixture ids');
    const testCases = loadEvalTestCases(fixturePath);
    const ids = testCases.map((testCase) => testCase.id);
    reportStep('eval fixtures ids', 'observed id count', { total: ids.length, unique: new Set(ids).size });

    expect(new Set(ids).size).toBe(ids.length);
  });
});
