import { stage } from "./navigation";
import { test, expect } from "@playwright/test";
import type { components } from "../lib/api.generated";

type Campaign = components["schemas"]["Campaign"];
type Matrix = components["schemas"]["MatrixSnapshot"];

test("stored 27-cell multilingual matrix, real returned previews and reload", async ({ page, request }) => {
  test.setTimeout(120000);
  const base = "http://127.0.0.1:8000/api/campaigns";
  let response = await request.post(base, { data: {
    languages: ["en", "kn", "kn-Latn"], channels: ["instagram", "whatsapp", "facebook"],
  } });
  expect(response.status()).toBe(201);
  let campaign: Campaign = await response.json();
  response = await request.post(`${base}/${campaign.id}/intent`, { data: {
    expected_revision: campaign.revision,
    transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all.",
  } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/${campaign.id}/facts/surface`, { data: {
    expected_revision: campaign.revision, confirm_canonical: true,
  } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/${campaign.id}/facts/lock`, { data: {
    expected_revision: campaign.revision, idempotency_key: `matrix-${campaign.id}`,
    reviewed_fact_versions: Object.fromEntries(campaign.facts.map(f => [f.key, f.version])),
    forms: campaign.facts.filter(f => f.canonical).map(f => ({ key: f.key, surface: f.surface })),
    approve_canonical_and_forms: true,
    acknowledged_warning_ids: campaign.warnings.map(w => w.id),
  } });
  expect(response.ok()).toBeTruthy();
  await page.goto(`/?campaign=${campaign.id}`);
  await stage(page,"brand-strategy");
  let panel = page.getByRole("region", { name: "A different reason to connect" });
  await panel.getByRole("button", { name: "Plan audience strategies" }).click();
  await expect(panel.getByText("MOCK · Hypothetical strategy · Saved personas: 5", { exact: true })).toBeVisible({ timeout: 20000 });
  await panel.getByRole("button", { name: "Generate selected matrix" }).click();
  panel=page.locator("#campaign-matrix");
  await expect(panel.getByText(/Generation completed · 27\/27 drafts ready/)).toBeVisible({ timeout: 60000 });
  const saved: Matrix = await (await request.get(`${base}/${campaign.id}/matrix`)).json();
  expect(saved.run?.cells).toHaveLength(27);
  expect(saved.run?.calls_used).toBe(3);
  expect(new Set(saved.strategy?.personas.map(p => p.id)).size).toBe(5);
  for (const language of ["en", "kn", "kn-Latn"]) {
    await panel.getByRole("combobox", { name: "Preview language", exact: true }).selectOption(language);
    for (const channel of ["instagram", "whatsapp", "facebook"]) {
      await panel.getByRole("group", { name: "Preview channel" }).getByRole("button", { name: channel==="whatsapp" ? "WhatsApp" : channel[0].toUpperCase()+channel.slice(1), exact: true }).click();
      const expected = saved.run!.cells.filter(c => c.language === language && c.channel === channel);
      expect(new Set(expected.map(c => c.variant!.template.headline)).size).toBe(3);
      for (const cell of expected) {
        const fields = cell.variant!.report.rendered!.fields;
        await expect(panel.getByText(fields.headline, { exact: true })).toBeVisible();
        expect(cell.variant!.report.approval_ready).toBe(false);
        expect(cell.variant!.report.missing_checks).toContain("G14");
      }
    }
  }
  await page.reload();
  await expect(panel.getByText(/Generation completed · 27\/27 drafts ready/)).toBeVisible();
  const reloaded: Matrix = await (await request.get(`${base}/${campaign.id}/matrix`)).json();
  expect(reloaded).toEqual(saved);
  await panel.getByRole("combobox", { name: "Preview language", exact: true }).selectOption("kn");
  await panel.screenshot({ path: "../docs/evidence/redesign-regression-regression-b3-matrix-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await panel.screenshot({ path: "../docs/evidence/redesign-regression-regression-b3-matrix-mobile.png" });
});
