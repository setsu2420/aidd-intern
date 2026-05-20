import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';
import { NPM_GITHUB_INSTALL_SPEC } from '../../src/utils/install-source.js';
import { reportStep } from './test-output.js';

describe('npm update helpers', () => {
  it('prints the global npm update command without executing it', () => {
    reportStep('npm update dry run', 'run real CLI dry-run command');
    const stdout = execFileSync('node', ['src/cli.ts', '--json', 'update', '--dry-run'], {
      encoding: 'utf8',
    });
    reportStep('npm update dry run', 'observed stdout', stdout);

    expect(stdout).toContain('STEP 1: Installing the npm package from GitHub');
    expect(stdout).toContain(`$ npm install -g "${NPM_GITHUB_INSTALL_SPEC}"`);
    expect(stdout).not.toContain('aidd-intern@latest');
    expect(stdout).toContain('Dry run only. No update commands were executed.');
  });

  it('prints the source checkout update command without executing it', () => {
    reportStep('checkout update dry run', 'run real CLI checkout dry-run command');
    const stdout = execFileSync(
      'node',
      ['src/cli.ts', '--json', 'update', '--checkout', '--with-frontend', '--dry-run'],
      { encoding: 'utf8' },
    );
    reportStep('checkout update dry run', 'observed stdout', stdout);

    expect(stdout).toContain('$ bash scripts/update-local.sh --with-frontend');
  });
});

describe('LLM configuration guide', () => {
  it('prints provider-specific OpenRouter configuration steps', () => {
    reportStep('configure llm openrouter', 'run real CLI provider guide command');
    const stdout = execFileSync('node', ['src/cli.ts', '--json', 'configure-llm', 'openrouter'], {
      encoding: 'utf8',
    });
    reportStep('configure llm openrouter', 'observed stdout', stdout);

    expect(stdout).toContain('STEP 1: Configure OpenRouter');
    expect(stdout).toContain('OPENROUTER_API_KEY=...');
    expect(stdout).toContain('AIDD_INTERN_DEFAULT_MODEL_ID=openrouter/openai/gpt-5.2');
  });
});
