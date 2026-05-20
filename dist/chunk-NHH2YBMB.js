// src/manifest.ts
import { readFileSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
var packageManifestPath = resolve(dirname(fileURLToPath(import.meta.url)), "../package.json");
var packageManifest = JSON.parse(readFileSync(packageManifestPath, "utf-8"));
var PACKAGE_NAME = packageManifest.name;
var PACKAGE_VERSION = packageManifest.version;
var PACKAGE_DESCRIPTION = packageManifest.description ?? "Node.js CLI for AIDD-Intern smoke tests, integration checks, and evaluation runs";

export {
  PACKAGE_NAME,
  PACKAGE_VERSION,
  PACKAGE_DESCRIPTION
};
//# sourceMappingURL=chunk-NHH2YBMB.js.map