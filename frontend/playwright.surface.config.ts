import {defineConfig} from "@playwright/test";
import recoveryConfig from "./playwright.recovery.config";

export default defineConfig({
  ...recoveryConfig,
  testMatch:["surface-recovery.spec.ts","intent-recovery.spec.ts","approval-recovery.spec.ts"],
  reporter:[["list"],["junit",{outputFile:"../docs/evidence/surface-recovery-browser-tests.xml"}]],
});
