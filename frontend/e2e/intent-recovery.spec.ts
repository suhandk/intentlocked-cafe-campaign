import {test, expect} from "@playwright/test";
import {readFile} from "node:fs/promises";

const brief = "Café name: Namma Cafe. Bengaluru. 20% off coffee this weekend. Open to all.";

for (const manual of [false, true]) {
  test(`intent failure preserves the brief and supports ${manual ? "manual fact entry" : "an explicit edited retry"}`, async ({page}) => {
    const fixture = JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json", "utf8"));
    const campaign = structuredClone(fixture.campaign);
    Object.assign(campaign, {revision:1, status:"draft", fact_hash:null, approved_at:null, transcript:"", agent_questions:[], warnings:[], acknowledged_warning_ids:[]});
    campaign.facts = campaign.facts.map((fact:Record<string,unknown>) => ({...fact, canonical:null, surface:{}, status:"not_specified", source:"unspecified", source_span:null, approved_at:null, approval_id:null}));
    let intentCalls = 0, manualSaves = 0;
    const keys: string[] = [];
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      let body:unknown;
      if (path.includes("/stream/")) return route.fulfill({contentType:"text/event-stream", body:": offline mock\n\n"});
      if (path.endsWith("/ready")) body = fixture.health;
      else if (path.endsWith("/cost")) body = fixture.cost;
      else if (path.endsWith("/traces")) body = [];
      else if (path.endsWith(`/campaigns/${campaign.id}`)) body = campaign;
      else if (path.endsWith("/work") && route.request().method() === "POST") {
        const request = route.request().postDataJSON();
        expect(request.kind).toBe("intent");
        expect(request.input.expected_revision).toBe(1);
        keys.push(request.idempotency_key); intentCalls++;
        if (intentCalls === 1) body = {id:"failed-intent-check", kind:"intent", status:"failed", error_code:"INTENT_UNAVAILABLE", result:null};
        else {
          expect(request.input.transcript).toBe(brief + " ID required.");
          Object.assign(campaign, {revision:2, transcript:request.input.transcript});
          body = {id:"retried-intent-check", kind:"intent", status:"completed", result:campaign};
        }
      } else if (path.endsWith("/facts/draft") && route.request().method() === "PUT") {
        const request = route.request().postDataJSON();
        expect(request.expected_revision).toBe(1);
        expect(request.transcript).toBe(brief);
        expect(request.facts.every((fact:Record<string,unknown>)=>fact.canonical === null)).toBeTruthy();
        manualSaves++; Object.assign(campaign, {revision:2, transcript:request.transcript});
        body = campaign;
      } else if (path.endsWith("/work")) body = {jobs:[], active:0, queued:0, concurrency_limit:2, mode:"mock", latest_event_id:0};
      else return route.fulfill({status:404, json:{message:"Offline fixture route unavailable"}});
      return route.fulfill({json:body});
    });
    await page.goto(`/?campaign=${campaign.id}#speak-type`);
    const workspace = page.getByRole("region", {name:"Campaign workspace"});
    const transcript = page.getByLabel("Your brief · review the transcript");
    await transcript.fill(brief);
    await page.getByRole("button", {name:"Propose facts from transcript", exact:true}).click();
    await expect(workspace.getByRole("alert")).toContainText("The model could not interpret this brief");
    await expect(transcript).toHaveValue(brief);
    await expect(transcript).toBeEnabled();
    expect(intentCalls).toBe(1);
    if (manual) {
      await page.getByRole("button", {name:"Enter facts manually", exact:true}).click();
      await expect(page.getByText("Brief saved for manual entry.", {exact:false})).toBeVisible();
      await expect(page.getByRole("button", {name:"Save editable facts", exact:true})).toBeEnabled();
      await page.getByLabel("Café name", {exact:true}).fill("Owner-entered Café");
      await expect(page.getByRole("button", {name:"Save editable facts", exact:true})).toBeEnabled();
      expect(manualSaves).toBe(1);
      expect(intentCalls).toBe(1);
      await page.reload();
      await page.getByRole("button", {name:/Speak/}).click();
      await expect(transcript).toHaveValue(brief);
    } else {
      await transcript.fill(brief + " ID required.");
      await page.getByRole("button", {name:"Retry this brief", exact:true}).click();
      await expect(page.getByLabel("Café name", {exact:true})).toBeVisible();
      expect(intentCalls).toBe(2);
      expect(new Set(keys).size).toBe(2);
      expect(manualSaves).toBe(0);
    }
    await expect(workspace.getByRole("alert")).toHaveCount(0);
    await expect(page.getByText("Locked by owner", {exact:false})).toHaveCount(0);
    expect(campaign.status).toBe("draft");
  });
}
