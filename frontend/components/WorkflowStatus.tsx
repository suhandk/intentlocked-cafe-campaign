"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useWorkspace } from "./workspace/WorkspaceShell";
import { type WorkSnapshot, workRead } from "@/lib/work-api";

const labels: Record<string, string> = { queued: "◷ Queued", running: "◷ Working", completed: "✓ Completed · review required", partial: "! Partially completed", failed: "! Failed", stale: "! Earlier revision", cancelled: "■ Cancelled", interrupted: "! Interrupted" };

export default function WorkflowStatus({ campaign, saved, onSaved }: { campaign: string; saved: boolean; onSaved: (value: boolean) => void }) {
  const {setProgress,setElapsed,setTraceOpen} = useWorkspace();
  const [paused,setPaused] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const [snapshot, setSnapshot] = useState<WorkSnapshot>();
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<{ id: number; timestamp: string; message: string }[]>([]);
  const [capture, setCapture] = useState("");
  const [savedExport, setSavedExport] = useState("");
  const [reload, setReload] = useState(0);
  const retryKeys = useRef<Record<string, string>>({});
  const previousSignature = useRef("");
  useEffect(() => {
    let stopped = false;
    const refresh = async () => {
      try { const next = await workRead<WorkSnapshot>(`/api/campaigns/${campaign}/work`); if (!stopped) {
        setSnapshot(next); setPollError("");
        const signature = JSON.stringify(next.jobs.map(j => [j.id, j.status, j.updated_at, j.calls]));
        if (previousSignature.current !== signature) { previousSignature.current = signature; window.dispatchEvent(new CustomEvent("workflow-update", {detail: {campaign, source: "poll"}})); }
      } }
      catch (e) { if (!stopped) setPollError(e instanceof Error ? e.message : "Cannot load saved jobs."); }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    const listener = (event: Event) => { if ((event as CustomEvent).detail?.source !== "poll") void refresh(); };
    window.addEventListener("workflow-update", listener);
    const cursorKey = `intent-stream-${campaign}`;
    const cursor = Number(sessionStorage.getItem(cursorKey) ?? 0);
    const source = new EventSource(`/api/stream/${campaign}?after=${Number.isFinite(cursor) ? cursor : 0}`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("workflow", (raw) => {
      const event = JSON.parse((raw as MessageEvent).data);
      sessionStorage.setItem(cursorKey, String(event.id));
      setEvents(old => old.some(v => v.id === event.id) ? old : [...old, event].slice(-30));
      window.dispatchEvent(new CustomEvent("workflow-update", { detail: { campaign, event } }));
    });
    return () => { stopped = true; source.close(); clearInterval(timer); window.removeEventListener("workflow-update", listener); };
  }, [campaign, reload]);
  useEffect(()=>{setElapsed(snapshot?.jobs[0]?.elapsed_seconds ?? null);const job=snapshot?.jobs.find(j=>["running","queued"].includes(j.status));setProgress(job ? `${job.kind.replaceAll("_"," ")} · ${job.completed_steps}/${job.max_steps} steps · ${Math.floor(job.elapsed_seconds)}s elapsed` : "");},[snapshot,setProgress,setElapsed]);
  useEffect(()=>{if(!paused)end.current?.scrollIntoView({block:"nearest"});},[events,paused]);
  const initialSaved = useRef("");
  const switchSaved = useCallback(async () => {
    try {
      const next = await workRead<WorkSnapshot>(`/api/campaigns/${campaign}/saved-output`);
      const captureJob = next.jobs.find(j => ["completed", "partial"].includes(j.status) && j.result && ["generate", "optimize", "poster_batch", "render"].includes(j.kind));
      const delivery = await workRead<{campaign_revision: number; items: {id: string; status: string}[]}>(`/api/campaigns/${campaign}/delivery`);
      const approved = delivery.items.filter(i => i.status === "approved");
      setSavedExport(approved.length ? `/api/campaigns/${campaign}/export.zip?expected_revision=${delivery.campaign_revision}&saved_view=true&${approved.map(i => `item_ids=${i.id}`).join("&")}` : "");
      setCapture(`Captured ${captureJob?.updated_at} · source ${captureJob?.mode.toUpperCase()} · fact revision ${captureJob?.campaign_revision} · ${captureJob?.provider ?? "original provider unknown"} · persisted prompts and artifacts`);
      onSaved(true); setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "No saved output is available."); }
  },[campaign,onSaved]);
  useEffect(()=>{if(!saved){initialSaved.current="";return;}if(initialSaved.current===campaign)return;initialSaved.current=campaign;void switchSaved();},[campaign,saved,switchSaved]);
  return <aside className="card mb-6 space-y-4" aria-label="Work and recovery">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold">Work and recovery</h3><span className="text-sm">{connected ? "✓ Progress connected" : "! Reconnecting progress · saved state still polled"}</span></div>
    <p className="mode-banner" role="status">{saved ? "SAVED DEMO OUTPUT · CACHED VIEW · read only" : `${snapshot?.mode.toUpperCase() ?? "Loading mode"} · current workspace`}{saved && <span className="mt-1 block text-xs">{capture}</span>}</p>
    <div className="flex flex-wrap gap-3">{saved ? <button className="primary" onClick={() => onSaved(false)}>Return to current workspace</button> : <button className="secondary" disabled={!!snapshot?.active || !!snapshot?.queued} onClick={() => void switchSaved()}>Switch explicitly to saved output</button>}<button className="secondary" onClick={() => setReload(v => v + 1)}>Reconnect and reload jobs</button></div>
    {saved && <p className="text-sm">CACHED · {savedExport ? <a className="underline" href={savedExport}>Download authorized saved ZIP and manifest</a> : "No approved saved outputs are available to export. Return to the current workspace to audit and approve."} The server checks current approvals again; pending or stale output cannot export.</p>}
    {error && <p role="alert">! {error}</p>}
    {pollError && <p role="alert">! {pollError}</p>}
    {!snapshot && !pollError && <p role="status">Loading durable work…</p>}
    {snapshot && <p className="text-sm">{snapshot.active}/{snapshot.concurrency_limit} worker slots · {snapshot.queued} queued. Estimates vary with provider latency and Retry-After. List prices are estimates; actual billing is unknown. Mock costs are excluded.</p>}
    {snapshot && !snapshot.jobs.length && <p className="text-sm">No jobs yet. Start with the brief below; work will stay saved here.</p>}
    <ul className="space-y-2">{snapshot?.jobs.slice(0, 8).map(job => <li className="rounded-xl border border-[#d3d8cd] p-3 text-sm" key={job.id}>
      <div className="flex flex-wrap items-center justify-between gap-3"><strong>{labels[job.status]} · {job.kind.replaceAll("_", " ")}</strong><span>{saved ? "CACHED · " : ""}{job.mode.toUpperCase()} · revision {job.campaign_revision}</span></div>
      <p>{Math.floor(job.elapsed_seconds)}s elapsed · {job.completed_steps}/{job.max_steps} steps · {job.calls}/{job.max_calls} calls · ${job.list_price_estimate_usd.toFixed(5)} list price{job.unknown_cost_calls > 0 ? ` · ${job.unknown_cost_calls} costs unknown` : ""}{job.queue_position > 0 ? ` · queue #${job.queue_position} · about ${Math.ceil(job.estimated_wait_seconds)}s wait` : ""}</p>
      {job.error_code && <p>Stop reason: {job.error_code}. Review saved outputs before retrying the matching action below.</p>}
      {job.notices?.map(notice => <p className="mt-1 font-semibold" key={notice}>! {notice}</p>)}
      {!!job.cache_hits?.length && <p>CACHED / reused persisted output · {job.cache_hits.map(s => s.split(" · ")[0]).join(", ")} · original source remains {job.mode.toUpperCase()}</p>}
      {["running", "queued"].includes(job.status) && <button className="secondary mt-2" onClick={() => void workRead(`/api/work/${job.id}/cancel`, {}).then(() => {setError("");setReload(v => v + 1);}).catch(e => setError(e.message))}>Cancel {job.kind.replaceAll("_", " ")}</button>}
      {!saved && job.kind === "forms" && ["failed", "interrupted", "cancelled", "partial"].includes(job.status) && <button className="secondary mt-2" onClick={() => {window.dispatchEvent(new CustomEvent("workspace-review-forms", {detail:{campaign}})); setTraceOpen(false);}}>Review facts to retry wording</button>}
      {!saved && !["video", "forms"].includes(job.kind) && ["failed", "interrupted", "cancelled", "partial"].includes(job.status) && <button className="secondary mt-2" onClick={() => { retryKeys.current[job.id] ??= crypto.randomUUID(); void workRead(`/api/work/${job.id}/retry`, { expected_revision: job.campaign_revision, idempotency_key: retryKeys.current[job.id] }).then(() => {setError("");setReload(v => v + 1);}).catch(e => setError(e.message)); }}>Retry unfinished {job.kind.replaceAll("_", " ")}</button>}
    </li>)}</ul>
    <details open><summary>Technical trace drawer · actions and decisions</summary><button className="secondary" onClick={()=>setPaused(v=>!v)}>{paused ? "Resume auto-scroll" : "Pause auto-scroll"}</button><ul className="mt-3 space-y-2 text-xs">{events.length ? events.map(event => <li key={event.id}>{new Date(event.timestamp).toLocaleTimeString()} · {event.message}</li>) : <li>No new events in this connection. Saved job status is authoritative.</li>}</ul><div ref={end}/><details><summary>Raw event JSON</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(events,null,2)}</pre></details></details>
  </aside>;
}
