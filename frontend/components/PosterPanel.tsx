/* eslint-disable @next/next/no-img-element -- display exact saved PNG bytes without transformations */

"use client";

import ErrorNotice from "./ui/ErrorNotice";
import CopyReadinessNotice from "./CopyReadinessNotice";

import { errorMessage } from "@/lib/error-message";

import { useCallback, useEffect, useState } from "react";

import type { components } from "@/lib/api.generated";

import type { Campaign } from "@/lib/campaign-api";

import { ToggleChip, Skeleton } from "./ui";

import { routedWork, submitWork } from "@/lib/work-api";

type Run = components["schemas"]["GenerationRun"];

type Art = components["schemas"]["ArtSnapshot"];

type Poster = components["schemas"]["PosterArtifact"];

type Audit = components["schemas"]["Audit"];

type Size = components["schemas"]["RenderRequest"]["size"];

const sizes: [Size, string][] = [["feed", "1080 × 1350 · Instagram 4:5"], ["square", "1080 × 1080"], ["story", "1080 × 1920"], ["landscape", "1200 × 630"]];

async function read<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {

  const job = body === undefined ? null : routedWork<T>(path, body);

  if (job) return job;

  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", signal,

    headers: { "Content-Type": "application/json" }, cache: "no-store", body: body === undefined ? undefined : JSON.stringify(body) });

  const data = await response.json();

  if (!response.ok) throw new Error(errorMessage(data,"Poster preparation failed."));

  return data as T;

}

export default function PosterPanel({ campaign, run, readOnly=false, onReviewCopy }: { campaign: Campaign; run: Run; readOnly?:boolean; onReviewCopy?:()=>void }) {

  const [art, setArt] = useState<Art | null>(null);

  const [variantId, setVariantId] = useState("");
  const [providerArtEnabled, setProviderArtEnabled] = useState<boolean | null>(null);
  const [imageNotice,setImageNotice] = useState("");

  const [chosen, setChosen] = useState<Size[]>(["feed", "square", "story"]);

  const [source, setSource] = useState<"provider" | "deterministic">("provider");

  const [logoId, setLogoId] = useState("");

  const [file, setFile] = useState<File | null>(null);

  const [reviewed, setReviewed] = useState(false);

  const [busy, setBusy] = useState("");

  const [error, setError] = useState("");

  const [refresh, setRefresh] = useState(0);

  const [audits, setAudits] = useState<Record<string, Audit>>({});

  const base = `/api/campaigns/${encodeURIComponent(campaign.id)}`;

  const available = run.campaign_revision === campaign.revision && run.status !== "stale"
    ? run.cells.filter(c => c.state === "ready" && c.variant && c.variant.report.status !== "BLOCKED") : [];

  const currentId = available.find(c => c.variant!.id === variantId)?.variant?.id || available[0]?.variant?.id;

  const reload = useCallback(async () => setArt(await read<Art>(`${base}/assets`)), [base]);

  useEffect(() => {

    const update = () => setRefresh(v => v + 1);

    window.addEventListener("workflow-update", update);

    return () => window.removeEventListener("workflow-update", update);

  }, []);

  useEffect(() => {

    const controller = new AbortController();

    void read<Art>(`${base}/assets`, undefined, controller.signal).then(value => {

      if (!controller.signal.aborted) setArt(value);

    }).catch(failure => { if (!controller.signal.aborted) setError(failure.message); });
    void read<{mode:string;image_generation_enabled?:boolean;image_configuration_notice?:string}>("/api/ready", undefined, controller.signal)
      .then(value=>{if(!controller.signal.aborted){setProviderArtEnabled(value.image_generation_enabled ?? value.mode==="MOCK");setImageNotice(value.image_configuration_notice||"");}})
      .catch(()=>{if(!controller.signal.aborted)setProviderArtEnabled(false);});

    return () => controller.abort();

  }, [base, refresh]);

  const render = async () => {

    if (!currentId) return;

    setError("");

    try {

      setBusy("Preparing durable poster batch · progress and cancellation above");

      await submitWork(campaign.id, "poster_batch", { expected_revision: campaign.revision,

        variant_id: currentId, sizes: chosen, source, logo_id: logoId || null });

      await reload();

    } catch (failure) { setError(failure instanceof Error ? failure.message : "No valid poster was returned."); }

    finally { setBusy(""); }

  };

  const upload = async () => {

    if (!file || !reviewed) return;

    setBusy("Validating owner-reviewed logo"); setError("");

    try {

      const response = await fetch(`${base}/logos?expected_revision=${campaign.revision}&owner_approves_logo=true`, {

        method: "POST", headers: { "Content-Type": file.type }, body: file });

      const data = await response.json();

      if (!response.ok) throw new Error(data.message ?? "Logo validation failed.");

      setLogoId(data); setReviewed(false); setFile(null); await reload();

    } catch (failure) { setError(failure instanceof Error ? failure.message : "Logo upload failed."); }

    finally { setBusy(""); }

  };

  const posters = art?.posters.filter(p => p.variant_id === currentId && p.status !== "stale") ?? [];

  const historical = art?.posters.filter(p => p.variant_id === currentId && p.status === "stale") ?? [];

  const audit = async (poster: Poster) => {

    setBusy("Reading exact rendered poster text"); setError("");

    try {

      const value = await submitWork<Audit>(campaign.id, "poster_audit", { expected_revision: campaign.revision }, poster.id);

      setAudits(old => ({ ...old, [poster.id]: value }));

    } catch (failure) { setError(failure instanceof Error ? failure.message : "Poster audit unavailable."); }

    finally { setBusy(""); }

  };

  return <section aria-labelledby="poster-heading" className="space-y-5 border-t border-[#cbd1c3] pt-6">

    <div><p className="eyebrow">Saved poster drafts</p><h3 id="poster-heading" className="mt-2 text-xl font-semibold">The same pixels, from preview to file</h3>

      <p className="mt-2 text-sm">Modern café posters: textured cream paper, forest-green brush accents, a bold mustard offer and a coffee hero on the right. AI artwork uses photography; local artwork stays labeled as illustration. Social captions stay separate. Every new poster needs its own audit and approval.</p></div>

    {error && <ErrorNotice message={error}/>}
    {!available.length && <CopyReadinessNotice run={run} onReview={onReviewCopy}/>}
    {providerArtEnabled===false && <p role="status">{imageNotice||"AI artwork is unavailable for the configured endpoint."} Choose Local coffee illustration to render without an image-provider call.</p>}

    {busy && <><p role="status">{busy}…</p><Skeleton/></>}

    <fieldset disabled={readOnly || !!busy} className="grid gap-4 sm:grid-cols-2"><legend className="font-semibold">Poster preparation</legend>

      <label>Poster copy<select className="field mt-2" value={currentId ?? ""} onChange={e => setVariantId(e.target.value)}>

        {!available.length && <option value="">No validated copy — review generation</option>}

        {available.map(c => <option key={c.variant!.id} value={c.variant!.id}>{c.language} · {c.channel} · {c.variant!.template.headline}</option>)}

      </select></label>

      <label>Background source<select className="field mt-2" value={source} onChange={e => setSource(e.target.value as typeof source)}><option value="provider" disabled={providerArtEnabled!==true}>AI-generated café artwork{providerArtEnabled===false ? " · unavailable" : ""}</option><option value="deterministic">Local coffee illustration · no AI call</option></select></label>

      <div className="space-y-2">{sizes.map(([size, name]) => <ToggleChip key={size} selected={chosen.includes(size)} onClick={()=>setChosen(chosen.includes(size) ? chosen.filter(s=>s!==size) : [...chosen,size].slice(-3))}>{name}</ToggleChip>)}</div>

      <label>Approved logo<select className="field mt-2" value={logoId} onChange={e => setLogoId(e.target.value)}><option value="">No logo · optional</option>{art?.logos.map(id => <option key={id} value={id}>{id.slice(0, 12)}</option>)}</select></label>

      <button className="primary" disabled={!currentId || !chosen.length || run.status === "stale" || (source==="provider" && providerArtEnabled!==true)} onClick={() => void render()}>Render selected poster sizes</button>

      <button className="secondary" onClick={() => setRefresh(v => v + 1)}>Reload saved posters</button>

    </fieldset>

    {logoId && <img className="logo-preview" src={`/api/assets/${logoId}`} alt="Owner-reviewed stored PNG logo"/>}

    <details><summary>Use your reviewed PNG logo</summary><div className="mt-3 space-y-3">

      <label className="block">Logo PNG · maximum 2MB<input type="file" accept="image/png" disabled={readOnly || !!busy} className="field mt-2" onChange={e => { setFile(e.target.files?.[0] ?? null); setReviewed(false); }} /></label>

      <label className="flex items-start gap-2"><input type="checkbox" disabled={readOnly || !!busy} checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I reviewed this logo and approve its exact content for this business.</label>

      <button className="secondary" disabled={readOnly || !!busy || !file || !reviewed} onClick={() => void upload()}>Store reviewed logo</button>

      <p className="text-xs">SVG and animated files are rejected. Logo review is recorded separately; final campaign approval still requires semantic review.</p>

    </div></details>

    <details><summary>Background provenance and QA</summary><ul className="mt-3 space-y-2 text-sm">{art?.backgrounds.map(background => <li key={background.id}>

      {background.ratio} · {background.provenance.toUpperCase()} · {background.status} · {background.calls_used} call attempts

      {background.qa && <> · R9 {background.qa.recommendation}: {background.qa.evidence.join("; ")}</>}

      {(background.reasons ?? []).length > 0 && <> · {(background.reasons ?? []).join(", ")}</>}
      {(background.reasons ?? []).includes("VISION_UNSUPPORTED") && <div className="mt-2"><p className="font-semibold">Unapproved generated draft · visual QA unavailable · cannot export as approved</p><img className="max-h-72 max-w-full rounded-lg" src={`/api/backgrounds/${background.id}/unapproved.png`} alt="Unapproved generated artwork awaiting visual QA"/></div>}

    </li>)}</ul></details>

    {!posters.length && <p className="text-sm">No saved poster for this copy yet. Choose sizes and render to create actual files.</p>}

    {historical.length > 0 && <details><summary>{historical.length} previous poster designs · historical</summary>

      <p className="mt-2 text-sm">These files use earlier facts or layouts. Render again for the current cream-and-green café design, then audit and approve the new files.</p>

    </details>}

    <div className="grid items-start gap-5 lg:grid-cols-3">{posters.map(poster => <article className="min-w-0 rounded-xl border border-[#cbd1c3] p-3" key={poster.id}>

      <p className="text-xs font-bold">{poster.width} × {poster.height} · {poster.status} · {poster.copy_provenance.toUpperCase()} copy</p>

      <img style={{aspectRatio:`${poster.width}/${poster.height}`}} className="mt-3 h-auto w-full rounded-xl" src={`/api/assets/${poster.id}`} alt={poster.render_input.fields.alt_text || "Campaign poster draft"} />

      <p className="mt-3 text-xs">Background: {poster.provenance.toUpperCase()} · Measured layout: {poster.validation.passed ? "passed" : "blocked"}</p>

      <a className="mt-3 inline-block font-semibold underline" href={`/api/assets/${poster.id}`} download={`draft-${poster.id}.png`}>Download draft PNG</a>

      <button className="secondary mt-3" disabled={readOnly || !!busy || poster.status !== "ready"} onClick={() => void audit(poster)}>Audit rendered poster text</button>

      {audits[poster.id] && <div className="mt-3 text-xs"><p>Blinded R7: {audits[poster.id].status} · persisted audit {audits[poster.id].id}</p><p>Exact rendered-text provenance · remote vision NOT_TESTED</p><p>Review warnings: {audits[poster.id].warning_ids.join(", ") || "none"}</p>{audits[poster.id].findings.map((finding,index) => <p key={index}>{finding}</p>)}<ul>{(audits[poster.id].measured_features ?? []).map(feature => <li key={feature.name}>{feature.name}: {feature.applicable ? feature.value ?? "unavailable" : "excluded"} · {feature.measurement}</li>)}</ul></div>}

      <details className="mt-3 text-xs"><summary>Exact artifact and review status</summary><p className="mt-2 break-all">SHA-256: {poster.sha256}</p><p>{poster.byte_count} bytes · Contrast {poster.validation.contrast.toFixed(2)}:1</p><p>Guardian {poster.guardian.status} · Pending {poster.guardian.missing_checks.join(", ")}</p></details>

      <p className="mt-3 text-xs">Draft · final approval/export pending · Native review pending</p>

    </article>)}</div>

  </section>;

}
