import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir:"./e2e",testMatch:["meta.spec.ts","approval-recovery.spec.ts"],workers:1,
  use:{baseURL:"http://127.0.0.1:3002",channel:"chrome"},
  webServer:{command:"npm run start -- --port 3002",url:"http://127.0.0.1:3002",reuseExistingServer:false},
});
