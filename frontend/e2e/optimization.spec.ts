import { stage } from "./navigation";
import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import type { components } from "../lib/api.generated";
type Campaign = components["schemas"]["Campaign"];
type Matrix = components["schemas"]["MatrixSnapshot"];
type Optimization = components["schemas"]["OptimizationSnapshot"];
type Run = components["schemas"]["OptimizationRun"];
type Poster = components["schemas"]["PosterArtifact"];
type Audit = components["schemas"]["Audit"];
let retainedRun: Run;
test.describe.configure({ mode: "serial" });

test("mock score, critique, permitted edit, verify, compare, retention and stop survive reload", async ({ page, request }) => {
  test.setTimeout(180000);
  const root = "http://127.0.0.1:8000/api/campaigns";
  let response = await request.post(root, { data: { languages: ["en"], channels: ["whatsapp"] } });
  expect(response.status()).toBe(201);
  let campaign: Campaign = await response.json();
  const base = `${root}/${campaign.id}`;
  response = await request.post(`${base}/intent`, { data: { expected_revision: campaign.revision,
    transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all." } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/facts/surface`, { data: { expected_revision: campaign.revision, confirm_canonical: true } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/facts/lock`, { data: { expected_revision: campaign.revision,
    idempotency_key: `g5-lock-${campaign.id}`, reviewed_fact_versions: Object.fromEntries(campaign.facts.map(f => [f.key, f.version])),
    forms: campaign.facts.filter(f => f.canonical).map(f => ({ key: f.key, surface: f.surface })),
    approve_canonical_and_forms: true, acknowledged_warning_ids: campaign.warnings.map(w => w.id) } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${base}/strategy`, { data: { expected_revision: campaign.revision } });
  expect(response.ok()).toBeTruthy(); const plan = await response.json();
  response = await request.post(`${base}/generate`, { data: { expected_revision: campaign.revision,
    strategy_id: plan.id, idempotency_key: `g5-generate-${campaign.id}`, audience_ids: plan.audiences.map((a: { id: string }) => a.id), languages: ["en"], channels: ["whatsapp"] } });
  expect(response.status()).toBe(202);
  await expect.poll(async () => (await (await request.get(`${base}/matrix`)).json()).run.status, { timeout: 45000 }).toBe("completed");
  const matrix: Matrix = await (await request.get(`${base}/matrix`)).json();
  await page.goto(`/?campaign=${campaign.id}`);
  await stage(page,"prediction");
  const panel = page.getByRole("region", { name: "Choose with evidence" });
  await expect(panel.getByRole("button", { name: "Optimize hero group" })).toBeEnabled();
  const startRequest = page.waitForRequest(req => req.url().endsWith("/work") && req.postDataJSON()?.kind === "optimize");
  await panel.getByRole("button", { name: "Optimize hero group" }).click();
  const sent = await startRequest;
  // A fast completed job may arrive before the first UI poll; don't require an ephemeral state.
  await expect(panel.getByText(/Optimization (queued|running|completed)/)).toBeVisible({ timeout: 15000 });
  await expect(panel.getByText(/Optimization completed/)).toBeVisible({ timeout: 90000 });
  const snapshot: Optimization = await (await request.get(`${base}/optimization`)).json();
  const run = snapshot.runs[0]; const group = run.groups[0];
  retainedRun = run;
  expect(run.mode).toBe("mock"); expect(group.rounds?.[0].accepted).toBe(true);
  expect(group.rounds?.[0].guardian?.status).toBe("PASS");
  expect(group.rounds?.[0].score?.complete_judgments).toBe(10);
  expect(group.stop_reason).toBe("NO_GAIN"); expect(group.final_audit?.status).toBe("PASS");
  expect(snapshot.unscored_variant_ids).toHaveLength(2);
  expect(run.calls_used).toBe(6); expect(run.known_cost_usd).toBe(0);
  expect(matrix.run?.cells.find(cell => cell.variant?.id === group.baseline.id)?.variant?.content_hash).toBe(group.baseline.content_hash);
  await panel.getByRole("button", {name: "Render retained square draft"}).click();
  await expect(panel.getByRole("link", {name: "Download exact retained draft PNG · owner approval pending"})).toBeVisible({timeout: 30000});
  const durable = await (await request.get(`${base}/work`)).json();
  expect(durable.jobs.some((job: {kind: string; status: string}) => job.kind === "poster_batch" && job.status === "completed")).toBe(true);
  await panel.getByText("Feature details and score formula").click();
  await panel.screenshot({ path: "../docs/evidence/redesign-regression-regression-b5-trajectory-desktop.png" });
  const duplicate = await request.post(sent.url(), { data: sent.postDataJSON() });
  expect(duplicate.status()).toBe(202); expect((await duplicate.json()).native_run_id).toBe(run.id);
  const nativeDuplicate = await request.post(`${base}/optimize`, {data: sent.postDataJSON().input});
  expect(nativeDuplicate.status()).toBe(202); expect((await nativeDuplicate.json()).id).toBe(run.id);
  await page.reload(); await stage(page,"prediction"); await expect(panel.getByText(/Optimization completed/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await panel.getByRole("heading", { name: "Choose with evidence" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../docs/evidence/redesign-regression-regression-b5-trajectory-mobile.png" });
  await writeFile("../docs/evidence/redesign-regression-regression-b5-browser-run.json", JSON.stringify({ timestamp: new Date().toISOString(),
    outcome: "PASS", mode: "mock", actual_customer_research: "NOT_PERFORMED", native_Kannada: "NOT_TESTED", live_roles: "NOT_TESTED", run }, null, 2));
});

test("retained copy renders actual bytes and blinded poster audit measures features", async ({ page, request }) => {
  test.setTimeout(90000);
  const run = retainedRun; const group = run.groups[0];
  const base = `http://127.0.0.1:8000/api/campaigns/${run.campaign_id}`;
  const records: { poster: Poster; audit: Audit }[] = [];
  for (const [size, width, height] of [["square",1080,1080],["story",1080,1920],["landscape",1200,630]] as const) {
    const backgroundResponse = await request.post(`${base}/backgrounds`, { data: { expected_revision: run.campaign_revision, source: "deterministic", size } });
    expect(backgroundResponse.ok()).toBeTruthy(); const background = await backgroundResponse.json();
    const rendered = await request.post(`${base}/assets/render`, { data: { expected_revision: run.campaign_revision,
      variant_id: group.current_id, background_id: background.id, size } });
    expect(rendered.ok()).toBeTruthy(); const poster: Poster = await rendered.json();
    expect([poster.width,poster.height]).toEqual([width,height]);
    expect(poster.render_input.renderer_version).toBe("canvas-modern-cafe-b1.0");
    expect(poster.validation.offer_area_ratio).toBeGreaterThan(0);
    expect(poster.validation.passed).toBe(true);
    const bytes = await (await request.get(`http://127.0.0.1:8000/api/assets/${poster.id}`)).body();
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(poster.sha256);
    await writeFile(`../docs/evidence/redesign-regression-regression-b5-retained-${size}.png`,bytes);
    const audited = await request.post(`http://127.0.0.1:8000/api/assets/${poster.id}/audit`, { data: { expected_revision: run.campaign_revision } });
    expect(audited.ok()).toBeTruthy(); const audit: Audit = await audited.json();
    expect(audit.status).toBe("PASS"); expect(audit.artifact_hash).toBe(poster.sha256);
    expect(audit.remote_vision).toBe("NOT_TESTED"); expect(audit.approval_ready).toBe(false);
    expect(audit.measured_features?.find(f => f.name === "offer_area")?.value).not.toBeNull();
    expect((await (await request.get(`http://127.0.0.1:8000/api/audits/${audit.id}`)).json())).toEqual(audit);
    records.push({ poster, audit });
  }
  await page.goto(`/?campaign=${run.campaign_id}`);
  await stage(page,"prediction");
  const panel = page.getByRole("region", { name: "Choose with evidence" });
  await expect(panel.getByRole("button", { name: "Render retained square draft" })).toBeEnabled();
  await panel.getByRole("button", { name: "Render retained square draft" }).click();
  await expect(panel.getByRole("link", { name: /Download exact retained draft PNG/ })).toBeVisible();
  await writeFile("../docs/evidence/redesign-regression-regression-b5-poster-audits.json", JSON.stringify({ timestamp: new Date().toISOString(), outcome: "PASS", mode: "mock", records },null,2));
});
