import { AgentClient } from '../client/index.js';
import { TraceCollector } from '../trace/collector.js';
import { analyzeTrace } from '../trace/analyzer.js';
import type { CommandEnv } from '../utils/env.js';
import { createLogger } from '../utils/logger.js';
import { printSuiteSummary, type CheckResult } from '../utils/reporting.js';

const log = createLogger('Integration');

export async function runIntegration(env: CommandEnv): Promise<boolean> {
  const client = new AgentClient({
    baseUrl: env.backendUrl,
    hfToken: env.hfToken,
    timeoutMs: 60_000,
  });
  const results: CheckResult[] = [];

  log.step(0, 'Create session');
  let sessionId: string;
  try {
    const session = await client.createSession(env.testModel);
    sessionId = session.session_id;
    log.info(`${sessionId} (${session.model})`);
  } catch (error) {
    log.fail(String(error));
    return false;
  }

  try {
    log.step(1, 'Basic Chat');
    try {
      const collector = new TraceCollector(sessionId);
      collector.startTurn('What is 2+2? Just the number.');

      const { events, response } = await client.submitAndCollect(
        sessionId,
        'What is 2+2? Just the number.',
        { timeoutMs: 90_000 },
      );
      for (const event of events) {
        collector.addEvent(event);
      }

      const trace = collector.finalize();
      const analysis = analyzeTrace(trace);
      const ok = events.some((event) => event.event_type === 'turn_complete') && !!response && !trace.metrics.doomLoopDetected;

      results.push({
        name: 'Chat',
        status: ok ? 'pass' : 'fail',
        detail: `${events.length} events, q=${analysis.qualityScore}`,
      });
      ok ? log.ok('Chat works') : log.fail('Chat issues');
    } catch (error) {
      results.push({ name: 'Chat', status: 'fail', detail: String(error) });
      log.fail(String(error));
    }

    log.step(2, 'SSE Structure');
    try {
      const { events } = await client.submitAndCollect(sessionId, 'Say hello.', { timeoutMs: 90_000 });
      const types = [...new Set(events.map((event) => event.event_type))];
      const ok = events.every((event) => event.event_type.length > 0) && events.some((event) => event.event_type === 'turn_complete');

      results.push({
        name: 'SSE',
        status: ok ? 'pass' : 'fail',
        detail: types.join(', '),
      });
      ok ? log.ok('SSE valid') : log.fail('SSE issues');
    } catch (error) {
      results.push({ name: 'SSE', status: 'fail', detail: String(error) });
      log.fail(String(error));
    }

    log.step(3, 'Session State');
    try {
      const session = await client.getSession(sessionId);
      const ok = session.turn_count >= 2 && session.is_active;

      results.push({
        name: 'State',
        status: ok ? 'pass' : 'fail',
        detail: `turns=${session.turn_count}`,
      });
      ok ? log.ok(`${session.turn_count} turns`) : log.fail('State mismatch');
    } catch (error) {
      results.push({ name: 'State', status: 'fail', detail: String(error) });
      log.fail(String(error));
    }
  } finally {
    try {
      await client.deleteSession(sessionId);
    } catch {
      // Best-effort cleanup only.
    }
  }

  printSuiteSummary('INTEGRATION', results, env.jsonOutput);
  return results.every((result) => result.status === 'pass');
}
