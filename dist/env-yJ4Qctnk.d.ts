declare const DEFAULT_BACKEND_URL = "http://[::1]:7860";
declare const DEFAULT_JUDGE_MODEL = "openai/gpt-4.1-mini";
interface RuntimeEnv {
    backendUrl: string;
    hfToken: string | undefined;
    testModel: string | undefined;
    judgeModel: string;
    judgeApiKey: string | undefined;
}
interface CommandEnv extends RuntimeEnv {
    jsonOutput: boolean;
}
declare function loadEnv(): RuntimeEnv;

export { type CommandEnv as C, DEFAULT_BACKEND_URL as D, type RuntimeEnv as R, DEFAULT_JUDGE_MODEL as a, loadEnv as l };
