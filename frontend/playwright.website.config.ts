import { defineConfig } from "@playwright/test";
// Started only by the isolated verification harness; never targets a user's live server.
export default defineConfig({
  testDir: "./e2e", testMatch: /website\.spec\.ts/, workers: 1,
  use: { baseURL: "https://localhost:3000", ignoreHTTPSErrors: true, channel: "chrome" },
});
