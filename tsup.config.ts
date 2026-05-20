import { defineConfig } from 'tsup';

export default defineConfig({
  entry: {
    cli: 'src/cli.ts',
    index: 'src/index.ts',
    'client/index': 'src/client/index.ts',
    'commands/index': 'src/commands/index.ts',
    'evaluator/index': 'src/evaluator/index.ts',
    'trace/index': 'src/trace/index.ts',
    'utils/index': 'src/utils/index.ts',
  },
  format: ['esm'],
  dts: true,
  clean: true,
  splitting: true,
  sourcemap: true,
  target: 'node22',
  external: ['chalk'],
});
