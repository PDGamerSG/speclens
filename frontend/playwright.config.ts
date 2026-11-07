import { defineConfig } from '@playwright/test'

const port = process.env.E2E_PORT || '8771'
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 30_000,
  use: { baseURL: `http://127.0.0.1:${port}`, headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: '../.venv/bin/python ../tests/ui_server.py', url: `http://127.0.0.1:${port}/api/workspace/status`, reuseExistingServer: !process.env.CI, timeout: 30_000 },
})
