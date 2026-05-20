import {
  source_default
} from "./chunk-4WEICLE4.js";

// src/utils/reporting.ts
function printSuiteSummary(suite, results, json) {
  if (json) {
    const summary2 = summarize(results);
    console.log(JSON.stringify({ suite, summary: summary2, results }, null, 2));
    return;
  }
  const summary = summarize(results);
  console.log(`
${source_default.bold.blue(`\u2550\u2550\u2550 ${suite} \u2550\u2550\u2550`)}`);
  for (const result of results) {
    const icon = result.status === "pass" ? source_default.green("\u2705") : result.status === "warn" ? source_default.yellow("\u26A0\uFE0F") : source_default.red("\u274C");
    console.log(`  ${icon} ${result.name} \u2014 ${source_default.dim(result.detail)}`);
  }
  const counts = [summary.passed, summary.warned, summary.failed];
  const labels = [`${counts[0]} passed`, `${counts[1]} warned`, `${counts[2]} failed`].filter(
    (item, index) => counts[index] > 0
  );
  console.log(`
  ${source_default.bold(labels.length > 0 ? labels.join(", ") : "0 passed, 0 warned, 0 failed")}
`);
}
function summarize(results) {
  return {
    passed: results.filter((result) => result.status === "pass").length,
    warned: results.filter((result) => result.status === "warn").length,
    failed: results.filter((result) => result.status === "fail").length
  };
}

export {
  printSuiteSummary,
  summarize
};
//# sourceMappingURL=chunk-JZZVF563.js.map