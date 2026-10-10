import { stage, trace, closeTrace } from "./navigation";
import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import type { components } from "../lib/api.generated";

type Campaign = components["schemas"]["Campaign"];
test("durable generate survives page closure, reconnect, owner approval and explicit saved view", async ({ page, request, context }) => {
  test.setTimeout(180000);
  const api = "http://127.0.0.1:8000/api";
  let response = await request.post(`${api}/campaigns`, { data: { languages: ["en"], channels: ["whatsapp"] } });
  let campaign: Campaign = await response.json();
  const base = `${api}/campaigns/${campaign.id}`;
  response = await request.post(`${base}/intent`, { data: { expected_revision: campaign.revision, transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all." } });
  campaign = await response.json();
  response = await request.post(`${base}/facts/surface`, { data: { expected_revision: campaign.revision, confirm_canonical: true } });
  campaign = await response.json();
  response = await request.post(`${base}/facts/lock`, { data: { expected_revision: campaign.revision, idempotency_key: crypto.randomUUID(), reviewed_fact_versions: Object.fromEntries(campaign.facts.map(f => [f.key, f.version])), forms: campaign.facts.filter(f => f.canonical).map(f => ({key: f.key, surface: f.surface})), approve_canonical_and_forms: true, acknowledged_warning_ids: campaign.warnings.map(w => w.id) } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  await page.goto(`/?campaign=${campaign.id}`);
  await expect(page.getByRole("navigation", { name: "Campaign workflow" }).locator(".stepper-item")).toHaveCount(8);
  const stageIds=["speak-type","facts-lock","brand-strategy","campaign-matrix","prediction","guardian","ledger-changes","approve-export"];
  for(const id of stageIds){await stage(page,id);}

  await trace(page);
  await page.getByRole("button", { name: "Switch explicitly to saved output" }).click();
  await expect(page.getByText("No captured output exists.", { exact: false })).toBeVisible();
  // A healthy progress poll must not dismiss a failed owner operation.
  await page.waitForTimeout(2200);
  await expect(page.getByText("No captured output exists.", { exact: false })).toBeVisible();
  await closeTrace(page);
  await stage(page,"brand-strategy");
  await page.getByRole("button", { name: "Plan audience strategies" }).click();
  await expect(page.getByText("MOCK · Hypothetical strategy · Saved personas: 5", {exact: true})).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("button", {name: "Generate selected matrix"})).toBeEnabled();
  const created = page.waitForResponse(r => r.url().endsWith("/work") && r.request().method() === "POST" && r.request().postDataJSON().kind === "generate");
  await page.getByRole("button", { name: "Generate selected matrix" }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  const job = await (await created).json();
  expect(job.status).toBe("queued");
  await page.close();
  const reopened = await context.newPage();
  await reopened.goto(`/?campaign=${campaign.id}`);
  await stage(reopened,"campaign-matrix");
  await expect.poll(async () => (await (await request.get(`${api}/work/${job.id}`)).json()).status, { timeout: 60000 }).toBe("completed");
  await expect(reopened.getByText(/Generation completed · 3\/3 drafts ready/)).toBeVisible({ timeout: 15000 });
  const jobs = await (await request.get(`${base}/work`)).json();
  expect(jobs.jobs.filter((j: {kind: string}) => j.kind === "generate")).toHaveLength(1);
  expect(jobs.jobs.find((j: {id: string}) => j.id === job.id).calls).toBe(1);
  const costBefore = await (await request.get(`${api}/cost`)).json();
  await trace(reopened);
  await reopened.route(`**/api/stream/${campaign.id}*`, route => route.abort());
  await reopened.getByRole("button", { name: "Reconnect and reload jobs" }).click();
  await expect(reopened.getByText(/Reconnecting progress/)).toBeVisible();
  await reopened.unroute(`**/api/stream/${campaign.id}*`);
  await reopened.getByRole("button", { name: "Reconnect and reload jobs" }).click();
  await expect(reopened.getByText("✓ Progress connected", {exact: true})).toBeVisible();
  expect(await (await request.get(`${api}/cost`)).json()).toEqual(costBefore);
  await closeTrace(reopened);
  await stage(reopened,"approve-export");
  const delivery = reopened.getByRole("region", { name: "Approve and export" });
  await delivery.getByRole("button", { name: "Audit this item" }).first().click();
  await expect(delivery.getByText(/audit PASS/).first()).toBeVisible({timeout: 30000});
  await delivery.getByRole("checkbox").first().check();
  await delivery.getByLabel("I approve the exact selected current content and poster bytes.").check();
  await delivery.getByRole("button", {name: "Approve selected items"}).click();
  await expect(delivery.getByText(/Owner approval recorded/).first()).toBeVisible();
  await delivery.getByRole("button", {name: "Authorize selected export"}).click();
  await expect(delivery.getByRole("link", {name: "Open WhatsApp draft"})).toBeVisible();
  await trace(reopened);
  await reopened.getByRole("button", {name: "Switch explicitly to saved output"}).click();
  await expect(reopened.getByText("SAVED DEMO OUTPUT · CACHED VIEW · read only")).toBeVisible();
  const cachedZip = reopened.getByRole("link", {name: "Download authorized saved ZIP and manifest"});
  await expect(cachedZip).toHaveAttribute("href", /saved_view=true/);
  const zipResponse = await request.get("http://127.0.0.1:8000" + await cachedZip.getAttribute("href"));
  expect(zipResponse.status()).toBe(200); expect((await zipResponse.body()).subarray(0,2).toString()).toBe("PK");
  await closeTrace(reopened);
  await expect(delivery.getByRole("button", {name: "Approve selected items"})).toBeDisabled();
  await reopened.screenshot({path: "../docs/evidence/redesign-regression-saved-workflow.png", fullPage: true});
  await trace(reopened);
  await reopened.getByRole("button", {name: "Return to current workspace"}).click();
  await closeTrace(reopened);
  await reopened.setViewportSize({width: 390, height: 844});
  expect(await reopened.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await reopened.getByRole("navigation").scrollIntoViewIfNeeded();
  await reopened.screenshot({path: "../docs/evidence/redesign-regression-workflow-mobile.png"});
  await writeFile("../docs/evidence/redesign-regression-browser-run.json", JSON.stringify({timestamp: new Date().toISOString(), mode: "MOCK", campaign: campaign.id, job: job.id, result: "PASS", rapid_generate: "one job / one copy call", page_close_reopen: "PASS", sse_reconnect: "PASS / no new cost", saved_manifest: "cached / source mock", mobile_width: 390, live_inference: "NOT_TESTED"}, null, 2));
});

test("microphone permission denial leaves editable text and accessible navigation", async ({page}) => {
  await page.addInitScript(() => {
    class DeniedSpeech {
      onerror: ((event: {error: string}) => void) | null = null;
      start() { queueMicrotask(() => this.onerror?.({error: "not-allowed"})); }
      stop() {} abort() {}
    }
    Object.defineProperty(window, "SpeechRecognition", {value: DeniedSpeech});
    Object.defineProperty(window, "webkitSpeechRecognition", {value: undefined});
  });
  await page.goto("/");
  await page.getByRole("button",{name:"Start a campaign",exact:true}).click();
  await page.getByRole("button", {name: "Use microphone"}).click();
  await expect(page.getByText("Microphone permission denied.", {exact: false})).toBeVisible();
  await page.getByLabel("Your brief · review the transcript").fill("fifteen or fifty — owner must review");
  await expect(page.getByLabel("Your brief · review the transcript")).toHaveValue("fifteen or fifty — owner must review");
  await page.goto("/");
  await page.keyboard.press("Control+Home");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", {name: "Skip to workspace"})).toBeFocused();
});

test("backend unavailable is an error with actionable reconnection", async ({page}) => {
  await page.route("**/api/**", route => route.abort());
  await page.goto("/");
  await expect(page.getByText("Cannot reach the local backend.", {exact: false})).toBeVisible();
  await expect(page.getByRole("button", {name: "Retry connection"})).toBeEnabled();
  await page.unroute("**/api/**");
  await page.getByRole("button", {name: "Retry connection"}).click();
  await trace(page);
  await expect(page.getByRole("button", {name: "Refresh status"})).toBeVisible();
});

test("owner cancellation stays terminal and explicit retry finishes only new work", async ({page, request}) => {
  test.setTimeout(90000);
  const root = "http://127.0.0.1:8000/api/campaigns";
  let campaign: Campaign = await (await request.post(root, {data: {languages: ["en"], channels: ["whatsapp"]}})).json();
  const base = `${root}/${campaign.id}`;
  campaign = await (await request.post(`${base}/intent`, {data: {expected_revision: campaign.revision, transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all."}})).json();
  campaign = await (await request.post(`${base}/facts/surface`, {data: {expected_revision: campaign.revision, confirm_canonical: true}})).json();
  campaign = await (await request.post(`${base}/facts/lock`, {data: {expected_revision: campaign.revision, idempotency_key: crypto.randomUUID(), reviewed_fact_versions: Object.fromEntries(campaign.facts.map(f => [f.key, f.version])), forms: campaign.facts.filter(f => f.canonical).map(f => ({key: f.key, surface: f.surface})), approve_canonical_and_forms: true, acknowledged_warning_ids: campaign.warnings.map(w => w.id)}})).json();
  expect((await request.post(`${base}/strategy`, {data: {expected_revision: campaign.revision}})).ok()).toBeTruthy();
  if (process.env.WORKFLOW_ISOLATED === "1") {
    expect((await request.post(`http://127.0.0.1:8000/api/__test/hold-next-generation/${campaign.id}`)).ok()).toBeTruthy();
  }
  await page.goto(`/?campaign=${campaign.id}`);
  await stage(page,"brand-strategy");
  await page.getByRole("button", {name: "Generate selected matrix"}).click();
  await trace(page);
  await page.getByRole("button", {name: "Cancel generate", exact: true}).click();
  await expect(page.getByText("■ Cancelled · generate", {exact: true})).toBeVisible();
  let run = (await (await request.get(`${base}/matrix`)).json()).run;
  expect(run.status).toBe("cancelled");
  expect(run.cells.some((c: {state: string}) => c.state === "ready")).toBe(false);
  await page.reload();
  await trace(page);
  await expect(page.getByText("■ Cancelled · generate", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Retry unfinished generate", exact: true}).click();
  await closeTrace(page);
  await stage(page,"campaign-matrix");
  await expect(page.getByText(/Generation completed · 3\/3 drafts ready/)).toBeVisible({timeout: 60000});
  await trace(page);
  run = (await (await request.get(`${base}/matrix`)).json()).run;
  expect(run.calls_used).toBe(1);
  await page.getByRole("complementary", {name: "Work and recovery"}).screenshot({path: "../docs/evidence/redesign-regression-cancel-retry.png"});
});

test("reopened pending fact extraction refreshes editable facts without a second job", async ({page, request, context}) => {
  test.setTimeout(60000);
  const root = "http://127.0.0.1:8000/api/campaigns";
  const warm = await (await request.post(root, {data: {languages: ["en"], channels: ["whatsapp"]}})).json();
  expect((await request.post(`${root}/${warm.id}/intent`, {data: {expected_revision: warm.revision, transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all."}})).ok()).toBeTruthy();
  await page.goto("/");
  await page.getByRole("button",{name:"Start a campaign",exact:true}).click();
  await page.getByLabel("Your brief · review the transcript").fill("Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all.");
  const response = page.waitForResponse(r => r.url().endsWith("/work") && r.request().method() === "POST" && r.request().postDataJSON().kind === "intent");
  await page.getByRole("button", {name: "Propose facts from transcript", exact: true}).click();
  const job = await (await response).json();
  await page.close();
  const reopened = await context.newPage();
  await reopened.goto(`/?campaign=${job.campaign_id}`);
  await stage(reopened,"facts-lock");
  await expect(reopened.getByLabel("Café name", {exact: true})).toHaveValue("Namma Cafe", {timeout: 30000});
  await expect(reopened.getByText("Editable draft", {exact: true})).toBeVisible();
  const jobs = await (await request.get(`${root}/${job.campaign_id}/work`)).json();
  expect(jobs.jobs.filter((j: {kind: string}) => j.kind === "intent")).toHaveLength(1);
  expect(jobs.jobs[0].status).toBe("completed");
});
