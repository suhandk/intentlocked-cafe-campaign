import { trace, closeTrace } from "./navigation";
import { test, expect } from "@playwright/test";
test("real backend health, cost and keyboard-operable trace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /A campaign that/ })).toBeVisible();
  await expect(page.getByText("MOCK", { exact: true })).toBeVisible();
  await trace(page);
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await page.getByText("Global activity trace", { exact: true }).click();
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(page.getByRole("button", { name: "Refresh status" })).toBeEnabled();
  await closeTrace(page);
  await page.screenshot({ path: "../docs/evidence/redesign-regression-regression-b1-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: /A campaign that/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "../docs/evidence/redesign-regression-regression-b1-mobile.png", fullPage: true });
});
test("backend failure gives a working retry and clears stale success", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, body: "{}" }));
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Cannot reach the local backend" })).toContainText("Start FastAPI");
  await expect(page.locator(".mode-pill")).not.toContainText("MOCK");
  await page.unroute("**/api/**");
  await page.getByRole("button", { name: "Retry connection" }).click();
  await trace(page);
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
});
