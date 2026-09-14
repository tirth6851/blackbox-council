import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8011;
const WEB_PORT = 3011;

// Run the whole e2e suite with an operator credential configured on both
// processes: this is what actually proves the browser flow still works
// end to end when a real deployment protects approval/execute/rollback,
// with the shared secret held only by the Next.js server (never sent to
// or read by the browser) and forwarded via the BFF proxy route.
const TEST_OPERATOR_CREDENTIAL = "e2e-test-operator-credential";

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
      command: `bash -c "cd ../api && source .venv/bin/activate && DATABASE_URL=sqlite:///./runtime/e2e.db CORS_ORIGINS='[\\"http://127.0.0.1:${WEB_PORT}\\"]' OPERATOR_CREDENTIAL='${TEST_OPERATOR_CREDENTIAL}' uvicorn app.main:app --port ${API_PORT}"`,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        NEXT_PUBLIC_API_BASE_URL: `http://127.0.0.1:${API_PORT}`,
        // Deliberately not NEXT_PUBLIC_-prefixed: only the Next.js server
        // process (and the proxy route it runs) ever sees this value.
        OPERATOR_CREDENTIAL: TEST_OPERATOR_CREDENTIAL,
      },
    },
  ],
});
