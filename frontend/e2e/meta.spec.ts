import { test, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";

// Supersedes API-delivery UI: legacy adapters remain covered by backend tests.
test("manual publishing persists links, exports exact copy, handles clipboard failure and never calls Meta", async ({page,context}) => {
  const data=JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json","utf8"));
  let profiles={version:0,instagram:null as string|null,facebook:null as string|null,whatsapp:null as string|null};
  let metaCalls=0,approvalCalls=0,profileSaves=0,failReload=false;
  const redirects: string[]=[];
  for(const destination of ["https://www.instagram.com/**","https://www.facebook.com/**","https://wa.me/**","https://web.whatsapp.com/**"]) await context.route(destination,route=>{expect(route.request().headers()["referer"]).toBeUndefined();return route.fulfill({contentType:"text/html",body:"<title>Offline destination verification</title><p>MOCK destination; no account contacted.</p>"});});
  await page.addInitScript(()=>Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText:()=>Promise.reject(new Error("Denied"))}}));
  await page.route("**/api/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    let body:unknown;
    if(path.includes("/meta")){metaCalls++;return route.fulfill({status:500,json:{message:"Meta calls forbidden"}});}
    if(path==="/api/social-profiles"){
      if(failReload && route.request().method()==="GET") return route.fulfill({status:503,json:{message:"Backend unavailable"}});
      if(route.request().method()==="PUT"){
        const next=route.request().postDataJSON();expect(next.expected_version).toBe(profiles.version);
        profiles={version:profiles.version+1,instagram:next.instagram,facebook:next.facebook,whatsapp:next.whatsapp};profileSaves++;
      }
      body=profiles;
    } else if(path.includes("/stream/"))return route.fulfill({contentType:"text/event-stream",body:": mock\n\n"});
    else if(path.endsWith("/ready"))body=data.health;
    else if(path.endsWith("/cost"))body=data.cost;
    else if(path.endsWith("/traces"))body=[];
    else if(path.endsWith("/campaigns/"+data.campaign.id))body=data.campaign;
    else if(path.endsWith("/matrix"))body=data.matrix;
    else if(path.endsWith("/delivery"))body=data.approved;
    else if(path.endsWith("/work"))body={jobs:[],active:0,queued:0,concurrency_limit:2,mode:"mock"};
    else if(path.endsWith("/assets"))body={backgrounds:[],posters:[],logos:[]};
    else if(path.endsWith("/export"))body=data.pack;
    else if(path.endsWith("/approve")){approvalCalls++;body=data.approval;}
    else return route.fulfill({status:404,json:{message:"Unavailable mock route"}});
    return route.fulfill({json:body});
  });
  await page.goto(`/?campaign=${data.campaign.id}#approve-export`);
  const manual=page.getByRole("region",{name:"Manual social publishing"});
  const delivery=page.getByRole("region",{name:"Approve and export"});
  await expect(page.getByRole("region",{name:"Optional API delivery"})).toHaveCount(0);
  await expect(manual.getByRole("link",{name:"Open Instagram profile"})).toHaveCount(0);
  await delivery.getByRole("button",{name:"Show approved final output"}).click();
  await expect(manual.getByText(/Instagram profile link not set/)).toBeVisible();
  await manual.getByLabel("Instagram profile URL (optional)").fill("https://www.instagram.com/test_cafe");
  await manual.getByLabel("Facebook Page URL (optional)").fill("https://www.facebook.com/TestCafe");
  await manual.getByLabel("WhatsApp café chat URL (optional)").fill("https://wa.me/15555550123");
  await expect(manual.getByRole("link",{name:"Open Instagram profile"})).toHaveCount(0);
  await manual.getByRole("button",{name:"Save social links"}).click();
  for(const [name,url] of [["Instagram profile",profiles.instagram],["Facebook Page",profiles.facebook],["WhatsApp café chat",profiles.whatsapp]]){
    const link=manual.getByRole("link",{name:`Open ${name}`,exact:true});
    await expect(link).toHaveAttribute("href",url!);await expect(link).toHaveAttribute("target","_blank");
    await expect(link).toHaveAttribute("rel","noopener noreferrer");
    const [popup]=await Promise.all([context.waitForEvent("page"),link.click()]);
    await popup.waitForLoadState();expect(popup.url()).toBe(url);redirects.push(name!);await popup.close();
  }
  const [whatsappWeb]=await Promise.all([context.waitForEvent("page"),manual.getByRole("link",{name:"Open WhatsApp Web",exact:true}).click()]);
  await whatsappWeb.waitForLoadState();expect(whatsappWeb.url()).toBe("https://web.whatsapp.com/");redirects.push("WhatsApp Web");await whatsappWeb.close();
  await manual.screenshot({path:"../docs/evidence/manual-social-desktop.png"});
  await expect(delivery.getByLabel("Authorized copy").first()).toHaveValue(Object.values(data.pack.copy_text)[0] as string);
  await delivery.getByRole("button",{name:"Copy approved text"}).first().click();
  await expect(page.getByRole("alert").filter({hasText:"Clipboard unavailable"})).toBeVisible();
  await expect(delivery.getByRole("link",{name:"Download approved text"})).toBeVisible();
  failReload=true;await manual.getByRole("button",{name:"Reload social links"}).click();
  await expect(manual.getByRole("alert")).toContainText("Backend unavailable");
  await expect(manual.getByRole("link",{name:"Open Instagram profile"})).toBeVisible();
  failReload=false;await page.reload();
  await expect(manual.getByLabel("Instagram profile URL (optional)")).toHaveValue(profiles.instagram!);
  await expect(manual.getByRole("link",{name:"Open Instagram profile"})).toHaveCount(0);
  await delivery.getByRole("button",{name:"Show approved final output"}).click();
  await expect(manual.getByRole("link",{name:"Open Instagram profile"})).toBeVisible();
  await delivery.getByRole("checkbox").first().uncheck();
  await expect(manual.getByRole("link",{name:"Open Instagram profile"})).toHaveCount(0);
  await delivery.getByRole("button",{name:"Show approved final output"}).click();
  await page.setViewportSize({width:390,height:844});
  await expect(manual).toBeVisible();
  expect(await manual.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  await manual.screenshot({path:"../docs/evidence/manual-social-mobile.png"});
  expect(metaCalls).toBe(0);expect(approvalCalls).toBe(0);expect(profileSaves).toBe(1);
  await writeFile("../docs/evidence/manual-social-browser.json",JSON.stringify({outcome:"PASS",mode:"mock",meta_api_calls:metaCalls,real_approvals:0,publishing_performed:false,redirect_checks:redirects,new_tab_destinations:"PASS (intercepted offline)",external_account_requests:0,persistence_reload:"PASS",clipboard_fallback:"PASS",changed_selection_hides_links:"PASS"},null,2));
});
