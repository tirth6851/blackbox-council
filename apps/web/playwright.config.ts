import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8011;
const WEB_PORT = 3011;

// This sandbox's environment pre-installs Chromium at a fixed path and
// skips Playwright's own browser download (see README/CI docs). Use it
// when present; otherwise (e.g. plain `npx playwright install` in CI or a
// contributor's machine) fall back to Playwright's own managed browser.
const SANDBOX_CHROMIUM_PATH = "/opt/pw-browsers/chromium";
const executablePath = existsSync(SANDBOX_CHROMIUM_PATH) ? SANDBOX_CHROMIUM_PATH : undefined;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(executablePath ? { launchOptions: { executablePath } } : {}),
      },
    },
  ],
  webServer: [
    {
      command: `bash -c "cd ../api && source .venv/bin/activate && DATABASE_URL=sqlite:///./runtime/e2e.db CORS_ORIGINS='[\\"http://127.0.0.1:${WEB_PORT}\\"]' uvicorn app.main:app --port ${API_PORT}"`,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { NEXT_PUBLIC_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
