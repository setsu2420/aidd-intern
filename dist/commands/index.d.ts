import { a as EvalTestCase } from '../index-DvcZdzUD.js';
import { C as CommandEnv } from '../env-yJ4Qctnk.js';
import '../client/index.js';
import '../types-CDvLvuOf.js';
import 'zod';
import '../analyzer-DWhucvPg.js';

declare const DEFAULT_EVAL_FIXTURE_PATH: string;
type Env = CommandEnv;
interface EvalOptions {
    enableJudge: boolean;
    fixturesPath?: string;
    limit?: number;
}
declare function loadEvalTestCases(fixturePath?: string, limit?: number): EvalTestCase[];
declare function runEval(env: Env, opts: EvalOptions): Promise<boolean>;

declare function runIntegration(env: CommandEnv): Promise<boolean>;

declare function runSmoke(env: CommandEnv): Promise<boolean>;

export { CommandEnv, DEFAULT_EVAL_FIXTURE_PATH, type Env as EvalEnv, type EvalOptions, loadEvalTestCases, runEval, runIntegration, runSmoke };
