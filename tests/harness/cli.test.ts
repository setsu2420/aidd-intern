import { execFileSync } from 'node:child_process';
import { mkdtempSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
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

  it('runs when invoked through an npm-style .bin symlink', () => {
    reportStep('CLI symlink', 'build package before simulating npm bin invocation');
    execFileSync('npm', ['run', 'build'], { encoding: 'utf8' });

    const binDir = mkdtempSync(join(tmpdir(), 'aidd-intern-bin-'));
    const binPath = join(binDir, 'aidd-intern');
    symlinkSync(join(process.cwd(), 'dist', 'cli.js'), binPath);

    reportStep('CLI symlink', 'invoke symlinked CLI with --version');
    const stdout = execFileSync(binPath, ['--version'], { encoding: 'utf8' });
    reportStep('CLI symlink', 'observed stdout', stdout.trim());

    expect(stdout.trim()).toBe(PACKAGE_VERSION);
  });
});
