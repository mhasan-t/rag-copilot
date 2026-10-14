import { defineConfig } from '@playwright/test'

// Browser tests against the running dev stack (`make up`): the UI on :5173, the real API behind it.
export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  // The tests share seeded runs and the demo service, so run them one after another.
  workers: 1,
  timeout: 60_000,
  use: { baseURL: 'http://localhost:5173', channel: 'chrome', trace: 'retain-on-failure' },
})
