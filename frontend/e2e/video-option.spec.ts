import {test,expect} from "@playwright/test";
import {readFile} from "node:fs/promises";

test("unsupported video is explicit and cannot submit despite locked facts",async({page})=>{
  const data=JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json","utf8"));
  let submissions=0;
  await page.route("**/api/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(route.request().method()!=="GET"){submissions++;return route.fulfill({status:500,json:{message:"Unexpected submission"}});}
    if(path.includes("/stream/"))return route.fulfill({contentType:"text/event-stream",body:": mock\n\n"});
    let body:unknown;
    if(path.endsWith("/ready"))body={...data.health,provider:"kRouter",text_model:"ollama/gpt-oss:120b",image_model:"nb/nanobanana-flash",vision_supported:false,video_enabled:false};
    else if(path.endsWith("/cost"))body=data.cost;
    else if(path.endsWith("/traces"))body=[];
    else if(path.endsWith("/campaigns/"+data.campaign.id))body=data.campaign;
    else if(path.endsWith("/matrix"))body=data.matrix;
    else if(path.endsWith("/delivery"))body=data.before;
    else if(path.endsWith("/work"))body={jobs:[],active:0,queued:0,concurrency_limit:2,mode:"mock"};
    else if(path.endsWith("/assets"))body={backgrounds:[],posters:[],logos:[]};
    else if(path.endsWith("/video/config"))body={enabled:false,model:"disabled",mode:"mock",price_verified:false,approval_enabled:false};
    else if(path.endsWith("/videos"))body=[];
    else return route.fulfill({status:404,json:{message:"Offline fixture unavailable"}});
    return route.fulfill({json:body});
  });
  await page.goto(`/?campaign=${data.campaign.id}#campaign-matrix`);
  await page.getByRole("button",{name:"Saved video drafts",exact:true}).click();
  const panel=page.getByRole("region",{name:"Optional video drafts"});
  await expect(panel).toContainText("AI footage generation is disabled");
  await expect(panel).toContainText("No saved video drafts");
  await expect(panel.getByRole("button",{name:"AI footage generation unavailable"})).toBeDisabled();
  await expect(panel.getByLabel("Video duration")).toHaveCount(0);
  await expect(panel.getByLabel("I authorize this exact clip count and generated duration, including possible charges.")).toHaveCount(0);
  expect(submissions).toBe(0);
});
