type Level = 'debug' | 'info' | 'warn' | 'error' | 'silent';
declare function setLogLevel(level: Level): void;
declare function createLogger(scope: string): {
    debug: (message: string, ...args: unknown[]) => void;
    info: (message: string, ...args: unknown[]) => void;
    warn: (message: string, ...args: unknown[]) => void;
    error: (message: string, ...args: unknown[]) => void;
    success: (message: string) => void;
    step: (step: number, description: string) => void;
    ok: (message: string) => void;
    fail: (message: string) => void;
};
type Logger = ReturnType<typeof createLogger>;

type CheckStatus = 'pass' | 'warn' | 'fail';
interface CheckResult {
    name: string;
    status: CheckStatus;
    detail: string;
}
declare function printSuiteSummary(suite: string, results: CheckResult[], json: boolean): void;
declare function summarize(results: CheckResult[]): {
    passed: number;
    warned: number;
    failed: number;
};

export { type CheckResult as C, type Logger as L, type CheckStatus as a, summarize as b, createLogger as c, printSuiteSummary as p, setLogLevel as s };
