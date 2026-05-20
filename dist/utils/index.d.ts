export { C as CommandEnv, D as DEFAULT_BACKEND_URL, a as DEFAULT_JUDGE_MODEL, R as RuntimeEnv, l as loadEnv } from '../env-yJ4Qctnk.js';
export { C as CheckResult, a as CheckStatus, L as Logger, c as createLogger, p as printSuiteSummary, s as setLogLevel, b as summarize } from '../reporting-0g08YTS2.js';

declare const GITHUB_REPOSITORY_URL = "https://github.com/setsu2420/aidd-intern.git";
declare const GITHUB_INSTALL_REF = "codex/aidd-prep-update-20260520";
declare const NPM_GITHUB_INSTALL_SPEC = "https://github.com/setsu2420/aidd-intern/archive/refs/heads/codex/aidd-prep-update-20260520.tar.gz";
declare function githubNpmInstallCommand(): string[];

export { GITHUB_INSTALL_REF, GITHUB_REPOSITORY_URL, NPM_GITHUB_INSTALL_SPEC, githubNpmInstallCommand };
