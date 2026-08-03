import { defineConfig, devices } from "@playwright/test";

const isolatedDatabaseUrl =
  process.env.E2E_DATABASE_URL ||
  `sqlite:////tmp/interview-lab-e2e-${process.pid}.db`;
const e2ePort = process.env.E2E_PORT || "8011";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["dot"]] : "dot",
  use: {
    baseURL: process.env.E2E_BASE_URL || `http://127.0.0.1:${e2ePort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command:
          `cd .. && APP_API_KEY= ZHIPU_API_KEY= ZHIPU_EMBEDDING_API_KEY= WEB_SEARCH_API_KEY= TRANSCRIPTION_API_KEY= AUTH_REQUIRED=${process.env.E2E_AUTH_REQUIRED || "false"} OTEL_ENABLED=false LOG_LEVEL=WARNING RATE_LIMIT_REQUESTS=500 AUTO_CREATE_SCHEMA=true DATABASE_URL=${isolatedDatabaseUrl} FRONTEND_DIST=frontend/dist ${
            process.env.CI ? "python" : ".venv/bin/python"
          } -m uvicorn app.main:app --host 127.0.0.1 --port ${e2ePort}`,
        url: `http://127.0.0.1:${e2ePort}/today`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
