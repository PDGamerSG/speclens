import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:8771', headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: '../.venv/bin/python ../tests/ui_server.py', url: 'http://127.0.0.1:8771/api/workspace/status', reuseExistingServer: !process.env.CI, timeout: 30_000 },
})
