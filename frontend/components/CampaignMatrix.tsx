"use client";
import ErrorNotice from "./ui/ErrorNotice";
import CopyReadinessNotice from "./CopyReadinessNotice";
import { errorMessage } from "@/lib/error-message";

import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "@/lib/api.generated";
import type { Campaign, Lang } from "@/lib/campaign-api";
import PosterPanel from "./PosterPanel";
import VideoPanel from "./VideoPanel";
import PredictionPanel from "./PredictionPanel";
import { routedWork, WorkFailure } from "@/lib/work-api";
import { Stage, useWorkspace } from "./workspace/WorkspaceShell";
import { CopyButton, EmptyState, StatusBadge, Tabs, ToggleChip } from "./ui";
import LockedText from "./workspace/LockedText";

type Matrix = components["schemas"]["MatrixSnapshot"];
type Plan = components["schemas"]["StrategyPlan"];
type Run = components["schemas"]["GenerationRun"];
type Generate = components["schemas"]["GenerateRequest"];
type Social = Generate["channels"][number];
type Selection = Omit<Generate, "idempotency_key" | "expected_revision">;
const social = (channel: string): channel is Social => ["instagram", "whatsapp", "facebook"].includes(channel);
const active = (run: Run | null | undefined) => run?.status === "queued" || run?.status === "running";

async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const job = body === undefined ? null : routedWork<T>(path, body);
  if (job) return job;
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", signal,
    cache: "no-store", headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(errorMessage(data,"Request failed. Reload saved progress before retrying."));
  return data as T;
}

export default function CampaignMatrix({ campaign, readOnly=false }: { campaign: Campaign; readOnly?:boolean }) {
  const {navigate,recordStage} = useWorkspace();
  const previewKey=`intent-preview:${campaign.id}:${campaign.revision}`;
  const [preview, setPreview] = useState<Social | "poster">(()=>{const stored=typeof window!=="undefined" ? sessionStorage.getItem(previewKey) : null;return stored==="poster" ? "poster" : stored && social(stored) && campaign.channels.includes(stored) ? stored : campaign.channels.filter(social)[0] ?? "whatsapp";});
  const [snapshot, setSnapshot] = useState<Matrix | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [language, setLanguage] = useState<Lang>(campaign.languages[0]);
  const [channel, setChannel] = useState<Social>(preview!=="poster" ? preview : campaign.channels.filter(social)[0] ?? "whatsapp");
  const [audience, setAudience] = useState("all");
  const [busy, setBusy] = useState("");
  const [videoOpen,setVideoOpen]=useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);
  const pendingRequest = useRef<Generate | null>(null);
  const submitting = useRef(false);
  const base = `/api/campaigns/${encodeURIComponent(campaign.id)}`;
  const receive = useCallback((next: Matrix) => {
    setSnapshot(next); setLoaded(true); setError("");
    if (next.strategy) {
      const plan = next.strategy;
      setSelection(old => old?.strategy_id === plan.id ? old : {
        strategy_id: plan.id,
        audience_ids: next.run?.strategy_id === plan.id ? next.run.request.audience_ids : plan.audiences.map(a => a.id),
        languages: next.run?.strategy_id === plan.id ? next.run.request.languages : campaign.languages,
        channels: next.run?.strategy_id === plan.id ? next.run.request.channels : campaign.channels.filter(social),
      });
    }
  }, [campaign.channels, campaign.languages]);

  useEffect(() => {
    const update = () => setReload(v => v + 1);
    window.addEventListener("workflow-update", update);
    return () => window.removeEventListener("workflow-update", update);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Matrix>(`${base}/matrix`, undefined, controller.signal);
        if (controller.signal.aborted) return;
        receive(next);
        if (active(next.run)) timer = setTimeout(() => void poll(), 1500);
      } catch (failure) {
        if (!controller.signal.aborted) {
          setLoaded(true);
          setError(failure instanceof Error ? failure.message : "Cannot load saved matrix.");
        }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [base, receive, reload]);

  const plan = snapshot?.strategy;
  const run = snapshot?.run;
  useEffect(()=>{const scope=`${campaign.id}:${campaign.revision}`;recordStage("brand-strategy",plan ? "Done ✓" : "Not started",scope);recordStage("campaign-matrix",run?.cells.some(c=>c.state==="blocked") ? "Blocked ⚠" : active(run) ? "In progress" : run ? "Needs your review" : "Not started",scope);},[campaign.id,campaign.revision,plan,run,recordStage]);
  const working = readOnly || !!busy || active(run);
  const strategy = async () => {
    setBusy("Planning hypothetical audiences"); setError("");
    try {
      await api<Plan>(`${base}/strategy`, { expected_revision: campaign.revision });
      setReload(v => v + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Planning failed."); }
    finally { setBusy(""); }
  };
  const generate = async () => {
    if (!selection || submitting.current) return;
    submitting.current = true;
    setBusy("Starting generation"); setError(""); navigate("campaign-matrix");
    const next = { ...selection, expected_revision: campaign.revision };
    const previous = pendingRequest.current;
    if (!previous || JSON.stringify({ ...previous, idempotency_key: undefined }) !== JSON.stringify(next)) {
      pendingRequest.current = { ...next, idempotency_key: crypto.randomUUID() };
    }
    try {
      const saved = await api<Run>(`${base}/generate`, pendingRequest.current);
      setSnapshot(old => old ? { ...old, run: saved } : old);
      pendingRequest.current = null;
      setReload(v => v + 1); navigate("campaign-matrix");
    } catch (failure) {
      if (failure instanceof WorkFailure) pendingRequest.current = null;
      setError(failure instanceof Error ? failure.message : "Generation failed.");
      setReload(v=>v+1);
    }
    finally { setBusy(""); submitting.current = false; }
  };
  const reviewCopy = () => {
    if (run) {
      const first = run.request.channels[0];
      setPreview(first); setChannel(first); setLanguage(run.request.languages[0]); setAudience("all");
    }
    navigate("campaign-matrix");
  };
  const retryCopy = async () => {
    if (!run || submitting.current || readOnly || active(run) || run.campaign_revision !== campaign.revision) return;
    submitting.current=true; setBusy("Retrying unfinished copy"); setError("");
    try {
      const saved=await api<Run>(`${base}/generate`, {...run.request,expected_revision:campaign.revision,
        retry_source_run_id:run.id,idempotency_key:crypto.randomUUID()});
      setSnapshot(old=>old?{...old,run:saved}:old);
    } catch(failure) {setError(failure instanceof Error?failure.message:"Copy retry failed.");}
    finally {setBusy("");submitting.current=false;setReload(v=>v+1);}
  };
  const toggle = <K extends "audience_ids" | "languages" | "channels">(key: K, value: Selection[K][number]) => {
    setSelection(old => {
      if (!old) return old;
      const values = old[key] as string[];
      return { ...old, [key]: values.includes(value) ? values.filter(v => v !== value) : [...values, value] };
    });
    pendingRequest.current = null;
  };

  return <><Stage id="brand-strategy"><section id="brand-strategy" className="card space-y-6" aria-labelledby="matrix-heading">
    <details><summary>Brand kit · owner-controlled</summary><div className="grid gap-4 sm:grid-cols-2"><div><p className="eyebrow">TONE & THEME</p><p>{campaign.brand.tone || "Tone not specified"}</p><p className="hint">{campaign.brand.theme || "Theme not specified"}</p></div><div><p className="eyebrow">OWNER-SUPPLIED COLORS</p><div className="flex flex-wrap gap-2">{campaign.brand.colors?.length ? campaign.brand.colors.map(color=><span className="status-badge" key={color}><span className="h-4 w-4 rounded-full border" style={{backgroundColor:color}}/>{color}</span>) : <p className="hint">No brand colors specified.</p>}</div></div><div><p className="eyebrow">MUST NOT SAY</p><div className="flex flex-wrap gap-2">{campaign.brand.must_not_say?.length ? campaign.brand.must_not_say.map(word=><StatusBadge key={word} tone="warning">{word}</StatusBadge>) : <p className="hint">No owner restrictions supplied; Guardian still checks every claim.</p>}</div></div><div><p className="hint">Facts are locked. Brand changes go through the reviewed change workflow.</p><button className="secondary mt-3" onClick={()=>navigate("ledger-changes")}>Review a brand change</button>{run && <button className="secondary mt-3" onClick={()=>{setPreview("poster");navigate("campaign-matrix");}}>Manage reviewed PNG logo</button>}</div></div></details>
    <div><p className="eyebrow">03 / Brand + Strategy</p><h2 id="matrix-heading" className="mt-2 text-2xl font-semibold">A different reason to connect</h2>
      <p className="mt-2 text-sm">Three hypothetical strategies and five simulated personas guide the copy. These are design choices, not customer research. Drafts require semantic review before approval.</p></div>
    {!loaded && <p role="status">Loading saved strategy and matrix…</p>}
    {error && <ErrorNotice message={error}/>}
    <div className="flex flex-wrap gap-3"><button className="secondary" onClick={() => setReload(v => v + 1)}>Reload saved matrix</button>
      {!plan && <button className="primary" disabled={working || !loaded || !campaign.channels.some(social)} onClick={() => void strategy()}>Plan audience strategies</button>}</div>
    {busy && <p role="status">{busy}…</p>}
    {campaign.channels.includes("poster") && <p className="text-sm">Generate social copy first, then prepare its poster sizes below.</p>}


    {plan && <>
      <p className="rounded-xl bg-[#e2e8d9] p-3 text-sm font-semibold">{plan.mode.toUpperCase()} · Hypothetical strategy · Saved personas: {plan.personas.length}</p>
      <div className="grid gap-3 md:grid-cols-3">{plan.audiences.map(a => <article key={a.id} className="strategy-card">
        <h3 className="font-semibold">{a.name}</h3><p className="mt-2">Motivation: {a.motivation}</p><p>Tone: {a.tone}</p><p>Preferred channel: {a.preferred_channel}</p>
        {plan.hero_audience_id === a.id && <p className="status-badge success mt-3">★ Suggested hero audience</p>}
      </article>)}</div>
      <details><summary>Five stable simulated personas</summary><ul className="mt-3 space-y-2">{plan.personas.map((p, i) => <li key={p.id}>Persona {i + 1} · {plan.audiences[p.audience_index]?.name} · {p.priority} · {p.reading_style.replaceAll("_", " ")} · {p.decision_style}</li>)}</ul></details>
      <details><summary>Strategy constraints and notices</summary><ul className="mt-2 list-disc pl-5">{plan.notices.map(n => <li key={n}>{n}</li>)}</ul></details>
      <div><p className="eyebrow">04 / Campaign Matrix</p><h3 className="mt-2 text-xl font-semibold">Choose languages, audiences and channels</h3></div>
      {selection && <fieldset disabled={working} className="space-y-4"><legend className="font-semibold">Select combinations to generate</legend>
        <div className="flex flex-wrap gap-4">{plan.audiences.map(a => <ToggleChip key={a.id} selected={selection.audience_ids.includes(a.id)} onClick={()=>toggle("audience_ids",a.id)}>{a.name}</ToggleChip>)}</div>
        <div className="flex flex-wrap gap-4">{campaign.languages.map(l => <ToggleChip key={l} selected={selection.languages.includes(l)} onClick={()=>toggle("languages",l)}>{l=== "kn" ? "Kannada" : l=== "kn-Latn" ? "Kanglish" : "English"}</ToggleChip>)}</div>
        <div className="flex flex-wrap gap-4">{campaign.channels.filter(social).map(c => <ToggleChip key={c} selected={selection.channels.includes(c)} onClick={()=>toggle("channels",c)}>{c}</ToggleChip>)}</div>
        <p className="callout success">{selection.audience_ids.length} audiences × {selection.languages.length} languages × {selection.channels.length} channels = {selection.audience_ids.length * selection.languages.length * selection.channels.length} variants · one initial copy batch per language; repairs may add calls.</p>
        <button className="primary" disabled={!selection.audience_ids.length || !selection.languages.length || !selection.channels.length} onClick={() => void generate()}>Generate selected matrix</button>
        <p className="text-xs">One batch per language; failed combinations may receive bounded repairs. Successful batches are saved progressively. Starting again creates a new baseline run.</p>
      </fieldset>}
    </>}
    </section></Stage>
    <Stage id="campaign-matrix"><div className="card space-y-5" id="campaign-matrix"><h2 className="sr-only">Campaign previews</h2>
    <button className="secondary" aria-expanded={videoOpen} onClick={()=>setVideoOpen(!videoOpen)}>Saved video drafts</button>
    {videoOpen&&<VideoPanel campaign={campaign} readOnly={readOnly}/>}
    {!run && <EmptyState title="Your matrix is waiting" action={<button className="primary" onClick={()=>navigate("brand-strategy")}>Choose your strategy</button>}>Plan audiences and generate your selected combinations first.</EmptyState>}
    {run && <div className="space-y-4">
      <p role="status" className="font-semibold">{run.mode.toUpperCase()} · Generation {run.status} · {run.cells.filter(c => c.state === "ready").length}/{run.cells.length} drafts ready · {run.calls_used} copy call attempts</p>
      {run.error_code && <p role="alert">{run.error_code} · Saved progress is retained.</p>}
      {!run.cells.some(cell=>cell.state==="ready") && <CopyReadinessNotice run={run}/>}
      {["failed","partial","interrupted","cancelled"].includes(run.status) && <button className="secondary" disabled={readOnly||!!busy||run.campaign_revision!==campaign.revision} onClick={()=>void retryCopy()}>Retry unfinished copy</button>}
      <div className="grid gap-3 sm:grid-cols-2"><label>Preview audience<select className="field" value={audience} onChange={e => setAudience(e.target.value)}><option value="all">All selected audiences</option>{plan?.audiences.filter(a => run.request.audience_ids.includes(a.id)).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>Preview language<select className="field" value={language} onChange={e => setLanguage(e.target.value as Lang)}>{campaign.languages.map(l => <option key={l}>{l}</option>)}</select></label></div>
      <div className="matrix-tiles" aria-label="Audience and language matrix">{plan?.audiences.filter(a=>run.request.audience_ids.includes(a.id)).flatMap(a=>run.request.languages.map(l=>{const cells=run.cells.filter(c=>c.audience_id===a.id && c.language===l);return <button key={`${a.id}:${l}`} className={`matrix-tile ${audience===a.id && language===l ? "active" : ""}`} aria-pressed={audience===a.id && language===l} onClick={()=>{setAudience(a.id);setLanguage(l);}}><strong>{a.name}</strong><small>{l} · {cells.filter(c=>c.state==="ready").length}/{cells.length} ready{cells.some(c=>c.state==="blocked") ? " · ⚠ blocked" : ""}</small></button>;}))}</div>
      <Tabs label="Preview channel" value={preview} options={[...campaign.channels.filter(social).map(value=>({value,label:value==="whatsapp" ? "WhatsApp" : value[0].toUpperCase()+value.slice(1)})),{value:"poster" as const,label:"Poster"}]} onChange={v=>{setPreview(v);sessionStorage.setItem(previewKey,v);if(v!=="poster")setChannel(v);}}/>
      <div hidden={preview==="poster"} className="space-y-4">
      {!run.cells.some(c => c.language === language && c.channel === channel) && <p>This language/channel combination was not selected for this run.</p>}
      <div className="grid gap-4 lg:grid-cols-3">{run.cells.filter(c => c.language === language && c.channel === channel && (audience === "all" || c.audience_id === audience)).map(cell => {
        const variant = cell.variant;
        const rendered = variant?.report.rendered?.fields;
        return <article key={`${cell.audience_id}:${cell.language}:${cell.channel}`} className={`device-preview ${channel}`}>
          <StatusBadge tone={cell.state === "blocked" ? "danger" : cell.state === "ready" ? "success" : "warning"}>{cell.channel} · {cell.state} · {run.mode}</StatusBadge><h3 className="mt-2 font-semibold">{plan?.audiences.find(a => a.id === cell.audience_id)?.name ?? "Historical audience"}</h3>
          {cell.state === "queued" || cell.state === "running" ? <p className="mt-4">{cell.state === "queued" ? "Waiting for this language batch." : "Generating or repairing this draft…"}</p> : null}
          {(cell.reasons ?? []).length > 0 && <p className="mt-3 break-words text-sm">{(cell.reasons ?? []).join(", ")}</p>}
          {rendered && <div lang={cell.language} className="customer-copy mt-5 space-y-3 break-words"><p className="text-xl font-semibold"><LockedText text={rendered.headline} field="headline" rendered={variant!.report.rendered!}/></p><p className="whitespace-pre-wrap"><LockedText text={rendered.body} field="body" rendered={variant!.report.rendered!}/></p><p className="font-semibold"><LockedText text={rendered.cta} field="cta" rendered={variant!.report.rendered!}/></p>{Object.entries(rendered).filter(([key]) => key.startsWith("hashtags.")).map(([key, text]) => <span className="mr-2 text-sm" key={key}>{text}</span>)}<p className="text-xs">Alt text: {rendered.alt_text}</p></div>}
          {!rendered && cell.state === "blocked" && <p className="mt-3">No valid preview returned. See the recorded reasons; no replacement copy was fabricated.</p>}
          {variant && <details className="mt-4 text-sm"><summary>Guardian {variant.report.status} · {variant.slots_used.length} derived slots</summary><p className="mt-2">Pending: {variant.report.missing_checks.join(", ") || "none"}</p><ul>{variant.report.checks.filter(c => c.passed === false).map(c => <li key={c.rule}>{c.rule}: {c.severity} — {(c.findings ?? []).map(f => f.message).join("; ")}</li>)}</ul><p>Warnings: {variant.report.warning_ids.join(", ") || "none"}</p></details>}
          {rendered && <CopyButton label="Copy draft text" value={Object.values(rendered).filter(Boolean).join("\n")}/>}
          <p className="mt-4 text-xs">Draft only · not approved · no posting or export</p>
        </article>;
      })}</div>
      <details><summary>All requested combinations and repair history</summary><ul className="mt-2 space-y-1 text-sm">{run.cells.map(cell => <li key={`${cell.audience_id}:${cell.language}:${cell.channel}`}>{plan?.audiences.find(a => a.id === cell.audience_id)?.name ?? cell.audience_id} · {cell.language} · {cell.channel}: {cell.state}{(cell.attempts ?? []).map(a => ` · attempt ${a.attempt}: ${a.reasons.join(", ") || "valid draft"}`).join("")}</li>)}</ul></details>
      </div><div hidden={preview!=="poster"}><PosterPanel key={run.id} campaign={campaign} readOnly={readOnly} run={run} onReviewCopy={reviewCopy}/></div>
    </div>}
  </div></Stage><Stage id="prediction">{run ? <PredictionPanel key={`prediction-${run.id}`} campaign={campaign} readOnly={readOnly} matrix={run} plan={plan} onReviewCopy={reviewCopy}/> : <EmptyState title="No score yet" action={<button className="primary" onClick={()=>navigate("brand-strategy")}>Generate a baseline</button>}>Predictions need actual generated variants. Missing judgments stay unscored.</EmptyState>}</Stage></>;
}
