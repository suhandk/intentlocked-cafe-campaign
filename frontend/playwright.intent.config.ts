import {defineConfig} from "@playwright/test";
import recoveryConfig from "./playwright.recovery.config";

export default defineConfig({
  ...recoveryConfig,
  testMatch:["intent-recovery.spec.ts"],
  reporter:[["list"],["junit",{outputFile:"../docs/evidence/intent-recovery-browser-tests.xml"}]],
});
