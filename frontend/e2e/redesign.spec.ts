import { test, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { stage, trace, closeTrace } from "./navigation";
import type { components } from "../lib/api.generated";
type Campaign=components["schemas"]["Campaign"];
const ids=["speak-type","facts-lock","brand-strategy","campaign-matrix","prediction","guardian","ledger-changes","approve-export"];
test("responsive eight-stage review, immutable modal, trace focus and saved safety",async({page,request})=>{
  test.setTimeout(240000);
  // Reuse real outputs produced by the preceding regression tests, not fixtures.
  const optimization=JSON.parse(await readFile("../docs/evidence/redesign-regression-regression-b5-browser-run.json","utf8"));
  const posters=JSON.parse(await readFile("../docs/evidence/redesign-regression-regression-b4-artifacts.json","utf8"));
  const primary:Campaign=await (await request.get(`http://127.0.0.1:8000/api/campaigns/${optimization.run.campaign_id}`)).json();
  const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await page.goto(`/?campaign=${primary.id}`);
  const observations=[];
  for(const width of [1440,820,390]) {
    await page.setViewportSize({width,height:960});
    for(const id of ids) {
      await stage(page,id);
      await expect(page.locator(".mode-pill")).toHaveText("MOCK");
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.screenshot({path:`../docs/evidence/redesign-stage-${id}-${width}.png`});
      observations.push({width,stage:id,campaign:primary.id,source:"MOCK persisted regression outputs"});
    }
    await trace(page);
    const pause=page.getByRole("button",{name:"Pause auto-scroll"});
    if(await pause.isVisible())await pause.click();
    await expect(page.getByRole("button",{name:"Resume auto-scroll"})).toBeVisible();
    await page.screenshot({path:`../docs/evidence/redesign-trace-${width}.png`});
    await page.keyboard.press("Shift+Tab");
    expect(await page.getByRole("dialog").evaluate(el=>el.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button",{name:"Open trace drawer",exact:true})).toBeFocused();
  }
  await stage(page,"ledger-changes");
  const changes=page.getByRole("region",{name:"Ledger and changes"});
  await changes.getByLabel("Owner change request",{exact:true}).fill("Make it 15%");
  await changes.getByRole("button",{name:"Propose change",exact:true}).click();
  const modal=page.getByRole("dialog",{name:"Confirm the change to locked truth"});
  await expect(modal).toBeVisible({timeout:90000});
  await expect(modal.getByRole("button",{name:"Confirm diff",exact:true})).toBeDisabled();
  await expect(modal.getByText(/Before: 20% off/)).toBeVisible();
  await expect(modal.getByText(/Proposed: 15% off/)).toBeVisible();
  for(const width of [1440,820,390]) {await page.setViewportSize({width,height:960});await page.screenshot({path:`../docs/evidence/redesign-immutable-modal-${width}.png`});}
  await modal.getByRole("button",{name:"Cancel whole proposal",exact:true}).click();
  const after=await (await request.get(`http://127.0.0.1:8000/api/campaigns/${primary.id}`)).json();
  expect(after.fact_hash).toBe(primary.fact_hash);expect(after.revision).toBe(primary.revision);
  await stage(page,"guardian");
  const redTeam=page.getByRole("region",{name:"Red-Team",exact:true});
  await redTeam.getByRole("group",{name:"Red-Team mode"}).getByRole("button",{name:"Edit the copy directly"}).click();
  await redTeam.getByLabel("Adversarial request or copy").fill("25% off coffee and free cake");
  await redTeam.getByRole("button",{name:"Run selected Red-Team mode"}).click();
  await expect(redTeam.getByRole("status")).toContainText("Guardian: BLOCKED",{timeout:90000});
  await trace(page);await page.getByRole("button",{name:"Switch explicitly to saved output"}).click();
  await expect(page.locator(".mode-pill")).toContainText("SAVED DEMO OUTPUT");await closeTrace(page);
  await stage(page,"facts-lock");await page.getByRole("group",{name:"Fact review section"}).getByRole("button",{name:"Approved wording"}).click();await expect(page.getByLabel("OFFER en nom",{exact:true})).toBeDisabled();
  await stage(page,"brand-strategy");await expect(page.getByRole("button",{name:"Generate selected matrix"})).toBeDisabled();
  await stage(page,"campaign-matrix");await page.getByRole("group",{name:"Preview channel"}).getByRole("button",{name:"WhatsApp",exact:true}).click();
  await stage(page,"approve-export");await expect(page.getByRole("button",{name:"Approve selected items"})).toBeDisabled();
  await page.screenshot({path:"../docs/evidence/redesign-saved-readonly-390.png"});
  await trace(page);await page.getByRole("button",{name:"Return to current workspace"}).click();await closeTrace(page);
  await page.emulateMedia({reducedMotion:"reduce"});await stage(page,"guardian");
  expect(await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  await expect(page.locator('.stage-view[data-stage="guardian"]').first()).toHaveCSS("opacity","1");
  // Separate Kannada artifact campaign: real PNG bytes from the poster regression.
  const kannadaId=posters.campaign?.id ?? posters.campaign_id;
  if(!kannadaId)throw new Error("Poster evidence lacks a campaign identifier");
  await page.goto(`/?campaign=${kannadaId}`);await stage(page,"campaign-matrix");
  await page.getByRole("group",{name:"Preview channel"}).getByRole("button",{name:"Poster",exact:true}).click();
  await expect(page.getByRole("region",{name:"The same pixels, from preview to file"}).locator("img").first()).toBeVisible();
  await page.screenshot({path:"../docs/evidence/redesign-kannada-posters-390.png",fullPage:true});
  expect(errors).toEqual([]);
  await writeFile("../docs/evidence/redesign-visual-review.json",JSON.stringify({timestamp:new Date().toISOString(),mode:"MOCK",observations,kannada_campaign:kannadaId,errors,focus_trap:"PASS",immutable_cancel:"facts preserved",reduced_motion:"PASS",saved_inference_and_approval:"disabled",native_review:"PENDING; no human sign-off",lighthouse:"measured separately"},null,2));
});
