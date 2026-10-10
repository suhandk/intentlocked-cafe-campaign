import { test, expect } from "@playwright/test";

test.skip(process.env.WEBSITE_UI_TEST !== "isolated-mock", "Use the isolated HTTPS website verification harness");
test("website wizard resumes, keeps offer read-only, exports without token, and handles encrypted publishing", async ({ page, request }) => {
  test.setTimeout(120000);
  const token = "website-browser-credential-88cd";
  const consoleText: string[] = []; page.on("console", message => consoleText.push(message.text()));
  const urls: string[] = []; page.on("request", r => urls.push(r.url()));
  const responseBodies: string[] = [];
  page.on("response", r => { if (r.url().includes("/api/")) void r.text().then(t => responseBodies.push(t)).catch(() => undefined); });
  await page.goto("/?campaign=test-campaign");
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByRole("button", { name: "Create website", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../docs/evidence/website-create-button.png" });
  await page.getByRole("button", { name: "Create website", exact: true }).click();
  let wizard = page.getByRole("dialog", { name: "Create website", exact: true });
  await expect(wizard.getByLabel("Café name (required)")).toHaveValue("");
  await wizard.getByRole("button", { name: "6. Review", exact: true }).click();
  await expect(wizard.getByRole("button", { name: "Generate website", exact: true })).toBeDisabled();
  await wizard.getByRole("button", { name: "1. Basics", exact: true }).click();
  await wizard.getByLabel("Café name (required)").fill("Namma Cafe");
  await wizard.getByLabel("City/area (required)").fill("Bengaluru");
  await wizard.screenshot({ path: "../docs/evidence/website-wizard-basics.png" });
  await wizard.getByRole("button", { name: "Save and close", exact: true }).click();
  await expect(wizard).not.toBeVisible();
  await page.reload(); await page.getByRole("button", { name: "Create website", exact: true }).click();
  wizard = page.getByRole("dialog", { name: "Create website", exact: true });
  await expect(wizard.getByLabel("Café name (required)")).toHaveValue("Namma Cafe");
  await wizard.getByRole("button", { name: "2. Offer", exact: true }).click();
  await expect(wizard.getByText(/Read-only offer/)).toBeVisible();
  await expect(wizard.locator("input,textarea")).toHaveCount(0);
  await expect(wizard.getByRole("link", { name: "Edit in Facts Lock" })).toHaveAttribute("href", /facts-lock/);
  await wizard.getByRole("button", { name: "6. Review", exact: true }).click();
  await expect(wizard.getByText(/Website layout: OpenRouter · qwen\/qwen3-coder-flash · MOCK/)).toBeVisible();
  await wizard.getByRole("button", { name: "Generate website", exact: true }).click();
  await expect(wizard.getByText(/Bundle SHA-256/)).toBeVisible();
  await expect(wizard.getByText("DRAFT - NOT PUBLISHED", { exact: true })).toBeVisible();
  await expect(wizard.locator("iframe")).toHaveAttribute("sandbox", "");
  await expect(wizard.getByText("en: PASS", { exact: true })).toBeVisible();
  await wizard.locator("iframe").scrollIntoViewIfNeeded();
  await wizard.screenshot({ path: "../docs/evidence/website-wizard-review.png" });
  await wizard.getByRole("button", { name: "7. Publish", exact: true }).click();
  const href = await wizard.getByRole("link", { name: "Download website (zip)" }).getAttribute("href");
  const zip = await request.get(href!); expect(zip.status()).toBe(200);
  expect((await zip.body()).includes(Buffer.from(token))).toBeFalsy();
  await wizard.getByLabel("Netlify API token").fill("expired-token-example");
  await wizard.getByRole("button", { name: "Test connection", exact: true }).click();
  await expect(wizard.getByRole("alert")).toContainText("invalid or expired");
  await expect(wizard.getByLabel("Netlify API token")).toHaveValue("");
  await wizard.getByLabel("Netlify API token").fill(token);
  await wizard.getByLabel("Remember for next time (encrypted on server)").check();
  await wizard.getByRole("button", { name: "Test connection", exact: true }).click();
  await expect(wizard.getByText(/Read-only connection passed/)).toBeVisible();
  await expect(wizard.getByRole("button", { name: "Publish", exact: true })).toBeDisabled();
  await wizard.getByLabel("I approve publication of this exact website bundle").check();
  await wizard.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(wizard.getByText(/Published and live URL verified/)).toBeVisible({ timeout: 15000 });
  await wizard.getByRole("button", { name: "Disconnect / delete token", exact: true }).click();
  await expect(wizard.getByLabel("Use remembered Netlify token")).toHaveCount(0);
  const stored = await page.evaluate(() => ({ local: JSON.stringify(localStorage), session: JSON.stringify(sessionStorage), cookie: document.cookie }));
  expect(JSON.stringify(stored)).not.toContain(token);
  expect(consoleText.join("\n")).not.toContain(token);
  expect(urls.join("\n")).not.toContain(token);
  expect(responseBodies.join("\n")).not.toContain(token);
  const core = await request.get("/api/campaigns/test-campaign"); expect(core.status()).toBe(200);
  expect((await core.json()).facts.find((f: { key: string }) => f.key === "OFFER").canonical.value).toBe(20);
  await page.screenshot({ path: "../docs/evidence/website-wizard-mock.png", fullPage: true });
});

test("optional visit/menu/images render and the actual webpage stays responsive", async ({ page, request }) => {
  const draft = await (await request.get("/api/campaigns/test-campaign/website")).json();
  const png = await page.evaluate(() => { const canvas = document.createElement("canvas");
    canvas.width = 40; canvas.height = 40; canvas.getContext("2d")!.fillRect(0,0,40,40);
    return canvas.toDataURL("image/png").split(",")[1]; });
  const imageResponse = await request.post(`/api/websites/${draft.id}/images`, { data: { mime: "image/png", base64: png } });
  expect(imageResponse.status()).toBe(201); const image = await imageResponse.json();
  const saved = await (await request.put(`/api/websites/${draft.id}`, { data: {
    expected_version: draft.version, step: 5, fields: { ...draft.fields,
      description: "Hello", address: "Owner-provided address", phone: "+919876543210",
      hours: [{day:"MON",open:"09:00",close:"18:00"}], menu: [{name:"Owner menu item",price:123456.78}],
      languages: ["en","kn"], style:"warm", logo_id:image.id, photo_ids:[image.id],
      social_links:["https://example.com/owner"],
    },
  } })).json();
  const generated = await request.post(`/api/websites/${draft.id}/generate`, { data: {expected_version:saved.version} });
  expect(generated.status()).toBe(200); const bundle = await generated.json();
  expect(bundle.report.design.model).toBe("qwen/qwen3-coder-flash");
  expect(bundle.report.design.mode).toBe("MOCK");
  await page.goto(`/api/websites/${draft.id}/preview/index.html`);
  await expect(page.getByRole("heading", {name:"Namma Cafe",exact:true})).toBeVisible();
  await expect(page.getByText("Owner menu item",{exact:false})).toContainText("₹123456.78");
  await expect(page.getByText("MON: 09:00–18:00",{exact:true})).toBeVisible();
  await expect(page.getByRole("link", {name:"+919876543210",exact:true})).toHaveAttribute("href","tel:+919876543210");
  await expect(page.locator('section[lang="kn"]')).toBeVisible();
  await expect(page.locator("img")).toHaveCount(2);
  for (const image of await page.locator("img").all())
    expect(await image.evaluate((node:HTMLImageElement) => node.complete && node.naturalWidth>0)).toBe(true);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({path:"../docs/evidence/website-openrouter-page-mobile.png",fullPage:true});
  await page.setViewportSize({width:1440,height:960});
  await page.screenshot({path:"../docs/evidence/website-openrouter-page-desktop.png",fullPage:true});
});
