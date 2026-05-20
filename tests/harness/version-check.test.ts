import { describe, expect, it } from 'vitest';
import {
  DISABLE_UPDATE_CHECK_ENV,
  compareVersions,
  getNpmUpdateNotice,
} from '../../src/utils/version-check.js';
import { NPM_GITHUB_INSTALL_SPEC } from '../../src/utils/install-source.js';
import { reportStep } from './test-output.js';

describe('version checks', () => {
  it('compares semantic versions without a semver dependency', () => {
    reportStep('version compare', 'compare newer, equal, and prerelease versions');

    expect(compareVersions('1.0.0', '1.0.1')).toBeLessThan(0);
    expect(compareVersions('v1.2.3', '1.2.3')).toBe(0);
    expect(compareVersions('1.2.3', '1.2.3-beta.1')).toBeGreaterThan(0);
  });

  it('builds an update notice when npm has a newer version', async () => {
    reportStep('npm update notice', 'simulate npm latest metadata');
    const fetchImpl = async () =>
      ({
        ok: true,
        status: 200,
        json: async () => ({ version: '1.2.0' }),
      }) as Response;

    const notice = await getNpmUpdateNotice({
      packageName: 'aidd-intern',
      currentVersion: '1.0.0',
      fetchImpl,
    });

    reportStep('npm update notice', 'observed notice', notice);
    expect(notice).toContain('local v1.0.0 is behind npm v1.2.0');
    expect(notice).toContain('aidd-intern update');
    expect(notice).toContain(`npm install -g ${NPM_GITHUB_INSTALL_SPEC}`);
    expect(notice).not.toContain('aidd-intern@latest');
  });

  it('honors the disable-update-check environment variable', async () => {
    reportStep('disabled update notice', 'suppress version notice with env var');
    const previous = process.env[DISABLE_UPDATE_CHECK_ENV];
    process.env[DISABLE_UPDATE_CHECK_ENV] = '1';
    try {
      const notice = await getNpmUpdateNotice({
        packageName: 'aidd-intern',
        currentVersion: '1.0.0',
        fetchImpl: async () =>
          ({
            ok: true,
            status: 200,
            json: async () => ({ version: '2.0.0' }),
          }) as Response,
      });

      reportStep('disabled update notice', 'observed notice', notice);
      expect(notice).toBeUndefined();
    } finally {
      if (previous === undefined) {
        delete process.env[DISABLE_UPDATE_CHECK_ENV];
      } else {
        process.env[DISABLE_UPDATE_CHECK_ENV] = previous;
      }
    }
  });
});
