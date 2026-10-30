import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Workers inherit this invocation's fixtures; existing runtime inputs are untouched.
process.env.PDTL_BROWSER_INPUTS ??= mkdtempSync(join(tmpdir(), 'pdtl-browser-inputs-'));

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  workers: 1,
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:5180", trace: "retain-on-failure" },
  projects: [{ name: "wide", use: { browserName: "chromium", viewport: { width: 1440, height: 960 } } }, { name: "mobile", use: { browserName: "chromium", ...devices["iPhone 13"] } }],
  webServer: [
    { command: "PYTHONPATH=src python3 scripts/browser_api.py", cwd: "..", port: 8100, reuseExistingServer: false, env: { PDTL_BROWSER_INPUTS: process.env.PDTL_BROWSER_INPUTS } },
    { command: "npm run dev -- --host 127.0.0.1 --port 5180 --strictPort", cwd: ".", port: 5180, env: { PDTL_API: "http://127.0.0.1:8100" }, reuseExistingServer: false },
  ],
});
