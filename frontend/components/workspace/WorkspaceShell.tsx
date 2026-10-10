"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { motion, MotionConfig } from "framer-motion";
import { ArrowLeft, ArrowRight, AudioLines, CalendarDays, Check, ChevronRight, CircleDot, Command, FileCheck2, Layers3, LockKeyhole, MessageSquare, Plus, ShieldCheck, Sparkles, Terminal, TrendingUp } from "lucide-react";
import type { Campaign } from "@/lib/campaign-api";
import type { components } from "@/lib/api.generated";
import dynamic from "next/dynamic";
import { Button, Dialog, StatusBadge, useMotionSafe } from "../ui";
const UiKit=dynamic(()=>import("../ui/UiKit"));

export const stages = [
  {id:"speak-type", label:"Speak", title:"Give your idea a voice.", help:"Tell us what you want to offer. You review every fact before it travels.", icon:AudioLines},
  {id:"facts-lock", label:"Facts Lock", title:"Your truth. Locked in.", help:"Confirm the facts and the exact words that carry them in every language.", icon:LockKeyhole},
  {id:"brand-strategy", label:"Strategy", title:"A reason for everyone.", help:"Different motivations. One owner-approved offer.", icon:Sparkles},
  {id:"campaign-matrix", label:"Campaign", title:"One idea. Many expressions.", help:"Explore the actual returned copy and posters across your selected combinations.", icon:Layers3},
  {id:"prediction", label:"Predict", title:"Choose with evidence.", help:"Follow the bounded optimization loop, including its rejected rounds.", icon:TrendingUp},
  {id:"guardian", label:"Guardian", title:"Keep every promise honest.", help:"Test the boundary. A diagnostic never grants approval.", icon:ShieldCheck},
  {id:"ledger-changes", label:"Changes", title:"Change direction. Keep the truth.", help:"Review what changes, what stays, and what needs another approval.", icon:MessageSquare},
  {id:"approve-export", label:"Approve", title:"Ready for your final say.", help:"Review the exact content and bytes before authorizing export.", icon:FileCheck2},
] as const;
export type StageId = typeof stages[number]["id"];
export type StageStatus="Not started"|"In progress"|"Needs your review"|"Done ✓"|"Blocked ⚠";
type Context = {stage:StageId; navigate:(id:StageId)=>void; campaign:Campaign|null; setCampaign:(c:Campaign|null)=>void; started:boolean; start:()=>void; traceOpen:boolean; setTraceOpen:(v:boolean)=>void; newCampaign:()=>void; traces:components["schemas"]["TraceEvent"][]; progress:string; setProgress:(s:string)=>void; connection:ReactNode; elapsed:number|null; setElapsed:(value:number|null)=>void; recordStage:(id:StageId,status:StageStatus,scope:string)=>void};
const WorkspaceContext = createContext<Context | null>(null);
export function useWorkspace() { const value = useContext(WorkspaceContext); if (!value) throw new Error("Workspace shell required"); return value; }
export function Stage({ id, children }: {id:StageId; children:ReactNode}) {
  const {stage} = useWorkspace(); const safe = useMotionSafe();
  return <motion.div hidden={stage !== id} aria-hidden={stage !== id} className="stage-view" data-stage={id} animate={stage === id ? {opacity:1,y:0} : {opacity:0,y:safe ? 12 : 0}} transition={{duration:safe ? .24 : 0}}>{children}</motion.div>;
}
export default function WorkspaceShell({ children, health, cost, traces, error, loading, refresh }: {children:ReactNode; health:components["schemas"]["Health"]|null; cost:components["schemas"]["Cost"]|null; traces:components["schemas"]["TraceEvent"][]; error:string; loading:boolean; refresh:()=>void}) {
  const [stage,setStage] = useState<StageId>("speak-type");
  const [campaign,setCampaign] = useState<Campaign|null>(null);
  const [started,setStarted] = useState(false);
  const [traceOpen,setTraceOpen] = useState(false);
  const [palette,setPalette] = useState(false);
  const [saved,setSaved] = useState(false);
  const [progress,setProgress] = useState("");
  const [elapsed,setElapsed]=useState<number|null>(null);
  const [notice,setNotice] = useState("");
  const [statuses,setStatuses] = useState<Partial<Record<StageId,{scope:string;status:StageStatus}>>>({});
  const recordStage=useCallback((id:StageId,status:StageStatus,scope:string)=>setStatuses(old=>old[id]?.scope===scope && old[id]?.status===status ? old : {...old,[id]:{scope,status}}),[]);
  const [kit,setKit] = useState(false);
  useEffect(()=>{if(process.env.NODE_ENV!=="development")return;const timer=setTimeout(()=>setKit(new URLSearchParams(window.location.search).get("uikit")==="1"),0);return()=>clearTimeout(timer);},[]);
  const locked = campaign?.status === "locked";
  const allowed = useCallback((id:StageId) => id === "speak-type" || (id === "facts-lock" ? !!campaign : locked), [campaign,locked]);
  const navigate = useCallback((id:StageId) => {
    if (!allowed(id)) {setNotice(id === "facts-lock" ? "Propose your brief first." : "Lock your facts first.");return;}
    setStarted(true); setStage(id); setNotice("");
    const url=new URL(window.location.href);url.hash=id;
    if(window.location.hash!==`#${id}`)window.history.pushState({},"",url);
    window.scrollTo({top:0,behavior:"instant"});
    window.setTimeout(() => document.getElementById("stage-title")?.focus({preventScroll:true}), 0);
  }, [allowed]);
  useEffect(() => {
    const sync = () => { const value = window.location.hash.slice(1); const found = stages.find(s=>s.id===value); if (found && allowed(found.id)) { setStage(found.id); setStarted(true); } };
    sync(); window.addEventListener("hashchange",sync); window.addEventListener("popstate",sync); return()=>{window.removeEventListener("hashchange",sync);window.removeEventListener("popstate",sync);};
  }, [allowed]);
  useEffect(() => { const update = (e:Event) => setSaved(!!(e as CustomEvent).detail.saved); window.addEventListener("workspace-mode",update); return()=>window.removeEventListener("workspace-mode",update); }, []);
  const newCampaign = useCallback(() => { window.dispatchEvent(new Event("workspace-new")); setStage("speak-type"); setStarted(true); window.location.hash="speak-type"; }, []);
  const index = stages.findIndex(s=>s.id===stage);
  useEffect(() => {
    const key = (e:KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && ["k","j"].includes(e.key.toLowerCase())) {e.preventDefault(); if(document.querySelector('[role="dialog"]') && !traceOpen && !palette)return; if(e.key.toLowerCase()==="j" && !palette)setTraceOpen(v=>!v);else if(!traceOpen)setPalette(v=>!v); return;}
      if ((e.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]") || traceOpen || palette || document.querySelector('[role="dialog"]')) return;
      if(e.key==="[" && index>0)navigate(stages[index-1].id);
      if(e.key==="]" && index<7)navigate(stages[index+1].id);
    };
    window.addEventListener("keydown",key); return()=>window.removeEventListener("keydown",key);
  }, [index,navigate,traceOpen,palette]);
  const active=stages[index];
  const name=campaign?.facts.find(f=>f.key==="CAFE")?.canonical;
  const mode=saved || health?.mode === "SAVED DEMO OUTPUT" ? "SAVED DEMO OUTPUT" : health?.mode ?? "CONNECTING";
  const hasWorkspace=started || !!campaign;
  return <MotionConfig reducedMotion="user"><WorkspaceContext.Provider value={{stage,navigate,campaign,setCampaign,started,start:()=>{setStarted(true);navigate("speak-type");},traceOpen,setTraceOpen,newCampaign,traces,progress,setProgress,elapsed,setElapsed,recordStage,connection:<div className="card mb-5 space-y-3"><h3 className="font-bold">Connection & call evidence</h3><p>{health ? "Ready" : loading ? "Checking local services…" : "Backend unavailable"}</p><p className="hint">{health?.provider ?? "Provider unavailable"} · video {health?.video_enabled ? "Opt-in enabled" : "disabled"}</p><p>{cost ? `${cost.calls} recorded attempts · ${cost.mock_calls} mock · ${cost.unknown_cost_calls} live attempts with unknown cost · $${cost.known_list_price_estimate.toFixed(6)} known list estimate` : "Usage unavailable"}</p><p className="hint">Actual billing is unknown. Simulated scores are not measured campaign performance.</p><Button variant="secondary" loading={loading} onClick={refresh}>{error ? "Retry connection" : "Refresh status"}</Button></div>}}>
    <div id="workspace-root" className="workspace-shell">
      <a href="#workspace-content" className="skip-link">Skip to workspace</a>
      <header className="top-bar"><a href="#speak-type" className="brand" onClick={e=>{e.preventDefault();navigate("speak-type");}}><span className="brand-symbol"><LockKeyhole size={19}/></span>Intent<span className="brand-light">Locked</span></a><span className="campaign-name">{name?.kind==="text" ? name.value : "Your next campaign"}{campaign && <span className="revision">Revision {campaign.revision}</span>}</span><div className="top-actions"><a className="ui-button secondary inline-flex items-center gap-2" href="/calendar" aria-label="Plan ahead in content calendar"><CalendarDays size={17}/><span className="desktop-label">Plan ahead</span></a><span className={`mode-pill ${mode==="SAVED DEMO OUTPUT" ? "saved" : mode.toLowerCase()}`}><CircleDot size={12}/>{mode}</span><span className="cost-meter">{cost ? `$${cost.known_list_price_estimate.toFixed(5)}` : "—"}<small>USD · list estimate{elapsed!==null ? ` · last work ${Math.floor(elapsed)}s` : ""}</small></span><Button variant="ghost" onClick={()=>setTraceOpen(true)} aria-label="Open trace drawer"><Terminal size={17}/><span className="desktop-label">Trace</span><kbd>⌘/Ctrl J</kbd></Button><Button variant="secondary" aria-label="New campaign" onClick={newCampaign}><Plus size={16}/><span className="desktop-label">New campaign</span></Button></div></header>
      <div className={`workspace-layout ${!hasWorkspace ? "welcome-layout" : ""}`}>
        {hasWorkspace && <nav className="stepper-rail" aria-label="Campaign workflow"><p className="eyebrow rail-eyebrow">YOUR WORKSPACE</p>{stages.map((s,i)=>{const Icon=s.icon; const available=allowed(s.id);const done=locked && i<2;return <button key={s.id} title={available ? s.title : i===1 ? "Propose your brief first" : "Lock your facts first"} aria-disabled={!available} aria-current={stage===s.id ? "step" : undefined} onClick={()=>navigate(s.id)} className={`stepper-item ${stage===s.id ? "current" : ""}`}>
          {stage===s.id && <motion.span className="stepper-active" layoutId="active-stage" transition={{type:"spring",stiffness:300,damping:30}}/>}<span className="step-number">{done ? <Check size={15}/> : i+1}</span><span className="step-copy"><span><Icon size={16}/>{s.label}</span><small>{!available ? "Locked" : done ? "Done ✓" : (statuses[s.id]?.scope===`${campaign?.id}:${campaign?.revision}` ? statuses[s.id]?.status : null) ?? (stage===s.id ? campaign?.status==="forms_review" && i===1 ? "Needs your review" : "In progress" : "Not started")}</small></span>{!available && <LockKeyhole size={13}/>}</button>;})}<div className="rail-note"><ShieldCheck size={23}/><p>Human controls truth.<br/>Code enforces the boundary.</p><button className="text-xs underline" onClick={()=>setPalette(true)}><Command size={12} className="inline"/> Quick navigation</button></div></nav>}
        <main id="workspace-content" className="workspace-content">
          {hasWorkspace && <header className="stage-header"><div><p className="eyebrow">WORKSPACE / {String(index+1).padStart(2,"0")}</p><h1 id="stage-title" tabIndex={-1}>{active.title}</h1><p>{active.help}</p></div><StatusBadge tone={locked ? "success" : "warning"}>{locked ? "Facts locked" : "Owner review required"}</StatusBadge></header>}
          {error && <div className="callout danger" role="alert"><p>{error}</p><Button variant="secondary" loading={loading} onClick={refresh}>Retry connection</Button></div>}
          <div hidden={kit}>{children}</div>{kit && <UiKit/>}
          {notice && <p className="callout warning" role="status">{notice}</p>}
        </main>
      </div>
      {hasWorkspace && <footer className="stage-footer"><Button variant="ghost" disabled={index===0} onClick={()=>navigate(stages[index-1].id)}><ArrowLeft size={17}/>Back</Button><p role="status">{progress || (locked ? "Locked facts guide every expression." : "Review and lock your facts to unlock the campaign.")}</p>{index===7 ? <span className="hint">Approve and export using the controls above.</span> : <Button disabled={!allowed(stages[Math.min(index+1,7)].id)} title={!allowed(stages[Math.min(index+1,7)].id) ? index===0 ? "Propose your brief first" : "Lock your facts first" : "Next stage"} onClick={()=>navigate(stages[index+1].id)}>Continue<ArrowRight size={17}/></Button>}</footer>}
    </div>
    <Dialog open={palette} onClose={()=>setPalette(false)} title="Go to your workspace"><div className="command-list">{stages.map(s=><Button variant="ghost" key={s.id} disabled={!allowed(s.id)} onClick={()=>{setPalette(false);navigate(s.id);}}>{s.label}<ChevronRight size={16}/></Button>)}<Button variant="ghost" onClick={()=>{setPalette(false);setTraceOpen(true);}}>Open trace</Button><Button variant="ghost" onClick={()=>{setPalette(false);newCampaign();}}>New campaign</Button></div></Dialog>
  </WorkspaceContext.Provider></MotionConfig>;
}
