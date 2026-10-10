"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Campaign } from "@/lib/campaign-api";
import { errorMessage } from "@/lib/error-message";

type Clip = {index:number; state:string; video_id:string|null; filename?:string};
type Video = {id:string; revision:number; mode:string; status:string; model:string;
  approval:string; qa:string; duration?:number; filename:string|null; reasons:string[]; clips:Clip[]; created_at:string;
  source?:string;source_provenance?:string;sha256?:string;poster_id?:string};
type Job = {id:string; kind:string; status:string; error_code:string|null};
type Poster = {id:string; render_input:{size:string; language:string}; validation:{passed:boolean};
  guardian:{status:string}; campaign_revision:number};
async function request<T>(url:string, body?:unknown):Promise<T> {
  const response=await fetch(url,{method:body===undefined?"GET":"POST",cache:"no-store",
    headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json();
  if(!response.ok) throw new Error(errorMessage(value,"Video request failed. Saved clips are retained."));
  return value as T;
}

export default function VideoPanel({campaign,readOnly=false}:{campaign:Campaign;readOnly?:boolean}) {
  const [duration,setDuration]=useState<24|30>(24);
  const [confirmed,setConfirmed]=useState(false);
  const [access,setAccess]=useState(false);
  const [posterId,setPosterId]=useState("");
  const [posters,setPosters]=useState<Poster[]>([]);
  const [model,setModel]=useState("disabled");
  const [mode,setMode]=useState("mock");
  const [enabled,setEnabled]=useState(false);
  const [localEnabled,setLocalEnabled]=useState(false);
  const [localPoster,setLocalPoster]=useState("");
  const [localDuration,setLocalDuration]=useState<12|18|24>(12);
  const [reviewed,setReviewed]=useState<Record<string,boolean>>({});
  const localKey=useRef<string|null>(null);
  const inFlight=useRef(false);
  const [videos,setVideos]=useState<Video[]>([]);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{
    const [saved,work]=await Promise.all([
      request<Video[]>(`/api/campaigns/${campaign.id}/videos`),
      request<{jobs:Job[]}>(`/api/campaigns/${campaign.id}/work`),
    ]);
    setVideos(saved);setJobs(work.jobs.filter(j=>j.kind==="video"||j.kind==="local_video"));
  },[campaign.id]);
  useEffect(()=>{
    let stopped=false;
    void Promise.all([request<{model:string;mode:string;enabled:boolean;local_enabled?:boolean}>("/api/video/config"),
      request<{posters:Poster[]}>(`/api/campaigns/${campaign.id}/assets`)]).then(([config,assets])=>{
      if(stopped)return;setModel(config.model);setMode(config.mode);setEnabled(config.enabled);setLocalEnabled(config.local_enabled===true);setPosters(assets.posters.filter(p=>
        p.campaign_revision===campaign.revision &&
        p.validation.passed && p.guardian.status!=="BLOCKED"));
    }).catch(e=>setError(e.message));
    const tick=()=>{void refresh().catch(e=>{if(!stopped)setError(e.message);});};
    tick();const timer=setInterval(tick,3000);
    return()=>{stopped=true;clearInterval(timer);};
  },[campaign.id,campaign.revision,refresh]);
  const active=jobs.some(j=>j.status==="queued"||j.status==="running");
  const stoppedJobs=jobs.filter(j=>["failed","cancelled","interrupted","stale"].includes(j.status));
  const currentPoster=posters.find(p=>p.id===localPoster)?.id||posters[0]?.id||"";
  const generateLocal=async()=>{
    if(inFlight.current||!currentPoster)return;
    inFlight.current=true;setBusy(true);setError("");
    localKey.current??=crypto.randomUUID();
    try{
      await request(`/api/campaigns/${campaign.id}/work`,{kind:"local_video",idempotency_key:localKey.current,
        input:{expected_revision:campaign.revision,poster_id:currentPoster,duration:localDuration}});
      localKey.current=null;await refresh();
      window.dispatchEvent(new CustomEvent("workflow-update",{detail:{source:"poll"}}));
    }catch(e){setError(e instanceof Error?e.message:"Animation failed. Retry to recover the same job.");}
    finally{inFlight.current=false;setBusy(false);}
  };
  const approveLocal=async(video:Video)=>{
    if(inFlight.current||!reviewed[video.id])return;
    inFlight.current=true;setBusy(true);setError("");
    try{
      await request(`/api/videos/${video.id}/approve`,{expected_revision:campaign.revision,
        observed_hash:video.sha256,owner_approves:true,idempotency_key:`video-approve-${video.id}`});
      await refresh();
    }catch(e){setError(e instanceof Error?e.message:"Approval failed. Approve the source poster first.");}
    finally{inFlight.current=false;setBusy(false);}
  };
  const generate=async()=>{
    setBusy(true);setError("");
    try {
      await request(`/api/campaigns/${campaign.id}/work`,{
        kind:"video",idempotency_key:crypto.randomUUID(),input:{expected_revision:campaign.revision,
          duration,generated_seconds:duration-6,confirm_clip_count:confirmed,
          confirm_possible_charges:confirmed,confirm_video_access:access,poster_id:posterId||null},
      });
      setConfirmed(false);await refresh();
      window.dispatchEvent(new CustomEvent("workflow-update",{detail:{source:"poll"}}));
    }catch(e){setError(e instanceof Error?e.message:"Video request failed");}
    finally{setBusy(false);}
  };
  return <section className="card space-y-4 mt-5" aria-label="Optional video drafts">
    <h3 className="text-xl font-semibold">Saved video drafts</h3>
    <div className="space-y-3 border rounded-xl p-4" aria-label="Poster animation">
      <h4 className="font-semibold">Create a poster animation</h4>
      <p>Real MP4 from your saved poster · local rendering · no AI video charges. All poster text stays visible. Approval is separate.</p>
      <div className="grid gap-3 sm:grid-cols-2"><label>Animation poster<select className="field" value={currentPoster} disabled={readOnly||active||busy} onChange={e=>{setLocalPoster(e.target.value);localKey.current=null;}}>
        {!posters.length&&<option value="">Render a valid poster first</option>}{posters.map(p=><option key={p.id} value={p.id}>{p.render_input.size} · {p.render_input.language} · {p.id.slice(0,8)}</option>)}
      </select></label><label>Animation duration<select className="field" value={localDuration} disabled={readOnly||active||busy} onChange={e=>{setLocalDuration(Number(e.target.value) as 12|18|24);localKey.current=null;}}>
        {[12,18,24].map(n=><option key={n} value={n}>{n} seconds</option>)}</select></label></div>
      {!localEnabled&&<p role="status">Local animation tools are unavailable. Install FFmpeg and FFprobe using the README command, then reload.</p>}
      <button className="primary" disabled={readOnly||!localEnabled||!currentPoster||busy||active||campaign.status!=="locked"} onClick={()=>void generateLocal()}>{busy?"Working…":active?"Video job running…":!currentPoster?"Render a poster first":"Create animated MP4"}</button>
    </div>
    {!enabled && <p role="status">AI footage generation is disabled: no verified AI video model is configured. Local poster animation and saved drafts remain available.</p>}
    <p className="hint">Optional 9:16 video draft · {mode.toUpperCase()} · {model}. Generated footage contains no campaign text. This draft does not approve or publish your campaign.</p>
    {enabled && <fieldset className="contents"><div className="grid gap-3 sm:grid-cols-2">
      <label>Video duration<select className="field" value={duration} disabled={active||busy||readOnly} onChange={e=>{setDuration(Number(e.target.value) as 24|30);setConfirmed(false);}}>
        <option value={24}>24 seconds — 3 generated clips</option><option value={30}>30 seconds — 4 generated clips</option>
      </select></label>
      <label>Six-second end card<select className="field" value={posterId} disabled={active||busy||readOnly} onChange={e=>{setPosterId(e.target.value);setConfirmed(false);}}>
        <option value="">Footage only — end card pending</option>{posters.filter(p=>p.render_input.size==="story").map(p=><option key={p.id} value={p.id}>Validated story poster · {p.render_input.language} · {p.id.slice(0,8)}</option>)}
      </select></label>
    </div>
    <p className="font-semibold">{(duration-6)/6} clips × 6 seconds = {duration-6} generated seconds{posterId?` + 6-second end card = ${duration} seconds total`:`. Footage draft: ${duration-6} seconds; the complete ${duration}-second campaign needs an end card.`}</p>
    <p className="hint">Pricing is unverified; Configured provider may charge. Submissions are rate limited. OCR, visual claim QA and final owner approval remain pending, so downloads are marked UNAPPROVED.</p>
    <label className="flex gap-2"><input type="checkbox" checked={access} disabled={readOnly||active} onChange={e=>setAccess(e.target.checked)}/>I have enabled access to this Configured provider video model on my account.</label>
    <label className="flex gap-2"><input type="checkbox" checked={confirmed} disabled={readOnly||active} onChange={e=>setConfirmed(e.target.checked)}/>I authorize this exact clip count and generated duration, including possible charges.</label>
    <button className="primary" disabled={readOnly||mode!=="live"||campaign.status!=="locked"||!access||!confirmed||busy||active} onClick={()=>void generate()}>{busy ? "Submitting…" : active ? "Video job running…" : mode !== "live" ? "Live mode required" : campaign.status !== "locked" ? "Lock facts first" : (!access || !confirmed) ? "Check authorizations above" : "Generate Video Draft"}</button></fieldset>}
    {!enabled && <button className="primary" disabled>AI footage generation unavailable</button>}
    {enabled&&mode!=="live"&&<p role="status">Switch the backend to LIVE mode to generate actual Configured provider footage. Mock video fixtures are not substituted.</p>}
    {error&&<p role="alert" className="text-red-800">{error}</p>}
    {!videos.length && <p>No saved video drafts for this campaign.</p>}
    {jobs.filter(job=>["queued","running"].includes(job.status)).map(job=><div key={job.id} className="flex flex-wrap items-center gap-3"><span>Video job: {job.status}</span><button className="secondary" disabled={readOnly} onClick={()=>void request(`/api/work/${job.id}/cancel`,{}).then(refresh).catch(e=>setError(e.message))}>Cancel video</button></div>)}
    {stoppedJobs.length>0 && <details><summary>Previous video requests · {stoppedJobs.length} stopped</summary><p className="hint">VIDEO_VALIDATOR_MISSING means the previous configuration lacked FFmpeg/FFprobe. Installing tools alone does not establish video-model support. No stopped request is retried automatically.</p>{stoppedJobs.map(job=><p key={job.id}>Historical request: {job.status} · {job.error_code??"no error recorded"}</p>)}</details>}
    {videos.map(video=><article className="border rounded-xl p-4 space-y-3" key={video.id}>
      <p className="font-semibold">{readOnly?"CACHED VIEW · ":""}{video.source==="local_animation"?"LOCAL POSTER ANIMATION · source ":video.filename ? "SAVED OUTPUT · source " : "Configured provider job · "}{(video.source_provenance||video.mode).toUpperCase()} · {video.status} · {video.approval} · {video.model}</p>
      <p className="hint">Captured: {video.created_at}</p>
      <p className="hint">{video.reasons.join(" · ")}</p>
      <ul>{video.clips.map(clip=><li key={clip.index}>Clip {clip.index+1}: {clip.state}{clip.filename&&video.status!=="cancelled"&&video.status!=="stale"&&<a className="underline ml-3" href={`/api/videos/${video.id}/clips/${clip.index}.mp4`} target="_blank" rel="noreferrer">Preview raw Configured provider clip</a>}</li>)}</ul>
      {video.filename&&["unapproved","approved"].includes(video.status)&&<><video controls preload="metadata" className="max-h-[520px] max-w-full rounded-lg" src={`/api/videos/${video.id}/draft.mp4`}/><p>{video.duration}s · {video.source==="local_animation"?"Source poster and encoding checks":"Visual/OCR QA"}: {video.qa}</p>
        {video.approval!=="APPROVED"&&<a className="secondary inline-block" download="unapproved-video-draft.mp4" href={`/api/videos/${video.id}/draft.mp4`}>Download unapproved draft</a>}
        {video.source==="local_animation"&&video.approval!=="APPROVED"&&<div className="space-y-2"><p>Approve and audit the source poster in Approve + Export first.</p><label className="flex gap-2"><input type="checkbox" checked={!!reviewed[video.id]} disabled={readOnly||busy} onChange={e=>setReviewed({...reviewed,[video.id]:e.target.checked})}/>I reviewed this exact animation and approve its export.</label><button className="primary" disabled={readOnly||busy||!reviewed[video.id]} onClick={()=>void approveLocal(video)}>Approve animation</button></div>}
        {video.source==="local_animation"&&video.approval==="APPROVED"&&<div className="flex flex-wrap gap-3"><a className="primary inline-block" href={`/api/videos/${video.id}/approved.mp4?saved_view=${readOnly}`}>Download approved MP4</a><a className="underline" target="_blank" rel="noreferrer" href={`/api/videos/${video.id}/manifest?saved_view=${readOnly}`}>View animation manifest</a></div>}
      </>}
    </article>)}
  </section>;
}
