import { defineConfig } from "@playwright/test";
import config from "./playwright.config";

// Verification recording only: actual MOCK app execution, never live proof.
export default defineConfig({
  ...config,
  workers: 1,
  testMatch: /delivery\.spec\.ts/,
  outputDir: "test-results/b8-backup-recording",
  use: { ...config.use, video: { mode: "on", size: { width: 1280, height: 720 } } },
});
