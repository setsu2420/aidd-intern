export function reportStep(testName: string, message: string, details?: unknown): void {
  const suffix = details === undefined ? '' : ` ${JSON.stringify(details)}`;
  console.info(`[${testName}] ${message}${suffix}`);
}
