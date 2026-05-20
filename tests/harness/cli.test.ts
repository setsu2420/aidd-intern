import { describe, expect, it } from 'vitest';
import { createProgram } from '../../src/cli.js';
import { PACKAGE_NAME, PACKAGE_VERSION } from '../../src/manifest.js';
import { reportStep } from './test-output.js';

describe('CLI program', () => {
  it('exposes the published package name and manifest version', () => {
    reportStep('CLI manifest', 'create Commander program from source');
    const program = createProgram();
    reportStep('CLI manifest', 'observed name and version', { name: program.name(), version: program.version() });

    expect(program.name()).toBe(PACKAGE_NAME);
    expect(program.version()).toBe(PACKAGE_VERSION);
  });

  it('registers the public command surface expected by npm users', () => {
    reportStep('CLI commands', 'inspect public subcommands and eval flags');
    const program = createProgram();
    const commands = program.commands.map((command) => command.name());
    reportStep('CLI commands', 'observed commands', commands);

    expect(commands).toEqual(['smoke', 'update', 'configure-llm', 'integration', 'eval']);
    expect(program.commands.find((command) => command.name() === 'update')?.options.map((option) => option.long)).toEqual([
      '--check',
      '--dry-run',
      '--checkout',
      '--with-frontend',
    ]);
    expect(program.commands.find((command) => command.name() === 'eval')?.options.map((option) => option.long)).toEqual([
      '--judge',
      '--fixtures',
      '--limit',
    ]);
  });
});
