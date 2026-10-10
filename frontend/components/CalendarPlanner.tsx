"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, CalendarDays, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import type { components } from "@/lib/api.generated";
import { errorMessage } from "@/lib/error-message";

type Snapshot = components["schemas"]["PlanningSnapshot"];
type Plan = components["schemas"]["PlanView"];
type Campaign = components["schemas"]["Campaign"];
type Draft = {title:string;brief:string;platform:string;planned_for:string;campaign_id:string|null;
  campaign_revision:number|null;item_ids:string[];source_campaign_id:string|null};
type ApprovedSelection = Pick<Draft,"campaign_id"|"campaign_revision"|"platform"|"item_ids">;

function indiaDate() {
  const parts=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
  const part=(type:string)=>parts.find(p=>p.type===type)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}
function emptyDraft(date:string):Draft {
  return {title:"",brief:"",platform:"instagram",planned_for:date+"T10:00",campaign_id:null,
    campaign_revision:null,item_ids:[],source_campaign_id:null};
}
async function api<T>(path:string,method="GET",body?:unknown):Promise<T> {
  const response=await fetch(`/api/plans${path}`,{method,cache:"no-store",headers:{"Content-Type":"application/json"},body:body ? JSON.stringify(body) : undefined});
  const value=await response.json();
  if(!response.ok) throw new Error(errorMessage(value,"Planning unavailable. Start the backend, reload, then retry."));
  return value;
}
const readinessLabels:Record<string,string>={brief_only:"Brief only",review_required:"Needs review",ready:"Approved output ready",stale:"Content changed — review again"};

export default function CalendarPlanner() {
  const router=useRouter();
  const [month,setMonth]=useState(()=>indiaDate().slice(0,7));
  const [day,setDay]=useState(()=>indiaDate());
  const [loaded,setLoaded]=useState<{month:string;data:Snapshot}>();
  const [draft,setDraft]=useState<Draft>(()=>emptyDraft(indiaDate()));
  const [editing,setEditing]=useState<Plan>();
  const [attachment,setAttachment]=useState<ApprovedSelection>();
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const guard=useRef(false);
  const createKey=useRef("");
  const formRef=useRef<HTMLFormElement>(null);
  const snapshot=loaded?.month===month ? loaded.data : undefined;
  const refresh=useCallback(async()=>{const data=await api<Snapshot>(`?month=${month}`);setLoaded({month,data});},[month]);
  useEffect(()=>{
    let active=true;
    const load=()=>void api<Snapshot>(`?month=${month}`).then(data=>{if(active){setLoaded({month,data});setError("");}}).catch(()=>{if(active)setError("Could not load plans. Start the backend and reload. Unsaved form entries remain here.");});
    load();const timer=setInterval(load,60000);
    return()=>{active=false;clearInterval(timer);};
  },[month]);
  useEffect(()=>{
    const query=new URLSearchParams(window.location.search);
    const id=query.get("campaign");const revision=Number(query.get("revision"));
    const timer=setTimeout(()=>{if(id) {
      const selection={campaign_id:id,campaign_revision:revision>0 ? revision : null,
        item_ids:query.getAll("item_ids"),platform:query.get("platform") ?? "instagram"};
      setDraft(old=>({...old,...selection}));
      if(selection.item_ids.length && selection.campaign_revision)setAttachment(selection);
    }},0);
    return()=>clearTimeout(timer);
  },[]);
  function change(patch:Partial<Draft>) {setDraft(old=>({...old,...patch}));createKey.current="";setMessage("");}
  function moveMonth(delta:number) {
    const [year,m]=month.split("-").map(Number);const next=new Date(Date.UTC(year,m-1+delta,1));
    if(next.getUTCFullYear()<2020 || next.getUTCFullYear()>2100)return;
    const value=next.toISOString().slice(0,7);setMonth(value);setDay(value+"-01");setError("");
  }
  async function action(task:()=>Promise<void>) {
    if(guard.current)return;guard.current=true;setBusy(true);setError("");setMessage("");
    try {await task();await refresh();}catch(e){setError(e instanceof Error ? e.message : "Could not save. Reload and retry.");}
    finally {guard.current=false;setBusy(false);}
  }
  function edit(plan:Plan) {
    setEditing(plan);setDraft({title:plan.title,brief:plan.brief ?? "",platform:plan.platform,
      planned_for:plan.planned_for,campaign_id:plan.campaign_id ?? null,campaign_revision:plan.campaign_revision ?? null,
      item_ids:plan.item_ids ?? [],source_campaign_id:plan.source_campaign_id ?? null});
    createKey.current="";setMessage("");formRef.current?.scrollIntoView({block:"start",behavior:"smooth"});
  }
  const [year,m]=month.split("-").map(Number);
  const offset=new Date(Date.UTC(year,m-1,1)).getUTCDay();
  const days=new Date(Date.UTC(year,m,0)).getUTCDate();
  const cells=Math.ceil((offset+days)/7)*7;
  const plans=snapshot?.plans ?? [];
  const upcoming=plans.filter(p=>p.status==="planned");
  const selected=plans.filter(p=>p.planned_for.slice(0,10)===day);
  const monthLabel=new Intl.DateTimeFormat("en-IN",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(Date.UTC(year,m-1,1)));
  const studio=draft.campaign_id ? `/?campaign=${encodeURIComponent(draft.campaign_id)}#approve-export` : "/#speak-type";
  return <div className="min-h-screen bg-[#f4f1e8] text-[#263e33]">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b bg-[#fffdf7] px-5 py-4"><Link className="font-bold" href="/">IntentLocked</Link><Link className="secondary inline-flex items-center gap-2" href={studio}><ArrowLeft size={16}/>Campaign workspace</Link></header>
    <main className="mx-auto max-w-7xl space-y-6 p-4 sm:p-7">
      <div><p className="eyebrow">PLAN AHEAD / BEFORE YOU GENERATE</p><h1 className="mt-2 flex items-center gap-3 text-3xl font-bold"><CalendarDays/>Content calendar</h1><p className="mt-2">Plan campaign briefs and manual posting times. A plan does not lock an offer or publish a post.</p><p className="hint mt-1">All times: Asia/Kolkata (IST). Planning dates and offer validity are separate.</p></div>
      <div className="grid gap-3 sm:grid-cols-3">{[["Plans this month",plans.length],["Need content review",upcoming.filter(p=>p.readiness!=="ready").length],["Owner marked posted",plans.filter(p=>p.status==="owner_posted").length]].map(([label,value])=><div className="card" key={label}><p>{label}</p><strong className="text-3xl">{snapshot ? value : "—"}</strong></div>)}</div>
      <section className="card grid min-w-0 gap-6 lg:grid-cols-[1fr_320px]" aria-label="Monthly campaign calendar">
        <div className="min-w-0"><div className="mb-5 flex flex-wrap items-center justify-between gap-2"><h2 className="text-xl font-bold">{monthLabel}</h2><div className="flex gap-2"><button className="secondary" aria-label="Previous month" onClick={()=>moveMonth(-1)}><ChevronLeft size={16}/></button><button className="secondary" aria-label="Next month" onClick={()=>moveMonth(1)}><ChevronRight size={16}/></button><button className="secondary" onClick={()=>{setMonth(indiaDate().slice(0,7));setDay(indiaDate());}}>Today</button></div></div>
          <div className="grid grid-cols-7 gap-1 text-center text-xs sm:gap-2"><div className="col-span-7 grid grid-cols-7 py-2 font-semibold">{["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(d=><span key={d}>{d}</span>)}</div>
            {Array.from({length:cells},(_,i)=>{const dateNumber=i-offset+1;if(dateNumber<1||dateNumber>days)return <span key={i} aria-hidden="true"/>;
              const date=`${month}-${String(dateNumber).padStart(2,"0")}`;const count=plans.filter(p=>p.planned_for.startsWith(date) && p.status!=="cancelled").length;
              return <button key={i} aria-label={`${date}, ${count} plans`} aria-pressed={day===date} onClick={()=>{setDay(date);if(!editing)change({planned_for:date+"T10:00"});}}
                className={`min-h-14 rounded-lg border p-1 sm:min-h-24 sm:p-3 ${day===date ? "border-[#35271f] bg-[#35271f] text-white" : "border-[#e5dfd4] bg-[#faf7f1]"}`}><strong>{dateNumber}</strong>{count>0 && <span className="mt-1 block text-[10px] sm:text-xs">{count} plan{count!==1 ? "s" : ""}</span>}{date===indiaDate() && <span className="block text-[10px]">Today</span>}</button>;
            })}
          </div><p className="mt-3 text-sm">Selected day: {day} · {selected.length} saved plan(s)</p>
        </div>
        <aside className="min-w-0 space-y-3 lg:border-l lg:pl-6"><h2 className="text-lg font-bold">Upcoming / due this month</h2>{!snapshot && !error && <p role="status">Loading saved plans…</p>}{snapshot && !upcoming.length && <p>No upcoming plans. Choose a date and save your first brief below.</p>}{upcoming.slice(0,5).map(p=><button className="w-full rounded-xl border bg-[#faf7f1] p-4 text-left" key={p.id} onClick={()=>{setDay(p.planned_for.slice(0,10));edit(p);}}><span className="text-xs font-bold uppercase">{p.platform}</span><strong className="mt-2 block break-words">{p.title}</strong><span className="mt-1 flex items-center gap-1 text-sm"><Clock size={14}/>{p.planned_for.replace("T"," ")} IST</span><span className="mt-2 block text-sm">{p.due ? "Due — post manually" : "Planned — manual posting"} · {readinessLabels[p.readiness]}</span></button>)}</aside>
      </section>
      <form ref={formRef} onSubmit={e=>{e.preventDefault();void action(async()=>{
        createKey.current ||= crypto.randomUUID();
        const result=await api<components["schemas"]["Plan"]>(editing ? `/${editing.id}` : "",editing ? "PUT" : "POST",{...draft,...(editing ? {expected_version:editing.version} : {idempotency_key:createKey.current})});
        setEditing(undefined);setDraft(emptyDraft(day));createKey.current="";setMonth(result.planned_for.slice(0,7));setDay(result.planned_for.slice(0,10));setMessage("Plan saved. Nothing was generated, approved or posted.");
      });}} className="card space-y-4" aria-label="Campaign planning form">
        <h2 className="text-xl font-semibold">{editing ? "Edit plan" : "Plan your next campaign"}</h2>
        <fieldset disabled={busy} className="grid min-w-0 gap-4 md:grid-cols-2">
          {attachment && <label className="md:col-span-2">Attach approved output to an existing plan (optional)<select aria-label="Attach approved output to an existing plan (optional)" className="field mt-1" value={editing?.id ?? ""} onChange={e=>{
            const plan=plans.find(p=>p.id===e.target.value);
            if(plan)edit({...plan,...attachment});
            else {setEditing(undefined);setDraft({...emptyDraft(day),...attachment});createKey.current="";}
          }}><option value="">Create a new plan for this output</option>{plans.filter(p=>p.status==="planned" && p.campaign_id===attachment.campaign_id && p.platform===attachment.platform).map(p=><option key={p.id} value={p.id}>{p.title} · {p.planned_for.replace("T"," ")}</option>)}</select><span className="hint">Choose your original plan to keep its brief and posting time. Navigate to its month if it is not listed. Saving updates the selection; it does not publish.</span></label>}
          <label>Plan title<input className="field mt-1" required maxLength={120} value={draft.title} onChange={e=>change({title:e.target.value})}/></label>
          <label>Posting date and time (IST)<input className="field mt-1" required type="datetime-local" min="2020-01-01T00:00" max="2100-12-31T23:59" value={draft.planned_for} onChange={e=>change({planned_for:e.target.value})}/></label>
          <label>Platform<select className="field mt-1" value={draft.platform} onChange={e=>change({platform:e.target.value,item_ids:[],campaign_revision:null})}><option value="instagram">Instagram</option><option value="facebook">Facebook</option><option value="whatsapp">WhatsApp</option></select></label>
          <label>Link an existing campaign (optional)<select className="field mt-1" value={draft.campaign_id ?? ""} onChange={e=>change({campaign_id:e.target.value || null,campaign_revision:null,item_ids:[]})}><option value="">New campaign brief</option>{snapshot?.campaigns.map(c=><option key={c.id} value={c.id}>{c.label} · {c.status} · {c.mode.toUpperCase()} · {c.id.slice(0,6)}</option>)}</select></label>
          <label className="md:col-span-2">Campaign brief<textarea className="field mt-1" rows={4} maxLength={2000} placeholder="Describe your planned offer, café identity and actual validity dates. Review these facts before locking." value={draft.brief} onChange={e=>change({brief:e.target.value})}/></label>
          {!draft.campaign_id && <label className="md:col-span-2">Reuse style from a saved campaign (optional)<select className="field mt-1" value={draft.source_campaign_id ?? ""} onChange={e=>change({source_campaign_id:e.target.value || null})}><option value="">Start with your own style</option>{snapshot?.campaigns.map(c=><option key={c.id} value={c.id}>{c.label} · {c.mode.toUpperCase()} · {c.id.slice(0,6)}</option>)}</select><span className="hint">Copies tone, theme, colours and languages only. Offers, dates, eligibility and approvals need fresh review.</span></label>}
        </fieldset>
        {draft.item_ids.length>0 && <p className="callout">{draft.item_ids.length} exact item(s) linked at revision {draft.campaign_revision}. Approval is checked again whenever this plan is shown.</p>}
        <div className="flex flex-wrap gap-3"><button className="primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save plan changes" : "Save plan"}</button><button type="button" className="secondary" disabled={busy} onClick={()=>{setEditing(undefined);setDraft(emptyDraft(day));createKey.current="";}}>Clear form</button><button type="button" className="secondary" disabled={busy} onClick={()=>void action(refresh)}>Reload plans</button></div>
      </form>
      <section className="space-y-3" aria-label="Plans for selected day"><h2 className="text-xl font-semibold">Plans for {day}</h2>{snapshot && !selected.length && <p>No saved plans on this day.</p>}{selected.map(p=><article className="card min-w-0 space-y-3" key={p.id}><h3 className="break-words text-lg font-bold">{p.title}</h3><p>{p.platform.toUpperCase()} · {p.planned_for.replace("T"," ")} IST · {p.status==="owner_posted" ? "Owner marked posted (not platform verified)" : p.status==="cancelled" ? "Cancelled" : p.due ? "Due — manual posting" : "Planned — manual posting"}</p><p>{readinessLabels[p.readiness]}</p><p className="whitespace-pre-wrap break-words">{p.brief}</p>{p.reasons.map(reason=><p className="callout warning" key={reason}>{reason}</p>)}
        <div className="flex flex-wrap gap-3">{p.campaign_id && <Link className="secondary" href={`/?campaign=${encodeURIComponent(p.campaign_id)}#approve-export`}>Review linked campaign / manual export</Link>}{p.status==="planned" && <><button className="secondary" disabled={busy} onClick={()=>edit(p)}>Edit this plan</button>{!p.campaign_id && <button className="primary" disabled={busy} onClick={()=>void action(async()=>{const c=await api<Campaign>(`/${p.id}/start`,"POST",{expected_version:p.version});router.push(`/?campaign=${c.id}#speak-type`);})}>Start campaign from brief</button>}<button className="secondary" disabled={busy} onClick={()=>void action(async()=>{await api(`/${p.id}/cancel`,"POST",{expected_version:p.version});setMessage("Plan cancelled. Campaign content and approvals are unchanged.");})}>Cancel this plan</button>{p.readiness==="ready" && <button className="secondary" disabled={busy} onClick={()=>{if(window.confirm("Have you manually published this exact approved output? This records your confirmation only."))void action(async()=>{await api(`/${p.id}/posted`,"POST",{expected_version:p.version,owner_confirms_manual_post:true});setMessage("Marked posted by owner. No platform verification or automatic send occurred.");});}}>I posted this manually</button>}</>}</div>
      </article>)}</section>
      {error && <p role="alert" className="callout danger">{error}</p>}{message && <p role="status" className="callout">{message}</p>}
      <p className="hint">No scheduled publishing or background reminder service. The calendar shows at most 200 entries for the selected month; counts refer to those entries. Use your existing approval and manual publishing workflow when a plan is due.</p>
    </main>
  </div>;
}
