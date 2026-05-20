import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { PACKAGE_NAME, PACKAGE_VERSION } from '../manifest.js';
import { compareVersions, fetchNpmLatestVersion } from '../utils/version-check.js';
import { githubNpmInstallCommand } from '../utils/install-source.js';

export type UpdateOptions = {
  dryRun?: boolean;
  check?: boolean;
  checkout?: boolean;
  withFrontend?: boolean;
};

type Step = {
  title: string;
  command: string[];
};

export async function runUpdate(options: UpdateOptions = {}): Promise<boolean> {
  if (options.check && !options.checkout) {
    return runNpmVersionCheck();
  }

  const steps = options.checkout ? checkoutSteps(options) : npmGlobalSteps(options);

  for (const [index, step] of steps.entries()) {
    printStep(index + 1, step);
    if (options.dryRun) {
      continue;
    }
    const result = runStep(step, { allowOutdatedExit: options.check === true });
    if (!result) {
      return false;
    }
  }

  if (options.dryRun) {
    console.log('Dry run only. No update commands were executed.');
  }
  return true;
}

async function runNpmVersionCheck(): Promise<boolean> {
  console.log(`Current ${PACKAGE_NAME} version: v${PACKAGE_VERSION}`);
  try {
    const latest = await fetchNpmLatestVersion(PACKAGE_NAME);
    console.log(`Latest published npm version: v${latest}`);
    if (compareVersions(PACKAGE_VERSION, latest) < 0) {
      console.log(`Update available. Run: aidd-intern update`);
    } else {
      console.log('Already up to date.');
    }
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes('HTTP 404') || message.includes('Not Found')) {
      console.log(`Package ${PACKAGE_NAME} is not published in the npm registry yet.`);
      console.log(`Install from GitHub instead: ${githubNpmInstallCommand().map(shellToken).join(' ')}`);
      console.log('For source checkouts, run: scripts/update-local.sh');
      return true;
    }
    console.error(`Could not check the npm registry: ${message}`);
    console.error(`Install from GitHub instead: ${githubNpmInstallCommand().map(shellToken).join(' ')}`);
    console.error('For source checkouts, run: scripts/update-local.sh');
    return false;
  }
}

function npmGlobalSteps(options: UpdateOptions): Step[] {
  if (options.check) {
    return [
      {
        title: 'Checking the globally installed npm package',
        command: ['npm', 'outdated', '-g', '--depth=0', PACKAGE_NAME],
      },
    ];
  }

  return [
    {
      title: 'Installing the npm package from GitHub',
      command: githubNpmInstallCommand(),
    },
    {
      title: 'Verifying the globally installed npm package',
      command: ['npm', 'list', '-g', PACKAGE_NAME, '--depth=0'],
    },
  ];
}

function checkoutSteps(options: UpdateOptions): Step[] {
  const scriptPath = join(process.cwd(), 'scripts', 'update-local.sh');
  const command = ['bash', 'scripts/update-local.sh'];
  if (options.withFrontend) {
    command.push('--with-frontend');
  }

  const steps: Step[] = [
    {
      title: 'Updating this source checkout',
      command,
    },
  ];

  if (!existsSync(scriptPath)) {
    steps.unshift({
      title: 'Checking for source checkout update helper',
      command: ['test', '-x', 'scripts/update-local.sh'],
    });
  }

  return steps;
}

function printStep(index: number, step: Step): void {
  console.log(`STEP ${index}: ${step.title}`);
  console.log(`$ ${step.command.map(shellToken).join(' ')}`);
}

function shellToken(value: string): string {
  if (/^[A-Za-z0-9_./:@=+-]+$/.test(value)) {
    return value;
  }
  return JSON.stringify(value);
}

function runStep(step: Step, options: { allowOutdatedExit?: boolean } = {}): boolean {
  const [command, ...args] = step.command;
  const result = spawnSync(command, args, {
    cwd: process.cwd(),
    env: process.env,
    stdio: 'inherit',
    shell: false,
  });

  if (result.error) {
    console.error(`Failed to run ${command}: ${result.error.message}`);
    return false;
  }

  if (options.allowOutdatedExit && result.status === 1) {
    return true;
  }

  return result.status === 0;
}
