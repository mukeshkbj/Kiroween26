import { defineConfig } from 'vitest/config';

// Scratch config for live-agent.test.ts (node environment; see the test header).
export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    include: ['test/live-agent.test.ts'],
    testTimeout: 30000,
  },
});
