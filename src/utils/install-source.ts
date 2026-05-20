export const GITHUB_REPOSITORY_URL = 'https://github.com/setsu2420/aidd-intern.git';
export const GITHUB_INSTALL_REF = 'codex/aidd-prep-update-20260520';
export const NPM_GITHUB_INSTALL_SPEC = `git+${GITHUB_REPOSITORY_URL}#${GITHUB_INSTALL_REF}`;

export function githubNpmInstallCommand(): string[] {
  return ['npm', 'install', '-g', NPM_GITHUB_INSTALL_SPEC];
}
