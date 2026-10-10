// Offline Chrome verification: every browser request is fulfilled from local fixtures.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { chromium } from "@playwright/test";

const root = new URL("../../", import.meta.url);
const fixtures = JSON.parse(await readFile(new URL("docs/evidence/pinterest-inputs.json", root), "utf8"));
const resources = new Map([
  ["/", ["text/html", Buffer.from('<!doctype html><script src="/canvas.js"></script>')]],
  ["/canvas.js", ["text/javascript", await readFile(new URL("frontend/public/renderer/canvas.js", root))]],
  ["/api/render/fonts/NotoSans.ttf", ["font/ttf", await readFile(new URL("frontend/public/fonts/NotoSans.ttf", root))]],
  ["/api/render/fonts/NotoSansKannada.ttf", ["font/ttf", await readFile(new URL("frontend/public/fonts/NotoSansKannada.ttf", root))]],
]);
for (const size of ["square", "story", "landscape"])
  resources.set(`/api/assets/editorial-${size}`, ["image/png", await readFile(new URL(`docs/evidence/pinterest-art-${size}.png`, root))]);
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage();
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    const resource = url.origin === "http://127.0.0.1:8003" && !url.search ? resources.get(url.pathname) : null;
    return resource ? route.fulfill({ contentType: resource[0], body: resource[1] }) : route.abort();
  });
  const results = [];
  for (const input of fixtures) {
    await page.goto("http://127.0.0.1:8003/");
    const result = await page.evaluate(value => window.PosterCanvas.render(value), input);
    assert.equal(result.validation.passed, true);
    assert.ok(result.validation.contrast >= 7);
    for (const [field, text] of Object.entries(input.fields)) {
      if (field === "alt_text") continue;
      assert.equal(result.validation.lines.filter(line => line.field === field).map(line => line.text).join(""), text.replaceAll("\n", ""));
    }
    const name = `pinterest-${input.size}-${input.language}`;
    await writeFile(new URL(`docs/evidence/${name}.png`, root), Buffer.from(result.png.split(",")[1], "base64"));
    results.push({ name, validation: result.validation });
  }
  const sample = fixtures[0];
  await assert.rejects(page.evaluate(value => window.PosterCanvas.render({ ...value, background_url: "https://example.com/image.png" }), sample), /CROSS_ORIGIN_ASSET/);
  await assert.rejects(page.evaluate(value => window.PosterCanvas.render({ ...value, fields: { ...value.fields, body: "Very long copy ".repeat(1000) } }), sample), /TEXT_OVERFLOW/);
  await assert.rejects(page.evaluate(value => window.PosterCanvas.render({ ...value, renderer_version: "canvas-b5.2" }), sample), /LAYOUT_INVALID/);
  await writeFile(new URL("docs/evidence/pinterest-canvas.json", root), JSON.stringify({ mode: "offline-local", results, external_url_block: "PASS", overflow_block: "PASS", old_renderer_block: "PASS" }, null, 2));
  console.log(`${results.length} actual Chrome renders PASS; remote assets, overflow and obsolete renderer blocked.`);
} finally {
  await browser.close();
}
