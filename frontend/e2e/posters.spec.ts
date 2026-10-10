import { stage } from "./navigation";
import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import type { components } from "../lib/api.generated";
type Campaign = components["schemas"]["Campaign"];
type Matrix = components["schemas"]["MatrixSnapshot"];
type Poster = components["schemas"]["PosterArtifact"];
type CanvasInput = components["schemas"]["CanvasInput"];
type Size = components["schemas"]["RenderRequest"]["size"];
type CanvasResult = { png: string; validation: components["schemas"]["CanvasValidation"] };
declare global { interface Window { PosterCanvas: { render(input: CanvasInput, options?: { fontTimeout?: number }): Promise<CanvasResult> } } }

const base = "http://127.0.0.1:8000/api";
let campaign: Campaign;
let matrix: Matrix;
let posters: Poster[];
const dimensions: [Size, number, number][] = [["square", 1080, 1080], ["story", 1080, 1920], ["landscape", 1200, 630]];
test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => {
  test.setTimeout(90000);
  let response = await request.post(`${base}/campaigns`, { data: { languages: ["kn"], channels: ["whatsapp"] } });
  expect(response.status()).toBe(201); campaign = await response.json();
  const path = `${base}/campaigns/${campaign.id}`;
  response = await request.post(`${path}/intent`, { data: { expected_revision: campaign.revision,
    transcript: "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all." } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${path}/facts/surface`, { data: { expected_revision: campaign.revision, confirm_canonical: true } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${path}/facts/lock`, { data: {
    expected_revision: campaign.revision, idempotency_key: `poster-${campaign.id}`,
    reviewed_fact_versions: Object.fromEntries(campaign.facts.map(f => [f.key, f.version])),
    forms: campaign.facts.filter(f => f.canonical).map(f => ({ key: f.key, surface: f.surface })),
    approve_canonical_and_forms: true, acknowledged_warning_ids: campaign.warnings.map(w => w.id),
  } });
  expect(response.ok()).toBeTruthy(); campaign = await response.json();
  response = await request.post(`${path}/strategy`, { data: { expected_revision: campaign.revision } });
  expect(response.ok()).toBeTruthy(); const strategy = await response.json();
  response = await request.post(`${path}/generate`, { data: { expected_revision: campaign.revision,
    strategy_id: strategy.id, audience_ids: strategy.audiences.map((a: { id: string }) => a.id),
    languages: ["kn"], channels: ["whatsapp"], idempotency_key: `postercopy-${campaign.id}` } });
  expect(response.status()).toBe(202);
  await expect.poll(async () => (await (await request.get(`${path}/matrix`)).json()).run?.status, { timeout: 30000 }).toBe("completed");
  matrix = await (await request.get(`${path}/matrix`)).json();
});

test("actual persisted poster bytes at all sizes, UI preview identity and reuse", async ({ page, request }) => {
  test.setTimeout(150000);
  await page.goto(`/?campaign=${campaign.id}`);
  await stage(page,"campaign-matrix");
  await page.getByRole("group",{name:"Preview channel"}).getByRole("button",{name:"Poster",exact:true}).click();
  const panel = page.getByRole("region", { name: "The same pixels, from preview to file" });
  // Select the exact sizes exercised here; the UI also defaults to a 4:5 feed option.
  await panel.getByRole("button", { name: "1080 × 1350 · Instagram 4:5", exact: true }).click();
  await panel.getByRole("button", { name: "1200 × 630", exact: true }).click();
  await expect(panel.getByRole("button", { name: "Render selected poster sizes" })).toBeEnabled();
  await panel.getByRole("button", { name: "Render selected poster sizes" }).click();
  await expect(panel.getByRole("link", { name: "Download draft PNG" })).toHaveCount(3, { timeout: 90000 });
  await expect(panel.getByRole("button", { name: "Render selected poster sizes" })).toBeEnabled();
  const assets = await (await request.get(`${base}/campaigns/${campaign.id}/assets`)).json();
  posters = assets.posters;
  expect(assets.backgrounds).toHaveLength(3);
  expect(assets.backgrounds.every((a: { provenance: string; status: string }) => a.provenance === "mock" && a.status === "ready")).toBeTruthy();
  expect(posters).toHaveLength(3);
  await mkdir("../docs/evidence", { recursive: true });
  for (const [size, width, height] of dimensions) {
    const poster = posters.find(p => p.render_input.size === size)!;
    expect([poster.width, poster.height]).toEqual([width, height]);
    expect(poster.validation.font_loaded).toBe(true);
    expect(poster.validation.contrast).toBeGreaterThanOrEqual(7);
    expect(poster.approval_ready).toBe(false);
    const imageResponse = await request.get(`${base}/assets/${poster.id}`);
    const bytes = await imageResponse.body();
    expect(imageResponse.headers()["content-type"]).toContain("image/png");
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(poster.sha256);
    expect(bytes.readUInt32BE(16)).toBe(width); expect(bytes.readUInt32BE(20)).toBe(height);
    await writeFile(`../docs/evidence/redesign-regression-regression-b4-poster-${size}.png`, bytes);
    const image = panel.locator(`img[src="/api/assets/${poster.id}"]`);
    await expect(image).toBeVisible();
    expect(await image.evaluate((el: HTMLImageElement) => [el.naturalWidth, el.naturalHeight])).toEqual([width, height]);
    expect(await image.evaluate(async (el: HTMLImageElement) => {
      const canvas = document.createElement("canvas"); canvas.width = el.naturalWidth; canvas.height = el.naturalHeight;
      canvas.getContext("2d")!.drawImage(el, 0, 0); return canvas.toDataURL("image/png").startsWith("data:image/png");
    })).toBe(true); // same-origin proxy never taints canvas.
  }
  const before = await (await request.get(`${base}/cost`)).json();
  const other = matrix.run!.cells[1].variant!;
  for (const poster of posters) {
    const response = await request.post(`${base}/campaigns/${campaign.id}/assets/render`, { data: {
      expected_revision: campaign.revision, variant_id: other.id, size: poster.render_input.size, background_id: poster.background_id,
    } });
    expect(response.ok()).toBeTruthy();
  }
  expect((await (await request.get(`${base}/cost`)).json()).calls).toBe(before.calls);
  await page.reload(); await expect(panel.getByRole("link", { name: "Download draft PNG" })).toHaveCount(3);
  await panel.screenshot({ path: "../docs/evidence/redesign-regression-regression-b4-posters-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await panel.screenshot({ path: "../docs/evidence/redesign-regression-regression-b4-posters-mobile.png" });
  await writeFile("../docs/evidence/redesign-regression-regression-b4-artifacts.json", JSON.stringify({ mode: "mock", native_review: "PENDING", campaign_id: campaign.id, posters }, null, 2));
});

test("grapheme wrapping preserves long Kannada and offer forms in actual PNGs", async ({ page }) => {
  test.setTimeout(60000);
  await page.goto("http://127.0.0.1:8000/api/render/worker");
  for (const offer of ["20% ರಿಯಾಯಿತಿ", "೨೫% ರಿಯಾಯಿತಿ", "ಇಪ್ಪತ್ತೈದು ಶೇಕಡಾ ರಿಯಾಯಿತಿ", "₹50 ರಿಯಾಯಿತಿ", "1 ಕೊಂಡರೆ 1 ಉಚಿತ", "Rs 50 off", "buy 1 get 1 free"]) {
    const input = structuredClone(posters[0].render_input);
    input.fields = { headline: "ನಿಮ್ಮದೇ ಪುಟ್ಟ ವಿರಾಮ", body: "ನಮ್ಮ ಕನ್ನಡ ಕಾಫಿ ಮತ್ತು ಮಾತುಕತೆಯ ಸುಂದರ ನೆನಪುಗಳ ಕೆಫೆ ".repeat(3) + `\n${offer}\nಕಾಫಿ · ಬೆಂಗಳೂರು · ಶನಿವಾರ / ಭಾನುವಾರ · 2026-10-10 – 2026-10-11`, cta: "ಬನ್ನಿ, ಜೊತೆಯಾಗೋಣ!", alt_text: "Explicit renderer test example" };
    const result = await page.evaluate(value => window.PosterCanvas.render(value), input);
    expect(result.validation.passed).toBe(true);
    const lines = result.validation.lines.filter(line => line.field === "body");
    expect(lines.map(line => line.text).join("")).toBe(input.fields.body.replaceAll("\n", ""));
    expect(lines.every(line => line.width <= 952 && line.font_size >= 26)).toBe(true);
    if (offer === "ಇಪ್ಪತ್ತೈದು ಶೇಕಡಾ ರಿಯಾಯಿತಿ") {
      await writeFile("../docs/evidence/redesign-regression-regression-b4-long-kannada.png", Buffer.from(result.png.split(",")[1], "base64"));
      await page.screenshot({ path: "../docs/evidence/redesign-regression-regression-b4-long-kannada-browser.png", fullPage: true });
    }
  }
  const input = structuredClone(posters.find(p => p.render_input.size === "landscape")!.render_input);
  input.fields.body = "ಕನ್ನಡದ ಬಹಳ ಉದ್ದವಾದ ಮಾತುಕತೆ ಮತ್ತು ವಿರಾಮ ".repeat(200);
  await expect(page.evaluate(value => window.PosterCanvas.render(value), input)).rejects.toThrow("TEXT_OVERFLOW");
});

test("slow font waits, missing font blocks and cross-origin URLs are rejected", async ({ page }) => {
  test.setTimeout(60000);
  await page.route("**/NotoSansKannada.ttf", async route => {
    await new Promise(resolve => setTimeout(resolve, 300)); await route.continue();
  });
  await page.goto("http://127.0.0.1:8000/api/render/worker");
  const input = posters[0].render_input;
  expect((await page.evaluate(value => window.PosterCanvas.render(value, { fontTimeout: 3000 }), input)).validation.font_loaded).toBe(true);
  await page.unroute("**/NotoSansKannada.ttf");
  await page.route("**/NotoSansKannada.ttf", route => route.abort());
  await page.reload();
  await expect(page.evaluate(value => window.PosterCanvas.render(value), input)).rejects.toThrow("FONT_UNAVAILABLE");
  await page.unroute("**/NotoSansKannada.ttf");
  await page.route("**/NotoSansKannada.ttf", async route => {
    await new Promise(resolve => setTimeout(resolve, 300)); await route.continue();
  });
  await page.reload();
  await expect(page.evaluate(value => window.PosterCanvas.render(value, { fontTimeout: 20 }), input)).rejects.toThrow("FONT_TIMEOUT");
  await page.unroute("**/NotoSansKannada.ttf"); await page.reload();
  await expect(page.evaluate(value => window.PosterCanvas.render({ ...value, background_url: "https://evil.test/a.png" }), input)).rejects.toThrow("CROSS_ORIGIN_ASSET");
});

test("reviewed PNG logo is placed inside safe areas; missing and SVG logos block", async ({ page, request }) => {
  test.setTimeout(30000);
  await page.goto(`/?campaign=${campaign.id}`);
  await stage(page,"campaign-matrix");
  await page.getByRole("group",{name:"Preview channel"}).getByRole("button",{name:"Poster",exact:true}).click();
  const panel = page.getByRole("region", { name: "The same pixels, from preview to file" });
  await panel.getByText("Use your reviewed PNG logo", { exact: true }).click();
  const encoded = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 80; canvas.height = 80;
    const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#E8EECE"; ctx.beginPath(); ctx.arc(40, 40, 36, 0, Math.PI * 2); ctx.fill();
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await panel.getByLabel("Logo PNG · maximum 2MB").setInputFiles({ name: "reviewed-test-logo.png", mimeType: "image/png", buffer: Buffer.from(encoded, "base64") });
  await panel.getByRole("checkbox", { name: "I reviewed this logo and approve its exact content for this business." }).check();
  await panel.getByRole("button", { name: "Store reviewed logo" }).click();
  await expect(panel.getByRole("combobox", { name: "Approved logo", exact: true })).not.toHaveValue("");
  const assets = await (await request.get(`${base}/campaigns/${campaign.id}/assets`)).json();
  const first = posters.find(p => p.render_input.size === "square")!;
  const payload = { expected_revision: campaign.revision, variant_id: first.variant_id, size: "square", background_id: first.background_id };
  let response = await request.post(`${base}/campaigns/${campaign.id}/assets/render`, { data: { ...payload, logo_id: assets.logos[0] } });
  expect(response.ok()).toBeTruthy(); const poster: Poster = await response.json();
  const [x,y,w,h] = poster.validation.logo_bounds!;
  const [sx,sy,sw,sh] = poster.validation.safe_area;
  expect(w).toBeGreaterThan(0); expect(h).toBeGreaterThan(0);
  expect(x).toBeGreaterThanOrEqual(sx); expect(y).toBeGreaterThanOrEqual(sy);
  expect(x+w).toBeLessThanOrEqual(sx+sw); expect(y+h).toBeLessThanOrEqual(sy+sh);
  expect(Math.abs(x-sx)).toBeLessThan(1);
  expect(poster.validation.lines.find(line=>line.field==="headline")!.x).toBe(x);
  const bytes = await (await request.get(`${base}/assets/${poster.id}`)).body();
  await writeFile("../docs/evidence/redesign-regression-regression-b4-logo-square.png", bytes);
  response = await request.post(`${base}/campaigns/${campaign.id}/assets/render`, { data: { ...payload, logo_id: "missing" } });
  expect(response.status()).toBe(404);
  response = await request.post(`${base}/campaigns/${campaign.id}/logos?expected_revision=${campaign.revision}&owner_approves_logo=true`, {
    data: '<svg onload="alert(1)"></svg>', headers: { "Content-Type": "image/svg+xml" },
  });
  expect(response.status()).toBe(422);
});

test("4:5 feed poster preserves exact PNG bytes and reuses approved square art", async ({ request }) => {
  const square = posters.find(p => p.render_input.size === "square")!;
  const before = await (await request.get(`${base}/cost`)).json();
  const response = await request.post(`${base}/campaigns/${campaign.id}/assets/render`, { data: {
    expected_revision: campaign.revision, variant_id: square.variant_id,
    size: "feed", background_id: square.background_id,
  } });
  expect(response.ok()).toBeTruthy(); const poster: Poster = await response.json();
  expect([poster.width, poster.height]).toEqual([1080, 1350]);
  expect(poster.validation.passed).toBe(true); expect(poster.validation.font_loaded).toBe(true);
  const raw = await (await request.get(`${base}/assets/${poster.id}`)).body();
  expect([raw.readUInt32BE(16), raw.readUInt32BE(20)]).toEqual([1080, 1350]);
  expect(createHash("sha256").update(raw).digest("hex")).toBe(poster.sha256);
  expect((await (await request.get(`${base}/cost`)).json()).image_outputs).toBe(before.image_outputs);
  await writeFile("../docs/evidence/workflow-debug-poster-feed.png", raw);
});
