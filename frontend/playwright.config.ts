import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  reporter: "list",
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "cd ../backend && rm -rf .e2e && EMBEDDER=hash LLM=fake DATABASE_PATH=.e2e/e2e.db STORAGE_DIR=.e2e/storage .venv/bin/uvicorn app.main:get_app --factory --port 8000",
      url: "http://localhost:8000/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 3000",
      url: "http://localhost:3000/login",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
