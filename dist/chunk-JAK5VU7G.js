// src/utils/install-source.ts
var GITHUB_REPOSITORY_URL = "https://github.com/setsu2420/aidd-intern.git";
var GITHUB_INSTALL_REF = "codex/aidd-prep-update-20260520";
var NPM_GITHUB_INSTALL_SPEC = `git+${GITHUB_REPOSITORY_URL}#${GITHUB_INSTALL_REF}`;
function githubNpmInstallCommand() {
  return ["npm", "install", "-g", NPM_GITHUB_INSTALL_SPEC];
}

export {
  GITHUB_REPOSITORY_URL,
  GITHUB_INSTALL_REF,
  NPM_GITHUB_INSTALL_SPEC,
  githubNpmInstallCommand
};
//# sourceMappingURL=chunk-JAK5VU7G.js.map