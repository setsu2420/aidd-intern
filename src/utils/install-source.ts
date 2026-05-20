export const GITHUB_REPOSITORY_URL = 'https://github.com/setsu2420/aidd-intern.git';
export const GITHUB_INSTALL_REF = 'codex/aidd-prep-update-20260520';
export const NPM_GITHUB_INSTALL_SPEC = `https://github.com/setsu2420/aidd-intern/archive/refs/heads/${GITHUB_INSTALL_REF}.tar.gz`;

export function githubNpmInstallCommand(): string[] {
  return ['npm', 'install', '-g', NPM_GITHUB_INSTALL_SPEC];
}
