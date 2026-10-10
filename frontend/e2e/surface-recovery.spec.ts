import {test, expect} from "@playwright/test";
import {readFile} from "node:fs/promises";

for (const changedFacts of [false, true]) {
  test(`failed wording loads the current revision and ${changedFacts ? "requires renewed fact confirmation" : "retries without losing confirmed facts"}`, async ({page}) => {
    const fixture = JSON.parse(await readFile("../docs/evidence/approval-browser-fixtures.json", "utf8"));
    const campaign = structuredClone(fixture.campaign);
    Object.assign(campaign, {revision:5,status:"draft",fact_hash:null,approved_at:null,warnings:[],acknowledged_warning_ids:[]});
    campaign.facts = campaign.facts.map((f:Record<string,unknown>) => ({...f,surface:{},status:f.canonical ? "proposed" : "not_specified",approved_at:null,approval_id:null}));
    let formCalls=0, lockCalls=0, staleGenericRetries=0;
    const keys:string[]=[];
    const failed={id:"failed-wording-job",campaign_id:campaign.id,campaign_revision:5,kind:"forms",status:"failed",mode:"mock",created_at:"2026-10-10T00:00:00Z",updated_at:"2026-10-10T00:00:01Z",deadline:"2026-10-10T00:08:00Z",error_code:"SURFACES_UNAVAILABLE",result:null,elapsed_seconds:1,completed_steps:0,max_steps:1,calls:2,max_calls:6,list_price_estimate_usd:0,unknown_cost_calls:0,notices:[],cache_hits:[]};
    await page.route("**/api/**",async route=>{
      const path=new URL(route.request().url()).pathname;
      let body:unknown;
      if(path.includes("/stream/"))return route.fulfill({contentType:"text/event-stream",body:": offline fixture\n\n"});
      if(path.endsWith("/ready"))body=fixture.health;
      else if(path.endsWith("/cost"))body=fixture.cost;
      else if(path.endsWith("/traces"))body=[];
      else if(path.endsWith(`/campaigns/${campaign.id}`))body=campaign;
      else if(path.endsWith("/retry")) {staleGenericRetries++;return route.fulfill({status:409,json:{code:"REVISION_CONFLICT",message:"Review current facts"}});}
      else if(path.endsWith("/work") && route.request().method()==="POST"){
        const request=route.request().postDataJSON();
        expect(request.kind).toBe("forms");
        expect(request.input.confirm_canonical).toBe(true);
        keys.push(request.idempotency_key);formCalls++;
        if(formCalls===1){
          expect(request.input.expected_revision).toBe(5);
          campaign.revision=6;campaign.status="canonical_confirmed";
          if(changedFacts){
            campaign.revision=7;campaign.status="draft";
            const offer=campaign.facts.find((f:{key:string})=>f.key==="OFFER");offer.canonical.value=15;offer.version++;
          }
          body=failed;
        } else {
          expect(request.input.expected_revision).toBe(changedFacts ? 7 : 6);
          campaign.revision+=2;campaign.status="forms_review";
          for(const fact of campaign.facts){
            if(!fact.canonical)continue;
            fact.surface={en:structuredClone(fixture.campaign.facts.find((f:{key:string})=>f.key===fact.key).surface.en)};
            if(changedFacts && fact.key==="OFFER")fact.surface.en.nom=["15% off"];
            fact.version++;
          }
          body={id:"retry-wording-job",kind:"forms",status:"completed",result:campaign};
        }
      }else if(path.endsWith("/facts/lock")){
        const request=route.request().postDataJSON();
        expect(request.expected_revision).toBe(campaign.revision);
        expect(request.approve_canonical_and_forms).toBe(true);
        expect(request.reviewed_fact_versions).toEqual(Object.fromEntries(campaign.facts.map((f:{key:string;version:number})=>[f.key,f.version])));
        lockCalls++;campaign.status="locked";campaign.revision++;campaign.fact_hash="mock-reviewed-lock";campaign.approved_at="2026-10-10T00:00:05Z";body=campaign;
      }else if(path.endsWith("/work"))body={jobs:formCalls ? [failed] : [],active:0,queued:0,concurrency_limit:2,mode:"mock",latest_event_id:0};
      else if(path.endsWith("/matrix"))body=fixture.matrix;
      else if(path.endsWith("/delivery"))body=fixture.before;
      else if(path.endsWith("/assets"))body={backgrounds:[],posters:[],logos:[]};
      else if(path.endsWith("/optimization"))body={runs:[],unscored_variant_ids:[]};
      else return route.fulfill({status:404,json:{message:"Offline fixture route unavailable"}});
      return route.fulfill({json:body});
    });
    await page.goto(`/?campaign=${campaign.id}#facts-lock`);
    const workspace=page.getByRole("region",{name:"Campaign workspace"});
    const confirm=page.getByLabel("I confirm the saved canonical facts, including names, numbers and dates.");
    await confirm.check();
    await page.getByRole("button",{name:"Propose localized forms",exact:true}).click();
    await expect(workspace.getByRole("alert")).toContainText("The wording could not be prepared");
    const retry=page.getByRole("button",{name:"Retry wording",exact:true});
    if(changedFacts){
      await expect(confirm).not.toBeChecked();
      await expect(retry).toBeDisabled();
      await expect(page.getByLabel("Percent off",{exact:true})).toHaveValue("15");
      await confirm.check();
    } else await expect(confirm).toBeChecked();
    await expect(retry).toBeEnabled();
    await page.getByRole("button",{name:"Open trace drawer",exact:true}).click();
    await expect(page.getByRole("button",{name:"Retry unfinished forms",exact:true})).toHaveCount(0);
    await page.getByRole("button",{name:"Review facts to retry wording",exact:true}).click();
    await expect(retry).toBeVisible();
    await retry.click();
    const lock=page.getByRole("button",{name:"Lock approved facts",exact:true});
    await expect(lock).toBeDisabled();
    await expect(page.getByLabel("OFFER en nom",{exact:true})).toHaveValue(changedFacts ? "15% off" : fixture.campaign.facts.find((f:{key:string})=>f.key==="OFFER").surface.en.nom.join(" | "));
    await page.getByLabel("I approve these canonical facts and all displayed localized forms. Lock this exact revision.").check();
    await lock.click();
    await expect(page.getByText("Locked by owner",{exact:false})).toBeVisible();
    expect(formCalls).toBe(2);expect(lockCalls).toBe(1);expect(new Set(keys).size).toBe(2);expect(staleGenericRetries).toBe(0);
  });
}
