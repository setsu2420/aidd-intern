import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface PackageManifest {
  name: string;
  version: string;
  description?: string;
}

const packageManifestPath = resolve(dirname(fileURLToPath(import.meta.url)), '../package.json');
const packageManifest = JSON.parse(readFileSync(packageManifestPath, 'utf-8')) as PackageManifest;

export const PACKAGE_NAME = packageManifest.name;
export const PACKAGE_VERSION = packageManifest.version;
export const PACKAGE_DESCRIPTION =
  packageManifest.description ?? 'Node.js CLI for AIDD-Intern smoke tests, integration checks, and evaluation runs';
