import {
  TraceCollector,
  analyzeTrace
} from "./chunk-5V6SUACB.js";
import {
  AgentClient
} from "./chunk-JEPPWU25.js";
import {
  printSuiteSummary
} from "./chunk-MVSK6XGK.js";
import {
  createLogger
} from "./chunk-OA6CDQ5U.js";

// src/commands/integration.ts
var log = createLogger("Integration");
async function runIntegration(env) {
  const client = new AgentClient({
    baseUrl: env.backendUrl,
    hfToken: env.hfToken,
    timeoutMs: 6e4
  });
  const results = [];
  log.step(0, "Create session");
  let sessionId;
  try {
    const session = await client.createSession(env.testModel);
    sessionId = session.session_id;
    log.info(`${sessionId} (${session.model})`);
  } catch (error) {
    log.fail(String(error));
    return false;
  }
  try {
    log.step(1, "Basic Chat");
    try {
      const collector = new TraceCollector(sessionId);
      collector.startTurn("What is 2+2? Just the number.");
      const { events, response } = await client.submitAndCollect(
        sessionId,
        "What is 2+2? Just the number.",
        { timeoutMs: 9e4 }
      );
      for (const event of events) {
        collector.addEvent(event);
      }
      const trace = collector.finalize();
      const analysis = analyzeTrace(trace);
      const ok = events.some((event) => event.event_type === "turn_complete") && !!response && !trace.metrics.doomLoopDetected;
      results.push({
        name: "Chat",
        status: ok ? "pass" : "fail",
        detail: `${events.length} events, q=${analysis.qualityScore}`
      });
      ok ? log.ok("Chat works") : log.fail("Chat issues");
    } catch (error) {
      results.push({ name: "Chat", status: "fail", detail: String(error) });
      log.fail(String(error));
    }
    log.step(2, "SSE Structure");
    try {
      const { events } = await client.submitAndCollect(sessionId, "Say hello.", { timeoutMs: 9e4 });
      const types = [...new Set(events.map((event) => event.event_type))];
      const ok = events.every((event) => event.event_type.length > 0) && events.some((event) => event.event_type === "turn_complete");
      results.push({
        name: "SSE",
        status: ok ? "pass" : "fail",
        detail: types.join(", ")
      });
      ok ? log.ok("SSE valid") : log.fail("SSE issues");
    } catch (error) {
      results.push({ name: "SSE", status: "fail", detail: String(error) });
      log.fail(String(error));
    }
    log.step(3, "Session State");
    try {
      const session = await client.getSession(sessionId);
      const ok = session.turn_count >= 2 && session.is_active;
      results.push({
        name: "State",
        status: ok ? "pass" : "fail",
        detail: `turns=${session.turn_count}`
      });
      ok ? log.ok(`${session.turn_count} turns`) : log.fail("State mismatch");
    } catch (error) {
      results.push({ name: "State", status: "fail", detail: String(error) });
      log.fail(String(error));
    }
  } finally {
    try {
      await client.deleteSession(sessionId);
    } catch {
    }
  }
  printSuiteSummary("INTEGRATION", results, env.jsonOutput);
  return results.every((result) => result.status === "pass");
}

export {
  runIntegration
};
//# sourceMappingURL=chunk-YDEKJVWW.js.map