import chalk from 'chalk';

export type CheckStatus = 'pass' | 'warn' | 'fail';

export interface CheckResult {
  name: string;
  status: CheckStatus;
  detail: string;
}

export function printSuiteSummary(suite: string, results: CheckResult[], json: boolean): void {
  if (json) {
    const summary = summarize(results);
    console.log(JSON.stringify({ suite, summary, results }, null, 2));
    return;
  }

  const summary = summarize(results);
  console.log(`\n${chalk.bold.blue(`═══ ${suite} ═══`)}`);
  for (const result of results) {
    const icon =
      result.status === 'pass'
        ? chalk.green('✅')
        : result.status === 'warn'
          ? chalk.yellow('⚠️')
          : chalk.red('❌');
    console.log(`  ${icon} ${result.name} — ${chalk.dim(result.detail)}`);
  }
  const counts = [summary.passed, summary.warned, summary.failed];
  const labels = [`${counts[0]} passed`, `${counts[1]} warned`, `${counts[2]} failed`].filter(
    (item, index) => counts[index] > 0,
  );
  console.log(`\n  ${chalk.bold(labels.length > 0 ? labels.join(', ') : '0 passed, 0 warned, 0 failed')}\n`);
}

export function summarize(results: CheckResult[]): {
  passed: number;
  warned: number;
  failed: number;
} {
  return {
    passed: results.filter((result) => result.status === 'pass').length,
    warned: results.filter((result) => result.status === 'warn').length,
    failed: results.filter((result) => result.status === 'fail').length,
  };
}
