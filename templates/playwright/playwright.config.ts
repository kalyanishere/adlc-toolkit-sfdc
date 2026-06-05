// playwright.config.ts — Salesforce Playwright harness
//
// Wired to satisfy agents/test-auditor.md severities:
//   - retries directive present (Major if missing)
//   - globalSetup reference present (Major if missing)
//   - prod project carries `grep: /@prod-safe/` (Critical if missing)
//
// Ports come from .adlc/config.yml `orgs:` block via env vars set by
// /canary or by `npm run test:e2e -- --project=<env>`. The login URL is
// produced by global-setup.ts via `sf org display --target-org`.

import { defineConfig, devices } from '@playwright/test';

const reportDir = process.env.PLAYWRIGHT_REPORT_DIR ?? 'reports/playwright';

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: `${reportDir}/html`, open: 'never' }],
    ['junit', { outputFile: `${reportDir}/junit.xml` }],
  ],
  globalSetup: require.resolve('./tests/e2e/global-setup'),
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    storageState: 'tests/e2e/storageState.json',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'sandbox',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'staging',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      // Prod is read-only smoke only. Specs MUST tag `@prod-safe` to run here.
      // test-auditor.md flags any prod project without this grep as Critical.
      name: 'prod',
      grep: /@prod-safe/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
