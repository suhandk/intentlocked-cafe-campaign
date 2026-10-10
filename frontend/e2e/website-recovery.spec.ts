import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

async function openWebsite(page: Page, request: APIRequestContext) {
  const api = "http://127.0.0.1:8000/api";
  let campaign = await (await request.post(`${api}/campaigns`, { data: { languages: ["en"], channels: ["whatsapp"] } })).json();
  const base = `${api}/campaigns/${campaign.id}`;
  campaign = await (await request.post(`${base}/intent`, { data: { expected_revision: campaign.revision,
    transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all." } })).json();
  campaign = await (await request.post(`${base}/facts/surface`, { data: { expected_revision: campaign.revision, confirm_canonical: true } })).json();
  campaign = await (await request.post(`${base}/facts/lock`, { data: { expected_revision: campaign.revision,
    idempotency_key: crypto.randomUUID(), reviewed_fact_versions: Object.fromEntries(campaign.facts.map((f: {key: string; version: number}) => [f.key, f.version])),
    forms: campaign.facts.filter((f: {canonical: unknown}) => f.canonical).map((f: {key: string; surface: unknown}) => ({key: f.key, surface: f.surface})),
    approve_canonical_and_forms: true, acknowledged_warning_ids: campaign.warnings.map((w: {id: string}) => w.id) } })).json();
  expect(campaign.status).toBe("locked");
  await page.goto(`/?campaign=${campaign.id}#campaign-matrix`);
  await page.getByRole("button", { name: "Create website", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Create website", exact: true });
  await expect(dialog.getByText("Draft saved", { exact: true })).toBeVisible();
  await dialog.getByLabel("Café name (required)").fill("Namma Cafe");
  await dialog.getByLabel("City/area (required)").fill("Bengaluru");
  await expect(dialog.getByRole("status")).toHaveText("Draft saved");
  return { dialog, campaignId: campaign.id };
}

test("incomplete hours do not trap navigation; owner fixes them and exports the real website", async ({ page, request }) => {
  const { dialog } = await openWebsite(page, request);
  const saves: {fields: {hours: {open: string; close: string}[]}}[] = [];
  page.on("request", r => { if (r.method() === "PUT" && /\/api\/websites\/[a-f0-9]+$/.test(r.url())) saves.push(r.postDataJSON()); });
  await dialog.getByRole("button", {name: "3. Visit info", exact: true}).click();
  await dialog.getByLabel("Address (optional)").fill("Test café address");
  await dialog.getByLabel("Add opening day").selectOption("MON");
  await dialog.getByLabel("open", {exact: true}).fill("09:00");
  await dialog.getByRole("button", {name: "1. Basics", exact: true}).click();
  await expect(dialog.getByLabel("Café name (required)")).toHaveValue("Namma Cafe");
  await expect(dialog.getByRole("status")).toContainText("Edits not saved yet");
  await dialog.getByRole("button", {name: "Save and close", exact: true}).click();
  await expect(dialog.getByRole("alert")).toContainText("opening");
  await dialog.getByRole("button", {name: "Keep editing", exact: true}).click();
  await dialog.getByRole("button", {name: "6. Review", exact: true}).click();
  await expect(dialog.getByRole("button", {name: "Generate website", exact: true})).toBeDisabled();
  await dialog.getByRole("button", {name: "Fix opening hours", exact: true}).click();
  await expect(dialog.getByLabel("Address (optional)")).toHaveValue("Test café address");
  await expect(dialog.getByLabel("open", {exact: true})).toHaveValue("09:00");
  await dialog.getByLabel("close", {exact: true}).fill("18:00");
  await expect(dialog.getByRole("status")).toHaveText("Draft saved");
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await dialog.getByRole("button", {name: "6. Review", exact: true}).click();
  await dialog.getByRole("button", {name: "Generate website", exact: true}).click();
  await expect(dialog.getByTitle("DRAFT - NOT PUBLISHED website preview")).toBeVisible();
  await dialog.getByRole("button", {name: "7. Publish", exact: true}).click();
  const href = await dialog.getByRole("link", {name: "Download website (zip)"}).getAttribute("href");
  const download = await request.get(href!);
  expect(download.status()).toBe(200);
  expect((await download.body()).subarray(0, 2).toString()).toBe("PK");
  expect(saves.every(s => s.fields.hours.every(h => h.open && h.close))).toBeTruthy();
  await dialog.screenshot({path: "../docs/evidence/website-recovery-download.png"});
  await dialog.getByRole("button", {name: "Save and close", exact: true}).click();
  await page.reload();
  await page.getByRole("button", {name: "Create website", exact: true}).click();
  await dialog.getByRole("button", {name: "3. Visit info", exact: true}).click();
  await expect(dialog.getByLabel("close", {exact: true})).toHaveValue("18:00");
});

test("unfinished menu can be explicitly discarded; failed saves retry without losing input", async ({ page, request }) => {
  const { dialog } = await openWebsite(page, request);
  await dialog.getByRole("button", {name: "4. Menu", exact: true}).click();
  await dialog.getByRole("button", {name: "Add menu row", exact: true}).click();
  await dialog.getByRole("button", {name: "1. Basics", exact: true}).click();
  await dialog.getByRole("button", {name: "Save and close", exact: true}).click();
  await dialog.getByRole("button", {name: "Discard unsaved edits and close", exact: true}).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", {name: "Create website", exact: true}).click();
  await dialog.getByRole("button", {name: "4. Menu", exact: true}).click();
  await expect(dialog.getByLabel("Menu item 1", {exact: true})).toHaveCount(0);
  await dialog.getByRole("button", {name: "3. Visit info", exact: true}).click();
  let failed = false;
  await page.route("**/api/websites/*", async route => {
    if (route.request().method() === "PUT" && !failed) { failed = true; await route.fulfill({status: 503, json: {message: "Website server temporarily unavailable"}}); }
    else await route.continue();
  });
  await dialog.getByLabel("Address (optional)").fill("Keep this test address");
  await expect(dialog.getByRole("alert")).toContainText("temporarily unavailable");
  await dialog.getByRole("button", {name: "Retry save", exact: true}).click();
  await expect(dialog.getByRole("status")).toHaveText("Draft saved");
  await expect(dialog.getByLabel("Address (optional)")).toHaveValue("Keep this test address");
  await dialog.getByRole("button", {name: "Save and close", exact: true}).click();
  await page.reload();
  await page.getByRole("button", {name: "Create website", exact: true}).click();
  await expect(dialog.getByLabel("Address (optional)")).toHaveValue("Keep this test address");
});

test("an older autosave response cannot claim newer incomplete hours were saved", async ({ page, request }) => {
  const { dialog } = await openWebsite(page, request);
  await dialog.getByRole("button", {name: "3. Visit info", exact: true}).click();
  await expect(dialog.getByRole("status")).toHaveText("Draft saved");
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let held = false;
  let submitted = 0;
  page.on("request", r => { if (r.method() === "PUT" && /\/api\/websites\/[a-f0-9]+$/.test(r.url())) submitted++; });
  const responseFinished = page.waitForResponse(r => r.request().method() === "PUT" && /\/api\/websites\/[a-f0-9]+$/.test(r.url()));
  await page.route("**/api/websites/*", async route => {
    if (route.request().method() !== "PUT" || held) { await route.continue(); return; }
    const response = await route.fetch(); held = true;
    await gate; await route.fulfill({response});
  });
  try {
    await dialog.getByLabel("Address (optional)").fill("Delayed-save test address");
    await expect.poll(() => held).toBeTruthy();
    await dialog.getByLabel("Address (optional)").fill("Superseded address one");
    await dialog.getByLabel("Address (optional)").fill("Superseded address two");
    await dialog.getByLabel("Address (optional)").fill("Keep the latest address");
    await dialog.getByLabel("Add opening day").selectOption("TUE");
    release(); await (await responseFinished).finished();
    await page.waitForTimeout(200);
    await expect(dialog.getByRole("status")).toContainText("Edits not saved yet");
    expect(submitted).toBe(1);
    await dialog.getByLabel("open", {exact: true}).fill("10:00");
    await dialog.getByLabel("close", {exact: true}).fill("19:00");
    await expect(dialog.getByRole("status")).toHaveText("Draft saved");
    expect(submitted).toBe(2);
    await expect(dialog.getByLabel("Address (optional)")).toHaveValue("Keep the latest address");
  } finally { release(); }
});
