import {
  compareVersions,
  fetchNpmLatestVersion
} from "./chunk-ZXBZNQLM.js";
import {
  PACKAGE_NAME,
  PACKAGE_VERSION
} from "./chunk-NHH2YBMB.js";
import {
  githubNpmInstallCommand
} from "./chunk-Y2QTMBPQ.js";
import "./chunk-7D4SUZUM.js";

// src/commands/update.ts
import { existsSync } from "fs";
import { join } from "path";
import { spawnSync } from "child_process";
async function runUpdate(options = {}) {
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
    console.log("Dry run only. No update commands were executed.");
  }
  return true;
}
async function runNpmVersionCheck() {
  console.log(`Current ${PACKAGE_NAME} version: v${PACKAGE_VERSION}`);
  try {
    const latest = await fetchNpmLatestVersion(PACKAGE_NAME);
    console.log(`Latest published npm version: v${latest}`);
    if (compareVersions(PACKAGE_VERSION, latest) < 0) {
      console.log(`Update available. Run: aidd-intern update`);
    } else {
      console.log("Already up to date.");
    }
    return true;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("HTTP 404") || message.includes("Not Found")) {
      console.log(`Package ${PACKAGE_NAME} is not published in the npm registry yet.`);
      console.log(`Install from GitHub instead: ${githubNpmInstallCommand().map(shellToken).join(" ")}`);
      console.log("For source checkouts, run: scripts/update-local.sh");
      return true;
    }
    console.error(`Could not check the npm registry: ${message}`);
    console.error(`Install from GitHub instead: ${githubNpmInstallCommand().map(shellToken).join(" ")}`);
    console.error("For source checkouts, run: scripts/update-local.sh");
    return false;
  }
}
function npmGlobalSteps(options) {
  if (options.check) {
    return [
      {
        title: "Checking the globally installed npm package",
        command: ["npm", "outdated", "-g", "--depth=0", PACKAGE_NAME]
      }
    ];
  }
  return [
    {
      title: "Installing the npm package from GitHub tarball",
      command: githubNpmInstallCommand()
    },
    {
      title: "Verifying the globally installed npm package",
      command: ["npm", "list", "-g", PACKAGE_NAME, "--depth=0"]
    }
  ];
}
function checkoutSteps(options) {
  const scriptPath = join(process.cwd(), "scripts", "update-local.sh");
  const command = ["bash", "scripts/update-local.sh"];
  if (options.withFrontend) {
    command.push("--with-frontend");
  }
  const steps = [
    {
      title: "Updating this source checkout",
      command
    }
  ];
  if (!existsSync(scriptPath)) {
    steps.unshift({
      title: "Checking for source checkout update helper",
      command: ["test", "-x", "scripts/update-local.sh"]
    });
  }
  return steps;
}
function printStep(index, step) {
  console.log(`STEP ${index}: ${step.title}`);
  console.log(`$ ${step.command.map(shellToken).join(" ")}`);
}
function shellToken(value) {
  if (/^[A-Za-z0-9_./:@=+-]+$/.test(value)) {
    return value;
  }
  return JSON.stringify(value);
}
function runStep(step, options = {}) {
  const [command, ...args] = step.command;
  const result = spawnSync(command, args, {
    cwd: process.cwd(),
    env: process.env,
    stdio: "inherit",
    shell: false
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
export {
  runUpdate
};
//# sourceMappingURL=update-SQBH3BLJ.js.map