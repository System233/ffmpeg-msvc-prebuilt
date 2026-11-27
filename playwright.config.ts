import { defineConfig } from "@playwright/test";
const base = process.env.BASE_URL ?? "/";
const port = process.env.PORT ?? "4173";
const url = "http://127.0.0.1:" + port + base;
export default defineConfig({
  testDir: "tests/e2e",
  use: { baseURL: url, browserName: "chromium" },
  webServer: {
    command: "node scripts/static-server.mjs",
    url,
    timeout: 15000,
    reuseExistingServer: false,
  },
});
