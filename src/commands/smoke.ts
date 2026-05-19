import { AgentClient } from '../client/index.js';
import type { CommandEnv } from '../utils/env.js';
import { createLogger } from '../utils/logger.js';
import { printSuiteSummary, type CheckResult } from '../utils/reporting.js';

const log = createLogger('Smoke');

export async function runSmoke(env: CommandEnv): Promise<boolean> {
  const client = new AgentClient({
    baseUrl: env.backendUrl,
    hfToken: env.hfToken,
  });
  const results: CheckResult[] = [];

  await recordCheck(
    results,
    1,
    'API Root',
    async () => {
      const root = await client.apiRoot();
      return `${root.name} v${root.version}`;
    },
    () => 'API accessible',
  );

  await recordCheck(
    results,
    2,
    'Health Check',
    async () => {
      const health = await client.healthCheck();
      if (health.status !== 'ok') {
        throw new Error(health.status);
      }
      return `${health.active_sessions}/${health.max_sessions}`;
    },
    () => 'Healthy',
  );

  await recordCheck(
    results,
    3,
    'LLM Health',
    async () => {
      const health = await client.llmHealthCheck();
      if (health.status !== 'ok') {
        throw new Error(health.error ?? health.status);
      }
      return health.model;
    },
    () => 'LLM available',
    'warn',
  );

  await recordCheck(
    results,
    4,
    'Model Config',
    async () => {
      const config = await client.getModelConfig();
      if (config.available.length === 0) {
        throw new Error('No models available');
      }
      return `${config.available.length} models`;
    },
    (detail) => detail,
  );

  await recordCheck(
    results,
    5,
    'Session Lifecycle',
    async () => {
      const session = await client.createSession();
      log.info(`Created: ${session.session_id}`);

      const active = await client.getSession(session.session_id);
      log.info(`Active: ${active.is_active}`);

      await client.deleteSession(session.session_id);
      log.info('Deleted');

      return 'CRUD OK';
    },
    () => 'Session lifecycle works',
  );

  printSuiteSummary('SMOKE', results, env.jsonOutput);

  return results.every((result) => result.status !== 'fail');
}

async function recordCheck(
  results: CheckResult[],
  step: number,
  title: string,
  action: () => Promise<string>,
  onSuccess: (detail: string) => string,
  failureLevel: 'fail' | 'warn' = 'fail',
): Promise<void> {
  log.step(step, title);
  try {
    const detail = await action();
    results.push({ name: title, status: 'pass', detail });
    log.ok(onSuccess(detail));
  } catch (error) {
    const detail = String(error);
    results.push({ name: title, status: failureLevel === 'warn' ? 'warn' : 'fail', detail });
    if (failureLevel === 'warn') {
      log.warn(detail);
    } else {
      log.fail(detail);
    }
  }
}
