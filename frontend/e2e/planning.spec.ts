import {test,expect} from "@playwright/test";
import {readFile,writeFile} from "node:fs/promises";

test("owner plans before generation: correct calendar, persistence, edit, review and no automatic publish",async({page})=>{
  const fixture=JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json","utf8"));
  type Plan={id:string;version:number;title:string;brief:string;platform:string;planned_for:string;status:string;
    readiness:string;reasons:string[];due:boolean;campaign_id:string|null;campaign_revision:number|null;item_ids:string[];source_campaign_id:string|null};
  const plans:Plan[]=[];
  let saved=0,starts=0,external=0;
  await page.clock.install({time:new Date("2026-10-09T08:00:00Z")});
  await page.route("**/api/**",async route=>{
    const url=new URL(route.request().url());const path=url.pathname;let body:unknown;
    if(path.includes("/meta") || path.endsWith("/intent")){external++;return route.fulfill({status:500,json:{message:"Unexpected inference or publishing"}});}
    if(path==="/api/plans"){
      if(route.request().method()==="POST"){
        const data=route.request().postDataJSON();saved++;
        const plan={...data,id:"mock-plan-1",version:1,status:"planned",readiness:"brief_only",reasons:[],due:false};
        plans.push(plan);body=plan;
      } else body={now:"2026-10-09T13:30:00+05:30",timezone:"Asia/Kolkata",campaigns:[],plans:plans.filter(p=>p.planned_for.startsWith(url.searchParams.get("month")!))};
    } else if(path==="/api/plans/mock-plan-1" && route.request().method()==="PUT"){
      const data=route.request().postDataJSON();expect(data.expected_version).toBe(plans[0].version);
      plans[0]={...plans[0],...data,version:plans[0].version+1};body=plans[0];
    } else if(path.endsWith("/mock-plan-1/start")){
      starts++;body={...fixture.campaign,status:"draft",facts:fixture.campaign.facts.map((f:object)=>({...f,canonical:null,approval_id:null})),transcript:plans[0].brief};
      plans[0].campaign_id=fixture.campaign.id;plans[0].readiness="review_required";
    } else if(path.endsWith("/mock-plan-1/cancel")){plans[0].status="cancelled";body=plans[0];}
    else if(path.endsWith("/ready"))body=fixture.health;
    else if(path.endsWith("/cost"))body=fixture.cost;
    else if(path.endsWith("/traces"))body=[];
    else if(path.endsWith("/campaigns/"+fixture.campaign.id))body={...fixture.campaign,status:"draft",transcript:plans[0].brief,facts:fixture.campaign.facts.map((f:object)=>({...f,canonical:null,approval_id:null}))};
    else if(path.endsWith("/work"))body={jobs:[],active:0,queued:0,concurrency_limit:2,mode:"mock"};
    else if(path.includes("/stream/"))return route.fulfill({contentType:"text/event-stream",body:": mock\n\n"});
    else return route.fulfill({status:404,json:{message:"Unavailable mock route"}});
    return route.fulfill({json:body,status:route.request().method()==="POST" && path==="/api/plans" ? 201 : 200});
  });
  await page.goto("/calendar");
  const calendar=page.getByRole("region",{name:"Monthly campaign calendar"});
  await expect(calendar.getByRole("heading",{name:"October 2026"})).toBeVisible();
  // October 1, 2026 is Thursday: four empty cells precede it.
  expect(await calendar.getByRole("button",{name:"2026-10-01, 0 plans",exact:true}).evaluate(el=>Array.from(el.parentElement!.children).indexOf(el))).toBe(5);
  await calendar.getByRole("button",{name:"Next month"}).click();
  await expect(calendar.getByRole("heading",{name:"November 2026"})).toBeVisible();
  await calendar.getByRole("button",{name:"Previous month"}).click();
  await calendar.getByRole("button",{name:"2026-10-16, 0 plans",exact:true}).click();
  const form=page.getByRole("form",{name:"Campaign planning form"});
  await form.getByLabel("Plan title",{exact:true}).fill("Friday coffee campaign");
  await form.getByLabel("Campaign brief",{exact:true}).fill("My future café offer needs facts and date review.");
  await expect(form.getByLabel("Posting date and time (IST)")).toHaveValue("2026-10-16T10:00");
  await form.getByRole("button",{name:"Save plan",exact:true}).click();
  await expect(page.getByRole("status")).toContainText("Nothing was generated, approved or posted");
  await expect(calendar.getByRole("button",{name:"2026-10-16, 1 plans",exact:true})).toBeVisible();
  await page.reload();
  await calendar.getByRole("button",{name:"2026-10-16, 1 plans",exact:true}).click();
  const list=page.getByRole("region",{name:"Plans for selected day"});
  await expect(list.getByText("Brief only",{exact:true})).toBeVisible();
  await list.getByRole("button",{name:"Edit this plan"}).click();
  await form.getByLabel("Plan title",{exact:true}).fill("Updated Friday plan");
  await form.getByRole("button",{name:"Save plan changes"}).click();
  await expect(list.getByRole("heading",{name:"Updated Friday plan"})).toBeVisible();
  await expect(list.getByRole("button",{name:"I posted this manually"})).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"../docs/evidence/planning-mobile.png",fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:"../docs/evidence/planning-desktop.png",fullPage:true});
  await list.getByRole("button",{name:"Start campaign from brief"}).click();
  await expect(page).toHaveURL(new RegExp(`campaign=${fixture.campaign.id}#speak-type`));
  await expect(page.getByRole("textbox",{name:/campaign brief|transcript|offer/i}).first()).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(saved).toBe(1);expect(starts).toBe(1);expect(external).toBe(0);
  await writeFile("../docs/evidence/planning-browser.json",JSON.stringify({mode:"mock",outcome:"PASS",calendar_alignment:"PASS",month_navigation:"PASS",save_reload_edit:"PASS",mobile:"PASS",draft_handoff:"PASS",inference_or_publish_calls:0},null,2));
});

test("approved output attaches to the original future plan without a duplicate",async({page})=>{
  const fixture=JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json","utf8"));
  const campaign=fixture.campaign;
  let plan={id:"existing-plan",version:3,title:"November coffee launch",brief:"Keep this reviewed planning brief.",
    platform:"instagram",planned_for:"2026-11-05T10:30",timezone:"Asia/Kolkata",campaign_id:campaign.id,
    campaign_revision:null,item_ids:[] as string[],source_campaign_id:null,status:"planned",readiness:"review_required",reasons:[],due:false};
  let updates=0;
  await page.clock.install({time:new Date("2026-10-09T08:00:00Z")});
  await page.route("**/api/**",async route=>{
    const url=new URL(route.request().url());
    if(url.pathname==="/api/plans" && route.request().method()==="GET")return route.fulfill({json:{now:"2026-10-09T13:30:00+05:30",timezone:"Asia/Kolkata",plans:url.searchParams.get("month")==="2026-11" ? [plan] : [],campaigns:[{id:campaign.id,label:"Test café",revision:campaign.revision,status:"locked",mode:"mock"}]}});
    if(url.pathname==="/api/plans/existing-plan" && route.request().method()==="PUT"){
      const body=route.request().postDataJSON();expect(body.expected_version).toBe(3);expect(body.item_ids).toEqual(["approved-item"]);
      expect(body.campaign_revision).toBe(campaign.revision);expect(body.planned_for).toBe("2026-11-05T10:30");
      expect(body.brief).toBe("Keep this reviewed planning brief.");updates++;plan={...plan,...body,version:4,readiness:"ready"};
      return route.fulfill({json:plan});
    }
    throw new Error("Unexpected planning request: "+route.request().method()+" "+url.pathname);
  });
  await page.goto(`/calendar?campaign=${campaign.id}&revision=${campaign.revision}&platform=instagram&item_ids=approved-item`);
  const picker=page.getByLabel("Attach approved output to an existing plan (optional)",{exact:true});
  await expect(picker).toBeVisible();
  await page.getByRole("button",{name:"Next month"}).click();
  await expect(picker.getByRole("option",{name:/November coffee launch/})).toHaveCount(1);
  await picker.selectOption("existing-plan");
  await page.getByRole("button",{name:"Save plan changes"}).click();
  await expect(page.getByRole("status")).toContainText("Plan saved");
  await expect(page.getByRole("region",{name:"Plans for selected day"}).getByText("Approved output ready",{exact:true})).toBeVisible();
  expect(updates).toBe(1);
});
