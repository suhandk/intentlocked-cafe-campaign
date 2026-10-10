"use client";
import {useWorkspace} from "./workspace/WorkspaceShell";
import ErrorNotice from "./ui/ErrorNotice";
import CopyReadinessNotice from "./CopyReadinessNotice";
import CountUp from "./ui/CountUp";
import { errorMessage } from "@/lib/error-message";
import { useEffect, useRef, useState } from "react";
import type { components } from "@/lib/api.generated";
import type { Campaign } from "@/lib/campaign-api";
import { routedWork, submitWork } from "@/lib/work-api";

type Run = components["schemas"]["OptimizationRun"];
type Snapshot = components["schemas"]["OptimizationSnapshot"];
type MatrixRun = components["schemas"]["GenerationRun"];
type Plan = components["schemas"]["StrategyPlan"];
type Group = Run["groups"][number];
type Poster = components["schemas"]["PosterArtifact"];
function bandLabel(score:Group["current_score"]) {if(score.overall===null || !score.sensitivity_band || score.sensitivity_band.length!==2)return "Sensitivity band unavailable";const [low,high]=score.sensitivity_band;const minus=score.overall-low,plus=high-score.overall;return `${Math.abs(minus-plus)<.05 ? `±${minus.toFixed(1)}` : `−${minus.toFixed(1)} / +${plus.toFixed(1)}`} · ${low.toFixed(1)}–${high.toFixed(1)} · simulated sensitivity`;}
const active = (run: Run) => ["queued", "running"].includes(run.status);
const reasonText = (reason: string) => reason === "SIX_WEIGHTED_WINS_FEATURE_DROP_LT3_STRICT_GAIN_ZERO_BLOCK"
  ? "Accepted: six weighted wins, limited feature decrease, strict score gain and no blocking finding."
  : reason.replaceAll("_", " ").toLowerCase();

async function api<T>(path: string, body?: unknown): Promise<T> {
  const job = body === undefined ? null : routedWork<T>(path, body);
  if (job) return job;
  const response = await fetch(path, { method: body ? "POST" : "GET", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const value = await response.json();
  if (!response.ok) throw new Error(errorMessage(value,"Cannot load optimization progress."));
  return value as T;
}

function Trajectory({ group }: { group: Group }) {
  const baseline = group.baseline_score.overall;
  if (baseline === null) return <p role="status">Trajectory unavailable until the baseline has complete score evidence.</p>;
  const scored = (group.rounds ?? []).filter(round => round.score?.overall != null);
  const count = Math.max((group.rounds ?? []).length, 1);
  const x = (round: number) => 48 + round * 430 / count;
  const y = (score: number) => 190 - score * 1.5;
  const points = (group.rounds ?? []).reduce<number[][]>((previous, round) => [
    ...previous,
    [round.number, round.accepted && round.score?.overall != null
      ? round.score.overall : previous[previous.length - 1][1]],
  ], [[0, baseline ?? 0]]);
  return <div className="overflow-hidden rounded-xl border border-[#cbd1c3] p-3">
    <svg viewBox="0 0 520 230" role="img" aria-label="Trajectory against the frozen original baseline; rejected scores do not replace the retained score" className="w-full">
      {[0, 50, 100].map(value => <g key={value}><line x1="48" x2="485" y1={y(value)} y2={y(value)} stroke="#d7ddd2" /><text x="8" y={y(value)+5} fontSize="12">{value}</text></g>)}
      {baseline != null && <line x1="48" x2="485" y1={y(baseline)} y2={y(baseline)} stroke="#ac5a2a" strokeDasharray="5 5" />}
      <polyline points={points.map(([round, score]) => `${x(round)},${y(score)}`).join(" ")} fill="none" stroke="#233d31" strokeWidth="3" />
      {scored.map(round => <g key={round.number}><circle cx={x(round.number)} cy={y(round.score!.overall!)} r="5" fill={round.accepted ? "#233d31" : "#a44629"} /><text x={x(round.number)} y="212" textAnchor="middle" fontSize="12">Round {round.number}</text></g>)}
      <text x="48" y="212" fontSize="12">Original</text>
    </svg>
    <p className="text-xs">Green: retained selection · red: rejected candidate · dashed: frozen baseline. Original tournament uses the declared 50 self-reference convention.</p>
  </div>;
}

export default function PredictionPanel({ campaign, matrix, plan, readOnly=false, onReviewCopy }: { campaign: Campaign; matrix: MatrixRun; plan: Plan | null | undefined; readOnly?:boolean; onReviewCopy?:()=>void }) {
  const {recordStage}=useWorkspace();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [language, setLanguage] = useState(campaign.languages[0]);
  const [audienceId, setAudienceId] = useState(plan?.hero_audience_id ?? matrix.request.audience_ids[0]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [posters, setPosters] = useState<Record<string, Poster>>({});
  const pending = useRef<{ expected_revision: number; variant_ids: string[]; idempotency_key: string } | null>(null);
  const submitting = useRef(false);
  const base = `/api/campaigns/${encodeURIComponent(campaign.id)}`;
  useEffect(() => {
    const update = () => setReload(v => v + 1);
    window.addEventListener("workflow-update", update);
    return () => window.removeEventListener("workflow-update", update);
  }, []);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Snapshot>(`${base}/optimization`);
        if (stopped) return;
        setSnapshot(next); setError("");
        if (next.runs.some(active)) timer = setTimeout(() => void poll(), 1200);
      } catch (failure) { if (!stopped) setError(failure instanceof Error ? failure.message : "Cannot load scores."); }
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [base, reload]);
  useEffect(()=>recordStage("prediction",snapshot?.runs.some(active) ? "In progress" : snapshot?.runs.length ? "Needs your review" : "Not started",`${campaign.id}:${campaign.revision}`),[campaign.id,campaign.revision,snapshot,recordStage]);
  const selected = matrix.campaign_revision === campaign.revision && matrix.status !== "stale"
    ? matrix.cells.filter(cell => cell.state === "ready" && cell.language === language && cell.audience_id === audienceId && cell.variant && cell.variant.report.status !== "BLOCKED").map(cell => cell.variant!.id) : [];
  const selectedAudience = plan?.audiences.find(audience => audience.id === audienceId);
  const working = readOnly || busy || !!snapshot?.runs.some(active);
  const start = async () => {
    if (submitting.current || !selected.length || matrix.campaign_revision !== campaign.revision) return;
    submitting.current = true;
    setBusy(true); setError("");
    const ids = JSON.stringify(selected);
    if (!pending.current || pending.current.expected_revision !== campaign.revision || JSON.stringify(pending.current.variant_ids) !== ids) pending.current = { expected_revision: campaign.revision, variant_ids: selected, idempotency_key: crypto.randomUUID() };
    try {
      await api<Run>(`${base}/optimize`, pending.current);
      pending.current = null;
      setReload(value => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Cannot start optimization."); }
    finally { setBusy(false); submitting.current = false; }
  };
  const renderRetained = async (group: Group) => {
    setBusy(true); setError("");
    try {
      const batch = await submitWork<{posters: Poster[]}>(campaign.id, "poster_batch", {expected_revision: campaign.revision,
        variant_id: group.current_id, sizes: ["square"], source: "deterministic"});
      const poster = batch.posters[0];
      setPosters(old => ({ ...old, [group.current_id]: poster }));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Retained draft could not be rendered."); }
    finally { setBusy(false); }
  };
  return <section id="prediction" className="mt-6 min-w-0 space-y-5 break-words border-t border-[#cbd1c3] pt-6" aria-labelledby="prediction-heading">
    <div><p className="eyebrow">Prediction + bounded optimization</p><h2 id="prediction-heading" className="mt-2 text-2xl font-semibold">Choose with evidence</h2><p className="mt-2 text-sm">Predicted preference (simulated personas + rules), not a CTR forecast. Improvement is not guaranteed.</p></div>
    <div className="flex flex-wrap items-end gap-3"><label>Audience group<select className="field" value={audienceId} onChange={event=>setAudienceId(event.target.value)} disabled={working}>{plan?.audiences.map(audience=><option key={audience.id} value={audience.id}>{audience.name}{audience.id===plan.hero_audience_id ? " · suggested hero" : ""}</option>)}</select></label><label>Hero language<select className="field" value={language} onChange={event => setLanguage(event.target.value as typeof language)} disabled={working && !readOnly}>{campaign.languages.map(lang => <option key={lang}>{lang}</option>)}</select></label><button className="primary" disabled={working || !selected.length || !snapshot || matrix.status === "stale"} onClick={() => void start()}>{audienceId===plan?.hero_audience_id ? "Optimize hero group" : "Optimize selected group"}</button><button className="secondary" onClick={() => setReload(value => value + 1)}>Reload saved trajectory</button></div>
    <p className="text-xs">Optimizes {selected.length} validated channel(s) for {selectedAudience?.name ?? "the selected audience"}. Maximum three rounds, or two in DEMO_FAST mode. Each candidate is verified before its two judge batches.</p>
    {!selected.length && <CopyReadinessNotice run={matrix} onReview={onReviewCopy}/>}
    {error && <ErrorNotice message={error}/>}
    {!snapshot && <p role="status">Loading persisted score evidence…</p>}
    {snapshot && <p className="text-sm">{snapshot.unscored_variant_ids.length} current variants have not been evaluated. Hero scores never populate other groups.</p>}
    {snapshot?.runs.map(run => <article key={run.id} className="space-y-4 rounded-xl bg-[#eef2e5] p-4">
      <p role="status" className="font-semibold">{run.mode.toUpperCase()} · Optimization {run.status} · {run.phase}</p>
      <p className="text-sm">{run.calls_used}/{run.max_calls} inference attempts · {run.mock_calls} mock · {run.steps_used}/{run.max_steps} steps · {(run.elapsed_ms/1000).toFixed(1)}s elapsed · ${run.known_cost_usd.toFixed(6)} known estimate · {run.unknown_cost_calls} unknown-cost calls</p>
      <p className="text-xs">Stop: {run.stop_reason ?? "running"} · Deadline {run.deadline_at} · Personas frozen {run.persona_hash.slice(0,12)} · Baseline frozen {run.baseline_hash.slice(0,12)}. Actual billing remains unknown.</p>
      {run.groups.map(group => <div key={group.baseline.id} className="space-y-3 rounded-xl bg-white p-4">
        <h3 className="font-semibold">{group.baseline.language} · {group.baseline.channel} · {group.stop_reason ?? "in progress"}</h3>
        <div className="kpi-grid"><div className="kpi-card"><small>ORIGINAL BASELINE</small><strong>{group.baseline_score.overall!==null ? <CountUp value={group.baseline_score.overall}/> : "Unscored"}</strong></div><div className="kpi-card"><small>RETAINED SELECTION</small><strong>{group.current_score.overall!==null ? <CountUp value={group.current_score.overall}/> : "Unscored"}</strong><small>{bandLabel(group.current_score)}</small></div></div>
        <Trajectory group={group} />
        <details><summary>Feature details and score formula</summary><p className="mt-2 text-sm">Overall = 0.5 × applicable-feature mean + 0.5 × tournament. Tournament = 100 × (wins + half ties) / 10. Missing votes leave the tournament and overall unscored.</p><ul className="mt-3 space-y-2 text-sm">{group.current_score.features.map(feature => <li key={feature.name}><strong>{feature.name.replaceAll("_", " ")}: {feature.applicable ? feature.value ?? "unavailable" : "excluded"}</strong> · {feature.measurement}{feature.applicable && feature.value!==null && <div className="score-bar"><span style={{width:`${feature.value}%`}}/></div>}</li>)}</ul><p className="mt-3 text-sm">Sensitivity: {group.current_score.sensitivity_band?.map(value => value.toFixed(1)).join("–") ?? "not available"} · order disagreements {group.current_score.order_disagreement}/5. Simulated judge sensitivity; not a confidence interval.</p></details>
        <details><summary>Retained customer copy · awaiting owner approval</summary><div lang={group.baseline.language} className="mt-3 space-y-2">{Object.entries(group.final_audit?.guardian.rendered?.fields ?? {}).map(([field, text]) => <p key={field}><strong>{field}:</strong> {text}</p>)}</div></details>
        <button className="secondary" disabled={working || run.status !== "completed" || run.campaign_revision !== campaign.revision || group.final_audit?.status !== "PASS"} onClick={() => void renderRetained(group)}>Render retained square draft</button>
        {posters[group.current_id] && <a className="block text-sm underline" href={`/api/assets/${posters[group.current_id].id}`} download={`retained-draft-${posters[group.current_id].id}.png`}>Download exact retained draft PNG · owner approval pending</a>}
        <p className="text-sm">Final blinded audit: {group.final_audit?.status ?? "PENDING"} · review warnings: {group.final_audit?.warning_ids.join(", ") || "none"}. Native Kannada review and owner export approval remain separate gates.</p>
        {group.final_audit?.findings.map((finding, index) => <p className="text-sm" key={index}>{finding}</p>)}
        <ol className="space-y-3">{(group.rounds ?? []).map(round => <li key={round.number} className="timeline-item">
          <p className="font-semibold">{(round.calls ?? []).some(c => c.provenance === "cache") ? "CACHED evidence · " : ""}Round {round.number} · {round.accepted ? "✓ Accepted" : "✕ Rejected / no change"} · {round.score?.overall?.toFixed(1) ?? "unscored"}</p><p className="mt-1 text-sm">{round.critique}</p><p className="text-xs">{(round.reasons ?? []).map(reasonText).join("; ")} · {(round.elapsed_ms/1000).toFixed(1)}s</p>
          <details className="mt-2"><summary>Permitted edits, verification, judgments and provenance</summary><ul className="mt-2 text-sm">{(round.edits ?? []).map(edit => <li key={edit.target}>{edit.target}: {edit.value}</li>)}</ul><p className="mt-2 text-sm">Guardian {round.guardian?.status ?? "not executed"} · R7 {round.audit?.status ?? "not executed"} · weighted wins {round.score?.weighted_wins ?? "not judged"}/10 · complete judgments {round.score?.complete_judgments ?? 0}/10</p><ul className="mt-2 space-y-1 text-xs">{round.score?.votes.map(vote => <li key={`${vote.persona_id}:${vote.order}`}>{vote.persona_id.slice(-3)} {vote.order}: {vote.outcome} · {vote.reason}</li>)}</ul><ul className="mt-2 space-y-1 text-xs">{(round.calls ?? []).map((call,index) => <li className="break-all" key={index}>{call.role} · {call.provenance} (source {call.source_mode}) · {call.model} · captured {call.captured_at} · cache {call.cache_key.slice(0,12)} · {call.call_ids.length} transport records{call.error_code ? ` · ${call.error_code}` : ""}</li>)}</ul></details>
        </li>)}</ol>
      </div>)}
    </article>)}
  </section>;
}
