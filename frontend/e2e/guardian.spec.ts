import { stage } from "./navigation";
import { test, expect } from "@playwright/test";
import type { components } from "../lib/api.generated";

type Campaign = components["schemas"]["Campaign"];

test("Guardian fragments, complete asset readiness and Kannada preservation", async ({ page, request }) => {
  test.setTimeout(90000);
  const base = "http://127.0.0.1:8000/api/campaigns";
  let response = await request.post(base, { data: { languages: ["en", "kn"], channels: ["whatsapp"] } });
  expect(response.status()).toBe(201);
  let campaign: Campaign = await response.json();
  response = await request.post(`${base}/${campaign.id}/intent`, { data: {
    expected_revision: campaign.revision,
    transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all.",
  } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/${campaign.id}/facts/surface`, { data: { expected_revision: campaign.revision, confirm_canonical: true } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/${campaign.id}/facts/lock`, { data: {
    expected_revision: campaign.revision, idempotency_key: `guardian-${campaign.id}`,
    reviewed_fact_versions: Object.fromEntries(campaign.facts.map(f => [f.key, f.version])),
    forms: campaign.facts.filter(f => f.canonical).map(f => ({ key: f.key, surface: f.surface })),
    approve_canonical_and_forms: true,
    acknowledged_warning_ids: campaign.warnings.map(w => w.id),
  } });
  expect(response.ok()).toBeTruthy();
  await page.goto(`/?campaign=${campaign.id}`);
  await stage(page,"guardian");
  const panel = page.getByRole("region", { name: "Guardian · Check the copy" });
  const copy = panel.getByRole("textbox", { name: "Copy", exact: true });
  await copy.fill("not {{OFFER}}");
  await panel.getByRole("button", { name: "Check copy" }).click();
  await expect(panel.getByText("BLOCKED · Fragment diagnostic only", { exact: true })).toBeVisible();
  await copy.fill("{{OFFER}}");
  await expect(panel.getByText("BLOCKED · Fragment diagnostic only", { exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: "Check copy" }).click();
  await expect(panel.getByText("PASS · Fragment diagnostic only", { exact: true })).toBeVisible();
  await panel.getByRole("combobox", { name: "Check mode", exact: true }).selectOption("asset");
  await copy.fill("{{CAFE}} · {{LOCATION}} · {{OFFER}} · {{PRODUCT}} · {{DATES}} · {{DAYS}} · {{ELIGIBILITY}}");
  await panel.getByRole("group",{name:"Copy field"}).getByRole("button",{name:"Call to action",exact:true}).click();
  await panel.getByRole("textbox", { name: "Call to action", exact: true }).fill("Visit us");
  await panel.getByRole("button", { name: "Check copy" }).click();
  await expect(panel.getByText("INCOMPLETE · Complete asset diagnostic", { exact: true })).toBeVisible();
  await expect(panel.getByText("Pending checks: G14", { exact: true })).toBeVisible();
  await panel.getByRole("combobox", { name: "Check mode", exact: true }).selectOption("fragment");
  await panel.getByRole("combobox", { name: "Language", exact: true }).selectOption("kn");
  await panel.getByRole("group",{name:"Copy field"}).getByRole("button",{name:"Copy",exact:true}).click();
  await copy.fill("{{PRODUCT|dat}} {{OFFER}}");
  await panel.getByRole("group",{name:"Copy field"}).getByRole("button",{name:"Call to action",exact:true}).click();
  await panel.getByRole("textbox", { name: "Call to action", exact: true }).fill("");
  await panel.getByRole("button", { name: "Check copy" }).click();
  await expect(panel.getByText("PASS · Fragment diagnostic only", { exact: true })).toBeVisible();
  await panel.getByText("Server-rendered draft and fact provenance", { exact: true }).click();
  await expect(panel.getByText("body: ಕಾಫಿಗೆ 20% ರಿಯಾಯಿತಿ", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await panel.screenshot({ path: "../docs/evidence/redesign-regression-regression-b2-guardian-mobile.png" });
});
