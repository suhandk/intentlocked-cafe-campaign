import { chromium } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";

const [inputPath, outputPath, pngPath, origin] = process.argv.slice(2);
if (!/^http:\/\/(127\.0\.0\.1|localhost):8000$/.test(origin)) throw new Error("RENDER_ORIGIN_INVALID");
const input = JSON.parse(await readFile(inputPath, "utf8"));
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: input.width, height: input.height }, deviceScaleFactor: 1 });
  const allowed = new Set(["/api/render/worker", "/api/render/canvas.js", input.background_url,
    input.logo_url, ...Object.values(input.font_urls)].filter(Boolean));
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    return url.origin === origin && allowed.has(url.pathname) && !url.search ? route.continue() : route.abort();
  });
  await page.goto(`${origin}/api/render/worker`);
  const result = await page.evaluate(async value => window.PosterCanvas.render(value), input);
  await writeFile(pngPath, Buffer.from(result.png.split(",")[1], "base64"));
  await writeFile(outputPath, JSON.stringify(result.validation));
} catch (error) {
  const code = /^[A-Z_]+$/.test(error.message) ? error.message : (error.message.match(/\b(?:FONT_TIMEOUT|FONT_UNAVAILABLE|IMAGE_UNAVAILABLE|TEXT_OVERFLOW|GRAPHEME_OVERFLOW|CANVAS_TAINTED|CROSS_ORIGIN_ASSET)\b/) || ["RENDER_FAILED"])[0];
  await writeFile(outputPath, JSON.stringify({ error: code }));
  process.exitCode = 1;
} finally { await browser.close(); }
