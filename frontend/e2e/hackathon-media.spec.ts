import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { writeFile } from "node:fs/promises";
import { stage } from "./navigation";

test("real poster animation, approval, reload, MP4 download and website ZIP", async ({page, request}) => {
  test.setTimeout(180000);
  const api="http://127.0.0.1:8000/api";
  let campaign=await (await request.post(`${api}/campaigns`,{data:{languages:["en"],channels:["whatsapp"]}})).json();
  const base=`${api}/campaigns/${campaign.id}`;
  campaign=await (await request.post(`${base}/intent`,{data:{expected_revision:campaign.revision,
    transcript:"Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend. Open to all."}})).json();
  campaign=await (await request.post(`${base}/facts/surface`,{data:{expected_revision:campaign.revision,confirm_canonical:true}})).json();
  campaign=await (await request.post(`${base}/facts/lock`,{data:{expected_revision:campaign.revision,
    idempotency_key:crypto.randomUUID(),reviewed_fact_versions:Object.fromEntries(campaign.facts.map((f:{key:string;version:number})=>[f.key,f.version])),
    forms:campaign.facts.filter((f:{canonical:unknown})=>f.canonical).map((f:{key:string;surface:unknown})=>({key:f.key,surface:f.surface})),
    approve_canonical_and_forms:true,acknowledged_warning_ids:campaign.warnings.map((w:{id:string})=>w.id)}})).json();
  expect(campaign.status).toBe("locked");
  const strategy=await (await request.post(`${base}/strategy`,{data:{expected_revision:campaign.revision}})).json();
  expect((await request.post(`${base}/generate`,{data:{expected_revision:campaign.revision,strategy_id:strategy.id,
    audience_ids:[strategy.audiences[0].id],languages:["en"],channels:["whatsapp"],idempotency_key:crypto.randomUUID()}})).status()).toBe(202);
  await expect.poll(async()=> (await (await request.get(`${base}/matrix`)).json()).run?.status,{timeout:30000}).toBe("completed");
  const matrix=await (await request.get(`${base}/matrix`)).json();
  const variant=matrix.run.cells[0].variant;
  const background=await (await request.post(`${base}/backgrounds`,{data:{expected_revision:campaign.revision,size:"story",source:"deterministic"}})).json();
  const rendered=await request.post(`${base}/assets/render`,{data:{expected_revision:campaign.revision,size:"story",variant_id:variant.id,background_id:background.id}});
  expect(rendered.ok()).toBeTruthy();const poster=await rendered.json();
  const squareBackground=await (await request.post(`${base}/backgrounds`,{data:{expected_revision:campaign.revision,size:"square",source:"deterministic"}})).json();
  const squareResponse=await request.post(`${base}/assets/render`,{data:{expected_revision:campaign.revision,size:"square",variant_id:variant.id,background_id:squareBackground.id}});
  expect(squareResponse.ok()).toBeTruthy();const square=await squareResponse.json();
  expect(square.render_input.renderer_version).toBe("canvas-modern-cafe-b1.0");
  expect(squareBackground.provenance).toBe("deterministic");
  await writeFile("../docs/evidence/modern-cafe-local-square.png",await (await request.get(`${api}/assets/${square.id}`)).body());
  await writeFile("../docs/evidence/modern-cafe-local-preview.json",JSON.stringify({mode:"MOCK",background:"deterministic local illustration",renderer:square.render_input.renderer_version,approval:"UNAPPROVED",reference_claims_copied:false,poster:square},null,2));
  await page.goto(`/?campaign=${campaign.id}`);await stage(page,"campaign-matrix");
  await page.getByRole("button",{name:"Saved video drafts",exact:true}).click();
  const panel=page.getByRole("region",{name:"Optional video drafts"});
  await expect(panel.getByRole("button",{name:"Create animated MP4"})).toBeEnabled();
  let submissions=0;
  page.on("request",r=>{if(r.method()==="POST"&&r.url().endsWith("/work")&&r.postDataJSON().kind==="local_video")submissions++;});
  await panel.getByRole("button",{name:"Create animated MP4"}).evaluate(button=>{(button as HTMLButtonElement).click();(button as HTMLButtonElement).click();});
  await expect(panel.getByRole("link",{name:"Download unapproved draft"})).toBeVisible({timeout:60000});
  expect(submissions).toBe(1);
  let videos=await (await request.get(`${base}/videos`)).json();
  const video=videos[0];expect(video.source).toBe("local_animation");expect(video.approval).toBe("UNAPPROVED");
  const raw=await (await request.get(`${api}/videos/${video.id}/draft.mp4`)).body();
  expect(raw.length).toBeGreaterThan(5000);expect(raw.subarray(4,8).toString()).toBe("ftyp");
  expect(createHash("sha256").update(raw).digest("hex")).toBe(video.sha256);
  expect((await request.get(`${api}/videos/${video.id}/approved.mp4`)).ok()).toBeFalsy();
  const delivery=await (await request.get(`${base}/delivery`)).json();
  const item=delivery.items.find((i:{poster_id:string})=>i.poster_id===poster.id);
  const audit=await (await request.post(`${base}/delivery/${item.id}/audit`,{data:{expected_revision:campaign.revision}})).json();
  expect(audit.status).toBe("PASS");
  const approved=await request.post(`${base}/approve`,{data:{expected_revision:campaign.revision,item_ids:[item.id],
    observed_hashes:{[item.id]:item.snapshot_hash},acknowledged_warning_ids:audit.warning_ids,
    owner_approves:true,idempotency_key:crypto.randomUUID()}});
  expect(approved.ok()).toBeTruthy();
  await panel.getByLabel("I reviewed this exact animation and approve its export.").check();
  await panel.getByRole("button",{name:"Approve animation",exact:true}).click();
  await expect(panel.getByRole("link",{name:"Download approved MP4"})).toBeVisible();
  const manifest=await (await request.get(`${api}/videos/${video.id}/manifest`)).json();
  expect(manifest.source_provenance).toBe("mock");expect(manifest.approved_hash).toBe(video.sha256);
  expect((await request.get(`${api}/videos/${video.id}/approved.mp4`)).status()).toBe(200);
  await writeFile("../docs/evidence/hackathon-MOCK-poster-animation.mp4",raw);
  await panel.locator("video").evaluate(async node=>{const video=node as HTMLVideoElement;await new Promise<void>((resolve,reject)=>{if(video.readyState>=1){resolve();return;}video.addEventListener("loadedmetadata",()=>resolve(),{once:true});video.addEventListener("error",()=>reject(new Error("MP4 failed playback")),{once:true});});await new Promise<void>(resolve=>{video.addEventListener("seeked",()=>resolve(),{once:true});video.currentTime=5;});});
  await panel.screenshot({path:"../docs/evidence/hackathon-local-animation.png"});
  await page.reload();await stage(page,"campaign-matrix");
  await page.getByRole("button",{name:"Saved video drafts",exact:true}).click();
  await expect(panel.getByRole("link",{name:"Download approved MP4"})).toBeVisible();

  await page.getByRole("button",{name:"Create website",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await expect(dialog.getByText("Draft saved",{exact:true})).toBeVisible();
  await dialog.getByLabel("Café name (required)").fill("Namma Cafe");
  await dialog.getByLabel("City/area (required)").fill("Bengaluru");
  await dialog.getByRole("button",{name:"3. Visit info",exact:true}).click();
  await dialog.getByLabel("Add opening day").selectOption("MON");
  await expect(dialog.getByRole("status")).toContainText("Edits not saved yet");
  await dialog.getByLabel("open",{exact:true}).fill("09:00");
  await expect(dialog.getByRole("status")).toContainText("Edits not saved yet");
  await dialog.getByLabel("close",{exact:true}).fill("18:00");
  await expect(dialog.getByRole("status")).toHaveText("Draft saved");
  await dialog.getByRole("button",{name:"4. Menu",exact:true}).click();
  await dialog.getByRole("button",{name:"Add menu row",exact:true}).click();
  await expect(dialog.getByRole("status")).toContainText("Edits not saved yet");
  await dialog.getByLabel("Menu item 1",{exact:true}).fill("Coffee");
  await dialog.getByLabel("Price 1",{exact:true}).fill("100");
  await expect(dialog.getByRole("status")).toHaveText("Draft saved");
  await dialog.getByRole("button",{name:"6. Review",exact:true}).click();
  await dialog.getByRole("button",{name:"Generate website",exact:true}).click();
  await expect(dialog.getByTitle("DRAFT - NOT PUBLISHED website preview")).toBeVisible();
  await dialog.getByRole("button",{name:"Next",exact:true}).click();
  const link=dialog.getByRole("link",{name:"Download website (zip)"});await expect(link).toBeVisible();
  const zip=await (await request.get("http://127.0.0.1:3000"+await link.getAttribute("href"))).body();
  expect(zip.subarray(0,2).toString()).toBe("PK");
  await writeFile("../docs/evidence/hackathon-MOCK-website.zip",zip);
  await dialog.screenshot({path:"../docs/evidence/hackathon-website-download.png"});
  videos=await (await request.get(`${base}/videos`)).json();expect(videos).toHaveLength(1);
  await writeFile("../docs/evidence/hackathon-media-browser.json",JSON.stringify({timestamp:new Date().toISOString(),
    mode:"MOCK",source:"Mock inference; real Chrome poster rendering and real FFmpeg animation",
    result:"PASS",video_bytes:raw.length,video_sha256:video.sha256,video_approval:"SIMULATED_TEST_OPERATOR",
    website_zip_bytes:zip.length,rapid_clicks:"one job",reload:"PASS",live_image:"NOT_TESTED"},null,2));
});
