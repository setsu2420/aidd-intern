import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['tests/harness/**/*.test.ts'],
    testTimeout: 10_000,
  },
});
