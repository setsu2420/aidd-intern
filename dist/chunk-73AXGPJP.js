import {
  PACKAGE_NAME,
  PACKAGE_VERSION
} from "./chunk-NHH2YBMB.js";
import {
  NPM_GITHUB_INSTALL_SPEC
} from "./chunk-JAK5VU7G.js";

// src/utils/version-check.ts
var DISABLE_UPDATE_CHECK_ENV = "AIDD_INTERN_DISABLE_UPDATE_CHECK";
var DEFAULT_TIMEOUT_MS = 2e3;
function compareVersions(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let index = 0; index < 3; index += 1) {
    if (a.parts[index] !== b.parts[index]) {
      return a.parts[index] < b.parts[index] ? -1 : 1;
    }
  }
  if (a.prerelease === b.prerelease) {
    return 0;
  }
  if (!a.prerelease) {
    return 1;
  }
  if (!b.prerelease) {
    return -1;
  }
  return a.prerelease < b.prerelease ? -1 : a.prerelease > b.prerelease ? 1 : 0;
}
async function fetchNpmLatestVersion(packageName = PACKAGE_NAME, options = {}) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  if (!fetchImpl) {
    throw new Error("fetch is not available in this Node.js runtime");
  }
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(`https://registry.npmjs.org/${encodeURIComponent(packageName)}/latest`, {
      headers: { accept: "application/json" },
      signal: controller.signal
    });
    if (!response.ok) {
      throw new Error(`npm registry returned HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (typeof payload.version !== "string" || payload.version.trim() === "") {
      throw new Error("npm registry response did not include a version");
    }
    return payload.version.trim();
  } finally {
    clearTimeout(timeout);
  }
}
async function getNpmUpdateNotice(options = {}) {
  if (isUpdateCheckDisabled()) {
    return void 0;
  }
  const packageName = options.packageName ?? PACKAGE_NAME;
  const currentVersion = options.currentVersion ?? PACKAGE_VERSION;
  const latestVersion = await fetchNpmLatestVersion(packageName, options);
  if (compareVersions(currentVersion, latestVersion) >= 0) {
    return void 0;
  }
  return [
    `${packageName} update available: local v${currentVersion} is behind npm v${latestVersion}.`,
    `Run \`aidd-intern update\` or \`npm install -g ${NPM_GITHUB_INSTALL_SPEC}\` to update.`
  ].join("\n");
}
function isUpdateCheckDisabled() {
  return ["1", "true", "yes", "on"].includes((process.env[DISABLE_UPDATE_CHECK_ENV] ?? "").trim().toLowerCase());
}
function parseVersion(version) {
  const normalized = version.trim().replace(/^v/i, "");
  const withoutBuild = normalized.split("+", 1)[0] ?? "";
  const [core, prerelease = ""] = withoutBuild.split("-", 2);
  const rawParts = core.split(".").map((part) => Number.parseInt(part, 10));
  const partAt = (index) => {
    const value = rawParts[index];
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  };
  const parts = [partAt(0), partAt(1), partAt(2)];
  return { parts, prerelease };
}

export {
  compareVersions,
  fetchNpmLatestVersion,
  getNpmUpdateNotice
};
//# sourceMappingURL=chunk-73AXGPJP.js.map