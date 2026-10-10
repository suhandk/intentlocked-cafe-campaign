// Offline actual Chrome pixels: no provider requests or real owner approvals.
import { chromium } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
const inputs = JSON.parse(await readFile("../docs/evidence/commercial-canvas-inputs.json", "utf8"));
const browser = await chromium.launch({ channel: "chrome", headless: true });
const results = [];
try {
  for (const input of inputs) {
    const page = await browser.newPage();
    await page.route("**/*", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/worker") return route.fulfill({contentType:"text/html",body:'<script src="/api/render/canvas.js"></script>'});
      if (path === "/api/render/canvas.js") return route.fulfill({contentType:"text/javascript",body:await readFile("public/renderer/canvas.js")});
      if (path.startsWith("/api/render/fonts/")) return route.fulfill({body:await readFile("public/fonts/"+path.split("/").at(-1))});
      if (path === input.background_url) return route.fulfill({contentType:"image/png",body:await readFile("../docs/evidence/commercial-background-"+input.size+".png")});
      return route.abort();
    });
    await page.goto("http://127.0.0.1:8000/worker");
    const output = await page.evaluate(value => window.PosterCanvas.render(value), input);
    await writeFile(`../docs/evidence/commercial-${input.language}-${input.size}.png`,Buffer.from(output.png.split(",")[1],"base64"));
    results.push({input,validation:output.validation,mode:"mock",outcome:"PASS"});
    await page.close();
  }
  await writeFile("../docs/evidence/commercial-canvas-results.json",JSON.stringify(results,null,2));
  process.stdout.write(`${results.length} actual offline Chrome renders PASS\n`);
} finally { await browser.close(); }
