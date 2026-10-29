import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/h5',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5190',
    screenshot: 'on',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
