"use client";
import ErrorNotice from "./ui/ErrorNotice";
import ManualPublishingPanel from "./ManualPublishingPanel";
import { errorMessage } from "@/lib/error-message";
import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import type { components } from "@/lib/api.generated";
import { campaignApi, type Campaign } from "@/lib/campaign-api";
import { Stage, useWorkspace } from "./workspace/WorkspaceShell";
import { Dialog, StatusBadge, Tabs } from "./ui";
import { Check, LockKeyhole, TriangleAlert } from "lucide-react";
import { VoiceInput } from "./VoiceInput";
import { routedWork, submitWork, WorkFailure, type Work } from "@/lib/work-api";
type Snapshot = components["schemas"]["DeliverySnapshot"];
type Proposal = components["schemas"]["Proposal"];
type Forms = components["schemas"]["FactSurface"][];
type Pack = components["schemas"]["ExportPack"];
type RedTeam = components["schemas"]["RedTeamResult"];

function readableFact(value: string): string {
  try {
    const envelope = JSON.parse(value);
    if (envelope === null || ("canonical" in envelope && envelope.canonical === null)) return "Unspecified · remains unknown";
    const fact = envelope.canonical ?? envelope;
    const canonical = fact.kind === "percent_off" ? `${fact.value}% off` : fact.kind === "unspecified" ? "Unspecified · remains unknown" : Object.entries(fact).filter(([key]) => key !== "kind").map(([key, v]) => `${key.replaceAll("_", " ")}: ${Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
    const forms = envelope.surface ?? envelope.proposed_surface;
    if (!forms) return canonical;
    const words = Object.entries(forms).map(([language, cases]) => `${language}: ${(cases as {nom?: string[]}).nom?.join(" / ") ?? "pending review"}`).join(" · ");
    return `${canonical} · ${words || "new forms await proposal and review"}`;
  } catch { return value; }
}

async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const job = method === "POST" && body !== undefined ? routedWork<T>(`/api${path}`, body) : null;
  if (job) return job;
  const response = await fetch(`/api${path}`, { method, cache: "no-store", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(`${errorMessage(result,"Request failed")}${response.status === 409 ? " Reload and review the current revision." : ""}`);
  return result as T;
}

export default function DeliveryPanel({ campaign, onPublished, saved = false }: { campaign: Campaign; onPublished: (next: Campaign) => void; saved?: boolean }) {
  const {navigate,recordStage} = useWorkspace();
  const [reviewOpen, setReviewOpen] = useState(false);
  const root = `/campaigns/${campaign.id}`;
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [proposal, setProposal] = useState<Proposal>();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"instruct_ai" | "edit_copy">("instruct_ai");
  const [result, setResult] = useState<RedTeam>();
  const [forms, setForms] = useState<Forms>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [formsApproved, setFormsApproved] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [review, setReview] = useState({proof:"", warnings:[] as string[], native:false, owner:false});
  const [history, setHistory] = useState<Snapshot["versions"][number]>();
  const [pack, setPack] = useState<Pack>();
  const [packProof,setPackProof] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const guarded = useRef(false);
  const key = useRef("");
  const failedJob = useRef<Work | null>(null);
  const load = useCallback(async () => {
    const next = await api<Snapshot>(`${root}/delivery`);
    setSnapshot(next);
    const failure = failedJob.current;
    if (failure?.kind === "item_audit" && failure.campaign_id === campaign.id && failure.campaign_revision === next.campaign_revision) {
      const item = next.items.find(i => i.id === failure.target_id);
      if (item?.audit_status === "PASS" && !item.approval_blockers?.length) {
        failedJob.current = null; setError(""); setMessage("Customer audit recovered. Review warnings and approve the current item.");
      }
    }
  }, [root, campaign.id]);
  useEffect(() => {
    const update = () => { void load().catch((e: Error) => setError(e.message)); };
    window.addEventListener("workflow-update", update);
    return () => window.removeEventListener("workflow-update", update);
  }, [load]);
  useEffect(() => { void api<Snapshot>(`${root}/delivery`).then(setSnapshot).catch((e: Error) => setError(e.message)); }, [root]);
  async function work(label: string, action: () => Promise<void>) {
    if (guarded.current) return;
    guarded.current = true; setBusy(label); setError(""); setMessage("");
    try { await action(); await load(); }
    catch (e) { failedJob.current = e instanceof WorkFailure ? e.job : null; setError(e instanceof Error ? e.message : "Request failed"); }
    finally { guarded.current = false; setBusy(""); }
  }
  function receive(p: Proposal) { setProposal(p); setReviewOpen(p.classification === "immutable" && p.status === "proposed"); setForms(p.forms ?? []); setConfirmed(false); setFormsApproved(false); }
  useEffect(()=>{const scope=`${campaign.id}:${campaign.revision}`;recordStage("ledger-changes",proposal && ["proposed","confirmed","forms_review"].includes(proposal.status) ? "Needs your review" : snapshot?.ledger.length ? "Done ✓" : "Not started",scope);recordStage("approve-export",snapshot?.items.some(i=>i.status==="blocked") ? "Blocked ⚠" : snapshot?.items.length ? snapshot.items.every(i=>i.status==="approved") ? "Done ✓" : "Needs your review" : "Not started",scope);},[campaign.id,campaign.revision,proposal,snapshot,recordStage]);
  const chosen = (snapshot?.campaign_revision === campaign.revision ? snapshot.items : []).filter((i) => selected.includes(i.id));
  const outputProof = JSON.stringify([campaign.id,campaign.revision,saved,chosen.map(i=>[i.id,i.snapshot_hash])]);
  const reviewProof = JSON.stringify([campaign.id,campaign.revision,chosen.map(i=>[i.id,i.snapshot_hash,i.audit_id,i.warnings,i.approval_blockers])]);
  const currentReview = review.proof === reviewProof ? review : {warnings:[] as string[],native:false,owner:false};
  const {warnings,native,owner} = currentReview;
  const updateReview = (patch: Partial<typeof currentReview>) => setReview({...currentReview,...patch,proof:reviewProof});
  const setOwner = (value:boolean) => updateReview({owner:value});
  const setNative = (value:boolean) => updateReview({native:value,owner:false});
  const setWarnings = (value:string[]) => updateReview({warnings:value,owner:false});
  const warningIds = Array.from(new Set(chosen.flatMap((i) => i.warnings ?? [])));
  const selectionQuery = chosen.map((item) => `item_ids=${encodeURIComponent(item.id)}`).join("&");
  const exportQuery = `expected_revision=${campaign.revision}&${selectionQuery}&saved_view=${saved}`;
  const blockCount=chosen.reduce((n,item)=>n+item.report.checks.filter(c=>c.completed && c.passed===false && c.severity==="BLOCK").length,0);
  const approvalReason = busy ? "Wait for the current action to finish." : !chosen.length ? "Select current items to review." : chosen.some(i=>i.approval_blockers?.length) ? `Approval blocked: ${chosen.flatMap(i=>i.approval_blockers ?? []).join(" ")}` : blockCount ? `Approval blocked: ${blockCount} Guardian violations` : chosen.some(i=>["blocked","regeneration_required"].includes(i.status)) ? "Approval blocked: selected items need correction or regeneration." : chosen.some(i=>i.audit_status!=="PASS") ? "Approval blocked: customer audit must pass; an absent G14 result is not passed." : warningIds.some(id=>!warnings.includes(id)) ? "Acknowledge the displayed warnings." : chosen.some(i=>i.variant.language!=="en") && !native ? "Complete native Kannada/Kanglish review of these exact items." : !owner ? "Confirm approval of the exact selected content and bytes." : "";
  const exportReason = !chosen.length ? "Select approved items to export." : chosen.some(i=>i.approval_blockers?.length) ? "Export blocked: current content or dependencies need correction and fresh review." : chosen.some(i=>i.status!=="approved") ? "Export blocked: every selected item needs current owner approval." : "";
  const authorizedPack = pack && packProof === outputProof && chosen.length > 0 && chosen.every(i=>i.status === "approved" && !i.approval_blockers?.length) && ((pack.mode === "cached") === saved) ? pack : undefined;
  const immutable = proposal?.classification === "immutable" && proposal.status === "proposed";
  const proposalContent = proposal && <div className="space-y-3">
        <h3 className="font-semibold">{proposal.classification} proposal · {proposal.status}</h3>
        {(proposal.questions ?? []).map((q) => <p key={q}>{q}</p>)}
        {proposal.diffs.map((diff) => <div key={diff.target} className="min-w-0 space-y-2 border-b pb-3"><StatusBadge tone="warning">{diff.target} · {diff.consequence}</StatusBadge><div className="grid gap-3 sm:grid-cols-2"><div className="rounded-xl bg-[#eef2e5] p-3"><p className="eyebrow">BEFORE</p><p className="break-words text-sm">Before: {readableFact(diff.before)}</p></div><div className="rounded-xl bg-[#f6ead4] p-3"><p className="eyebrow">PROPOSED</p><p className="break-words text-sm">Proposed: {readableFact(diff.after)}</p></div></div><p className="text-xs">{diff.affected_ids.length} affected item(s). Scores/audits and relevant approvals will need review; unrelated approvals remain valid.</p></div>)}
        {proposal.status === "proposed" && <><label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I confirm this exact diff and its scope.</label><button className="primary" disabled={saved || !!busy || !confirmed} onClick={() => work("Confirming diff", async () => {receive(await api<Proposal>(`${root}/change/confirm`, "POST", { expected_revision: campaign.revision, proposal_id: proposal.id, decision: "confirm", idempotency_key: `confirm-${proposal.id}` }));setReviewOpen(false);})}>Confirm diff</button></>}
        {["proposed", "confirmed", "forms_review"].includes(proposal.status) && <button className="secondary" disabled={saved || !!busy} onClick={() => work("Cancelling proposal", async () => {receive(await api<Proposal>(`${root}/change/confirm`, "POST", { expected_revision: campaign.revision, proposal_id: proposal.id, decision: "cancel", idempotency_key: `cancel-${proposal.id}` }));setReviewOpen(false);})}>Cancel whole proposal</button>}
  </div>;
  return <div className="space-y-6"><Stage id="ledger-changes">
    <section id="ledger-changes" className="card min-w-0 space-y-4" aria-label="Ledger and changes">
      <p className="eyebrow">Ledger + Changes / Current revision {campaign.revision}</p>
      <h2 className="text-2xl font-semibold">Review a change before it becomes truth</h2>
      <p className="text-sm">R8 proposes. You confirm the diff and new forms. Code publishes all parts together. Pending proposals have not changed current facts.</p>
      <label className="block">Change scope<select className="field mt-1" aria-label="Change scope" value={selected.length === 1 ? selected[0] : ""} onChange={(e) => setSelected(e.target.value ? [e.target.value] : [])}><option value="">All current items</option>{snapshot?.items.map((i) => <option key={i.id} value={i.id}>{i.variant.language} · {i.variant.channel} · {i.kind} · {i.id.slice(0, 8)}</option>)}</select></label>
      <label className="block">Owner change request<textarea className="field mt-1" maxLength={2000} value={text} onChange={(e) => { setText(e.target.value); key.current = ""; }} placeholder="Make it 15% and tone calm" /></label><details><summary>Speak a change instead</summary><VoiceInput value={text} disabled={saved || !!busy} onChange={value=>{setText(value);key.current="";}}/></details>
      <div className="flex flex-wrap gap-3"><button className="primary" disabled={saved || !!busy || !text.trim()} onClick={() => work("Proposing change", async () => { key.current ||= crypto.randomUUID(); receive(await api<Proposal>(`${root}/change`, "POST", { expected_revision: campaign.revision, text, scope_ids: selected, idempotency_key: key.current })); })}>Propose change</button><button className="secondary" disabled={saved || !!busy} onClick={() => work("Reloading", load)}>Reload changes and approvals</button></div>
      {proposal && <div className="space-y-3 rounded-xl border border-[#c9d0c3] p-4">
        {immutable ? <><button className="primary" onClick={()=>setReviewOpen(true)}><LockKeyhole size={16}/>Review immutable fact change</button><Dialog open={reviewOpen} onClose={()=>setReviewOpen(false)} title="Confirm the change to locked truth"><fieldset disabled={saved}>{proposalContent}</fieldset></Dialog></> : proposalContent}
        {proposal.status === "confirmed" && (proposal.changed_keys.length > 0 || proposal.candidate.languages.join() !== campaign.languages.join()) && <button className="primary" disabled={saved || !!busy} onClick={() => work("Proposing forms", async () => receive(await api<Proposal>(`${root}/change/${proposal.id}/surface`, "POST", { expected_revision: campaign.revision })))}>Propose changed forms</button>}
        {proposal.status === "forms_review" && <div className="grid gap-3 md:grid-cols-2">{forms.map((form, index) => <fieldset key={form.key} className="min-w-0 rounded-lg border p-3"><legend>{form.key}</legend>{Object.entries(form.surface).map(([language, cases]) => cases && Object.entries(cases).filter(([, values]) => values).map(([grammaticalCase, values]) => <label className="mt-2 block text-sm" key={`${language}-${grammaticalCase}`}>{language} {grammaticalCase}<input aria-label={`Changed ${form.key} ${language} ${grammaticalCase}`} className="field mt-1" value={values?.join(" | ") ?? ""} onChange={(e) => { setForms(forms.map((f, n) => n !== index ? f : { ...f, surface: { ...f.surface, [language]: { ...cases, [grammaticalCase]: e.target.value.split("|").map((v) => v.trim()) } } })); setFormsApproved(false); }} /></label>))}</fieldset>)}</div>}
        {(proposal.status === "forms_review" || (proposal.status === "confirmed" && proposal.changed_keys.length === 0 && proposal.candidate.languages.join() === campaign.languages.join())) && <><label className="flex gap-2"><input type="checkbox" checked={formsApproved} onChange={(e) => setFormsApproved(e.target.checked)} />I approve the diff and all displayed new forms for publication.</label><button className="primary" disabled={saved || !!busy || !formsApproved} onClick={() => work("Publishing revision", async () => { await api<Proposal>(`${root}/change/publish`, "POST", { expected_revision: campaign.revision, proposal_id: proposal.id, reviewed_forms: forms, approve_diff_and_forms: true, idempotency_key: `publish-${proposal.id}` }); onPublished(await campaignApi(`/${campaign.id}`)); })}>Publish reviewed revision</button></>}
      </div>}
      <details><summary>Saved proposals, events and version history</summary><div className="mt-3 space-y-2">{snapshot?.proposals.map((p) => <button className="secondary mr-2" key={p.id} onClick={() => receive(p)}>{p.classification} · {p.status} · revision {p.expected_revision}</button>)}{snapshot?.versions.map((v) => <button className="secondary mr-2" key={v.revision} onClick={() => setHistory(v)}>View {v.current ? "current" : "historical"} revision {v.revision}</button>)}{history && <div className="rounded-lg bg-[#f4ead7] p-3"><p className="font-semibold">{history.current ? "Current snapshot" : "Historical snapshot — not current, cannot export as current"}</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(history.campaign.facts, null, 2)}</pre></div>}<pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(snapshot?.ledger, null, 2)}</pre></div></details>
    </section>
    </Stage><Stage id="guardian"><section className="card space-y-3" aria-label="Red-Team">
      <h2 className="text-xl font-semibold">Guardian + Red-Team</h2><Tabs label="Red-Team mode" value={mode} onChange={value=>{setMode(value);setResult(undefined);}} options={[{value:"instruct_ai",label:"Instruct the AI"},{value:"edit_copy",label:"Edit the copy directly"}]}/><label className="block">Adversarial request or copy<textarea aria-label="Adversarial request or copy" className="field mt-2" value={text} maxLength={2000} onChange={e=>{setText(e.target.value);key.current="";setResult(undefined);}}/></label><p className="text-sm">Uses the owner request above. “Make it 25%” proposes a fact edit in instruction mode; unapproved 25% copy is blocked in copy mode. Unsupported promises remain blocked/rejected.</p><button className="secondary" disabled={saved || !!busy || !text.trim()} onClick={() => work("Testing red-team request", async () => { const r = await api<RedTeam>(`${root}/red-team`, "POST", { expected_revision: campaign.revision, mode, text, language: campaign.languages[0], idempotency_key: crypto.randomUUID() }); setResult(r); if (r.proposal) {receive(r.proposal);navigate("ledger-changes");} })}>Run selected Red-Team mode</button>{result && <p key={`${result.mode}:${result.report?.status}`} role="status" className={`verdict ${result.report?.status === "BLOCKED" ? "block" : ""}`}>{result.mode === "instruct_ai" ? `Proposal: ${result.proposal?.classification} · ${result.proposal?.status}` : `Guardian: ${result.report?.status} · ${(result.report?.checks.filter((c) => c.passed === false).map((c) => c.rule) ?? []).join(", ")}`}</p>}
    </section>
    </Stage><Stage id="approve-export"><section id="approve-export" className="card space-y-4" aria-label="Approve and export">
      <h2 className="text-2xl font-semibold">Approve + Export</h2><p className="text-sm">Select exact current items. Run the customer audit, review warnings and approve. Downloads and WhatsApp drafts require server authorization. Mock output stays labeled.</p>
      <div className="grid gap-3 sm:grid-cols-3">{[["Facts locked",campaign.status==="locked"],["No selected Guardian BLOCKs",!!chosen.length && blockCount===0 && !chosen.some(i=>i.status==="blocked")],["Customer audit passed",!!chosen.length && chosen.every(i=>i.audit_status==="PASS" && !i.approval_blockers?.length)]].map(([label,passed])=><div className="callout" key={String(label)}>{passed ? <Check size={17}/> : <TriangleAlert size={17}/>}<span>{String(label)} · {passed ? "Passed" : !chosen.length && label !== "Facts locked" ? "Select items" : "Pending / blocked"}</span></div>)}</div>
      <button className="secondary" disabled={saved || !!busy || !snapshot?.items.some(i=>i.status==="approved" && !i.approval_blockers?.length)} onClick={()=>work("Retrieving approved final output",async()=>{const items=(snapshot?.items ?? []).filter(i=>i.status==="approved" && !i.approval_blockers?.length);setSelected(items.map(i=>i.id));setPack(undefined); setPackProof(JSON.stringify([campaign.id,campaign.revision,saved,items.map(i=>[i.id,i.snapshot_hash])]));const query=items.map(i=>`item_ids=${encodeURIComponent(i.id)}`).join("&");setPack(await api<Pack>(`${root}/export?expected_revision=${campaign.revision}&${query}&saved_view=${saved}`));})}>Show approved final output</button>
      {!snapshot?.items.length && <p>No current outputs. Generate a baseline first.</p>}
      {snapshot?.items.map((item) => <article key={item.id} className="min-w-0 space-y-2 rounded-xl border border-[#d3d8cd] p-4"><label className="flex gap-2"><input type="checkbox" checked={selected.includes(item.id)} onChange={(e) => { setSelected(e.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id)); setOwner(false); setPack(undefined); }} /><strong>{item.variant.language} · {item.variant.channel} · {item.kind} · {item.status}</strong></label><p className="text-xs">{item.mode.toUpperCase()} · created revision {item.created_revision} · audit {item.audit_status ?? "NOT_RUN"} · {item.approval_id ? "Owner approval recorded" : "Pending owner approval"}</p><pre className="whitespace-pre-wrap break-words text-sm">{Object.values(item.fields).filter(Boolean).join("\n")}</pre>{item.kind === "poster" && <Image unoptimized width={1080} height={1080} className="h-auto w-auto max-h-80 max-w-full rounded-lg" src={`/api/assets/${item.poster_id}`} alt="Persisted campaign poster draft" />}<ul className="space-y-1 text-sm">{(item.approval_blockers ?? []).map(reason=><li className="callout danger" key={reason}>{reason} Reload current outputs or rerender changed posters before approval.</li>)}{(item.audit_findings ?? []).map((finding,index)=><li key={index}>{finding}</li>)}</ul>{item.audit_status === "PENDING" && <p className="text-sm">Customer audit is incomplete. Review the evidence issue below, then explicitly retry this item.</p>}{item.audit_status === "BLOCKED" && <p className="text-sm">Customer expectations differ from locked facts. Correct the copy or regenerate it before approval.</p>}{item.kind === "poster" && !!item.approval_blockers?.length && <button className="secondary" onClick={()=>navigate("campaign-matrix")}>Review and regenerate posters</button>}<button className="secondary" disabled={saved || !!busy || !!item.approval_blockers?.length || ["blocked", "regeneration_required"].includes(item.status)} onClick={() => work("Auditing customer expectations", async () => { await api(`${root}/delivery/${item.id}/audit`, "POST", { expected_revision: campaign.revision }); setOwner(false); })}>Audit this item</button>{item.kind === "text" && item.variant.campaign_revision === campaign.revision && item.variant.parent_id && <button className="secondary ml-2" disabled={saved || !!busy || item.status === "blocked"} onClick={() => work("Rendering changed square", async () => { await submitWork(campaign.id, "poster_batch", { expected_revision: campaign.revision, variant_id: item.variant.id, sizes: ["square"], source: "deterministic" }); })}>Render changed square draft</button>}{item.status === "regeneration_required" && <p>Regenerate compatible copy or rerender the changed template; this historical item cannot export as current.</p>}</article>)}
      {warningIds.map((id) => <label className="flex gap-2" key={id}><input type="checkbox" checked={warnings.includes(id)} onChange={(e) => setWarnings(e.target.checked ? [...warnings, id] : warnings.filter((w) => w !== id))} />I acknowledge review warning: {id}</label>)}
      {chosen.some((i) => i.variant.language !== "en") && <label className="flex gap-2"><input type="checkbox" disabled={saved} checked={native} onChange={(e) => setNative(e.target.checked)} />I have completed native Kannada/Kanglish review of these exact items.</label>}
      <label className="flex gap-2"><input type="checkbox" disabled={saved || !!busy} checked={owner} onChange={(e) => setOwner(e.target.checked)} />I approve the exact selected current content and poster bytes.</label><div className="flex flex-wrap gap-3"><button className="primary" title={approvalReason || "Approve exact selected items"} disabled={saved || !!approvalReason || !!busy || !chosen.length || !owner || chosen.some((i) => i.audit_status !== "PASS" || ["blocked", "regeneration_required"].includes(i.status)) || warningIds.some((id) => !warnings.includes(id)) || (chosen.some((i) => i.variant.language !== "en") && !native)} onClick={() => work("Approving exact items", async () => { await api(`${root}/approve`, "POST", { expected_revision: campaign.revision, item_ids: chosen.map(i=>i.id), observed_hashes: Object.fromEntries(chosen.map((i) => [i.id, i.snapshot_hash])), acknowledged_warning_ids: warnings, native_review_confirmed: native, owner_approves: true, idempotency_key: crypto.randomUUID() }); setMessage("Owner approval saved. Retrieving authorized final output…"); setPack(undefined); setPackProof(outputProof); setPack(await api<Pack>(`${root}/export?${exportQuery}`)); setMessage("Approved final output is ready below."); })}>Approve selected items</button><button className="secondary" disabled={saved || !!busy || !chosen.length || chosen.some((i) => i.status !== "approved" || i.approval_blockers?.length)} onClick={() => work("Authorizing export", async () => { setPack(undefined); setPackProof(outputProof); setPack(await api<Pack>(`${root}/export?${exportQuery}`)); })}>Authorize selected export</button></div>
      {approvalReason && <p className="callout warning" role="status">{approvalReason}</p>}{exportReason && <p className="hint">{exportReason}</p>}
      <details><summary>What customers are told · final fact review</summary><div className="grid gap-3 sm:grid-cols-2">{campaign.facts.filter(f=>["OFFER","PRODUCT","DATES","DAYS","LOCATION","ELIGIBILITY"].includes(f.key)).map(f=><div className="rounded-xl border p-3" key={f.key}><strong>{f.key}</strong><p>{f.surface?.en?.nom?.join(" / ") ?? "Not specified"}</p></div>)}</div></details>
      {pack && packProof === outputProof && chosen.every(i=>i.status === "approved" && !i.approval_blockers?.length) && ((pack.mode === "cached") === saved) && <div className="space-y-3 rounded-xl bg-[#edf2e6] p-4"><p>{pack.mode.toUpperCase()} · Authorized revision {pack.campaign_revision}</p><p>{pack.disclaimer}</p>{Object.entries(pack.copy_text).map(([id, copy]) => <div className="space-y-2" key={id}><p className="text-sm font-semibold">{pack.files.find(f=>f.item_id===id)?.language} · {pack.files.find(f=>f.item_id===id)?.channel} · Approved description / poster text</p><textarea readOnly className="field" aria-label="Authorized copy" value={copy} onFocus={e=>e.currentTarget.select()} /><button className="secondary" onClick={() => work("Copying authorized text", async () => { try { await navigator.clipboard.writeText(copy); setMessage("Copied approved text."); } catch { throw new Error("Clipboard unavailable. Select the approved description and use Ctrl+C / Command+C, or download the approved text file."); } })}>Copy approved text</button>{pack.whatsapp_drafts[id] && <a className="secondary ml-2" href={pack.whatsapp_drafts[id]} target="_blank" rel="noopener noreferrer">Open WhatsApp draft</a>}</div>)}{pack.files.filter(f=>f.filename.endsWith(".png")).map(f=><Image key={`preview-${f.item_id}`} unoptimized width={1080} height={1350} className="h-auto max-h-96 w-auto max-w-full rounded-lg" src={f.artifact_url!} alt={`Approved ${f.language} ${f.channel} poster`} />)}{pack.files.map((f) => <a key={f.item_id} className="export-tile" href={f.artifact_url ?? `/api${root}/export/files/${encodeURIComponent(f.item_id)}?expected_revision=${campaign.revision}&saved_view=${saved}`}>{f.filename.endsWith(".png") ? "Download approved poster separately" : "Download approved text"}</a>)}<a className="export-tile" href={`${root.replace("/campaigns", "/api/campaigns")}/export.zip?${exportQuery}`}>Download authorized ZIP and manifest</a><details><summary>Authorized manifest and approved hashes</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(pack, null, 2)}</pre></details></div>}
    </section>
    {authorizedPack && Array.from(new Set(chosen.map(i=>i.variant.channel === "poster" ? "instagram" : i.variant.channel))).map(platform=><a key={platform} className="secondary inline-block" href={`/calendar?campaign=${encodeURIComponent(campaign.id)}&revision=${campaign.revision}&platform=${platform}&${chosen.filter(i=>i.variant.channel===platform || (i.kind==="poster" && i.variant.channel==="poster")).map(i=>`item_ids=${encodeURIComponent(i.id)}`).join("&")}`}>Plan a manual {platform} post with approved output</a>)}
    <ManualPublishingPanel key={campaign.id} pack={authorizedPack} />
    </Stage>
    {busy && <p role="status">{busy}…</p>}{error && <ErrorNotice message={error}/>}{message && <p role="status">{message}</p>}
  </div>;
}
