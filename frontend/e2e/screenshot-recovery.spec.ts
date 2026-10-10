import {test, expect} from "@playwright/test";
import {readFile} from "node:fs/promises";

async function fixture() {
  return JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json", "utf8"));
}

test("blocked copy explains poster and score dependencies; explicit retry preserves selection", async ({page})=>{
  const data=await fixture();
  let matrix=structuredClone(data.matrix);
  const failedId=matrix.run.id;
  matrix.run.status="failed"; matrix.run.error_code="COPY_VALIDATION_FAILED";
  matrix.run.cells[0].state="blocked"; matrix.run.cells[0].reasons=["G05","G08"];
  matrix.run.cells[0].variant.status="blocked"; matrix.run.cells[0].variant.report.status="BLOCKED";
  let retries=0, videoRequests=0;
  await page.route("**/api/**", async route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown;
    if(path.endsWith("/work") && route.request().method()==="POST") {
      const request=route.request().postDataJSON();
      if(request.kind==="video") videoRequests++;
      expect(request.kind).toBe("generate");
      expect(request.input.retry_source_run_id).toBe(failedId);
      expect(request.input.expected_revision).toBe(data.campaign.revision);
      expect(request.input.audience_ids).toEqual(data.matrix.run.request.audience_ids);
      expect(request.input.channels).toEqual(data.matrix.run.request.channels);
      retries++;
      matrix=structuredClone(data.matrix); matrix.run.id="explicit-copy-retry";
      body={id:"copy-retry-job",status:"completed",kind:"generate",result:matrix.run};
    } else if(path.includes("/stream/")) return route.fulfill({contentType:"text/event-stream",body:": mock\n\n"});
    else if(path.endsWith("/ready")) body={...data.health,image_generation_enabled:false};
    else if(path.endsWith("/cost")) body=data.cost;
    else if(path.endsWith("/traces")) body=[];
    else if(path.endsWith("/campaigns/"+data.campaign.id)) body=data.campaign;
    else if(path.endsWith("/matrix")) body=matrix;
    else if(path.endsWith("/delivery")) body=data.before;
    else if(path.endsWith("/optimization")) body={runs:[],unscored_variant_ids:[]};
    else if(path.endsWith("/assets")) body={backgrounds:[],posters:[],logos:[]};
    else if(path.endsWith("/video/config")) body={enabled:false,model:"disabled",mode:"mock"};
    else if(path.endsWith("/videos")) body=[];
    else if(path.endsWith("/work")) body={jobs:Array.from({length:5},(_,i)=>({id:`old-video-${i}`,campaign_id:data.campaign.id,campaign_revision:data.campaign.revision,kind:"video",status:"failed",mode:"mock",created_at:"2026-10-10T00:00:00Z",updated_at:"2026-10-10T00:00:00Z",deadline:"2026-10-10T00:08:00Z",error_code:"VIDEO_VALIDATOR_MISSING",elapsed_seconds:0,completed_steps:0,max_steps:6,calls:0,max_calls:48,list_price_estimate_usd:0,unknown_cost_calls:0,queue_position:0,estimated_wait_seconds:0,notices:[]})),active:0,queued:0,concurrency_limit:2,latest_event_id:0,mode:"mock"};
    else return route.fulfill({status:404,json:{message:"Offline fixture route unavailable"}});
    return route.fulfill({json:body});
  });
  await page.goto(`/?campaign=${data.campaign.id}#prediction`);
  const prediction=page.locator("section[aria-labelledby=prediction-heading]");
  await expect(prediction.getByRole("button",{name:"Optimize hero group"})).toBeDisabled();
  await expect(prediction).toContainText("Required business facts or conditions are missing");
  await prediction.getByRole("button",{name:"Review campaign copy"}).click();
  const campaign=page.locator("div#campaign-matrix");
  await expect(campaign.getByRole("button",{name:"Retry unfinished copy"})).toBeVisible();
  await campaign.getByRole("button",{name:"Poster",exact:true}).click();
  const poster=page.locator("section[aria-labelledby=poster-heading]");
  await expect(poster).toContainText("No validated copy drafts");
  await expect(poster.getByRole("button",{name:"Render selected poster sizes"})).toBeDisabled();
  await poster.getByRole("button",{name:"Review campaign copy"}).click();
  await campaign.getByRole("button",{name:"Retry unfinished copy"}).click();
  await expect(campaign).toContainText("1/1 drafts ready");
  expect(retries).toBe(1);
  await campaign.getByRole("button",{name:"Poster",exact:true}).click();
  await expect(poster.getByRole("button",{name:"Render selected poster sizes"})).toBeDisabled();
  await poster.getByLabel("Background source").selectOption("deterministic");
  await expect(poster.getByRole("button",{name:"Render selected poster sizes"})).toBeEnabled();
  await campaign.getByRole("button",{name:"Saved video drafts",exact:true}).click();
  const video=page.getByRole("region",{name:"Optional video drafts"});
  await expect(video.getByRole("button",{name:"Video generation unavailable"})).toBeDisabled();
  await expect(video.getByText("Previous video requests · 5 stopped")).toBeVisible();
  await expect(video.getByLabel("Video duration")).toHaveCount(0);
  expect(videoRequests).toBe(0);
});

test("a ready non-hero audience is explicitly selected and sent as its own group",async({page})=>{
  const data=await fixture();
  const matrix=structuredClone(data.matrix);
  const plan=matrix.strategy;
  const other=structuredClone(plan.audiences[0]); other.id="explicit-other"; other.name="Other selected audience";
  plan.audiences.push(other);
  matrix.run.request.audience_ids=[other.id];
  matrix.run.cells[0].audience_id=other.id; matrix.run.cells[0].variant.audience_id=other.id;
  let optimizations=0;
  await page.route("**/api/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown;
    if(path.endsWith("/work") && route.request().method()==="POST") {
      const request=route.request().postDataJSON();
      expect(request.kind).toBe("optimize");
      expect(request.input.variant_ids).toEqual([matrix.run.cells[0].variant.id]);
      optimizations++;body={id:"non-hero-job",status:"completed",kind:"optimize",result:{id:"non-hero-run",status:"completed"}};
    } else if(path.includes("/stream/")) return route.fulfill({contentType:"text/event-stream",body:": mock\n\n"});
    else if(path.endsWith("/ready")) body={...data.health,image_generation_enabled:false};
    else if(path.endsWith("/cost")) body=data.cost;
    else if(path.endsWith("/traces")) body=[];
    else if(path.endsWith("/campaigns/"+data.campaign.id)) body=data.campaign;
    else if(path.endsWith("/matrix")) body=matrix;
    else if(path.endsWith("/delivery")) body=data.before;
    else if(path.endsWith("/optimization")) body={runs:[],unscored_variant_ids:[matrix.run.cells[0].variant.id]};
    else if(path.endsWith("/assets")) body={backgrounds:[],posters:[],logos:[]};
    else if(path.endsWith("/work")) body={jobs:[],active:0,queued:0,concurrency_limit:2,mode:"mock"};
    else return route.fulfill({status:404,json:{message:"Offline fixture route unavailable"}});
    return route.fulfill({json:body});
  });
  await page.goto(`/?campaign=${data.campaign.id}#prediction`);
  const panel=page.locator("section[aria-labelledby=prediction-heading]");
  await expect(panel.getByRole("button",{name:"Optimize hero group"})).toBeDisabled();
  await panel.getByLabel("Audience group").selectOption(other.id);
  await expect(panel.getByRole("button",{name:"Optimize selected group"})).toBeEnabled();
  await panel.getByRole("button",{name:"Optimize selected group"}).click();
  await expect.poll(()=>optimizations).toBe(1);
});
