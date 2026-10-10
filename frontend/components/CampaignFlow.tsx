"use client";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { campaignApi, type Campaign, type Canonical, type Channel, type DraftRequest, type Fact, type Lang, type LockRequest } from "@/lib/campaign-api";
import { FactEditor, factNames } from "./FactEditor";
import { Readback, VoiceInput } from "./VoiceInput";
import GuardianPanel from "./GuardianPanel";
import CampaignMatrix from "./CampaignMatrix";
import WebsiteWizard from "./WebsiteWizard";
import DeliveryPanel from "./DeliveryPanel";
import WorkflowStatus from "./WorkflowStatus";
import BrandDraftEditor from "./BrandDraftEditor";
import {WorkFailure, workRead} from "@/lib/work-api";
import { Stage, useWorkspace } from "./workspace/WorkspaceShell";
import { Button, CopyButton, Dialog, Tabs, ToggleChip } from "./ui";
import { ArrowRight, AudioLines, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";

const example = "Café name: Namma Cafe. Bengaluru. 20 percent off coffee this weekend for students.";
const languages: [Lang, string][] = [["en", "English"], ["kn", "Kannada"], ["kn-Latn", "Kanglish"]];
const channels: Channel[] = ["whatsapp", "instagram", "facebook", "poster"];
type FactMap = Partial<Record<Fact["key"], Canonical | null>>;

export default function CampaignFlow({ inferenceDisabled = false }: { inferenceDisabled?: boolean }) {
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [transcript, setTranscript] = useState("");
  const [selectedLanguages, setLanguages] = useState<Lang[]>(["en"]);
  const [selectedChannels, setChannels] = useState<Channel[]>(["whatsapp"]);
  const [facts, setFacts] = useState<FactMap>({});
  const [target, setTarget] = useState("");
  const [tone, setTone] = useState("");
  const [brandDraft,setBrandDraft]=useState<Campaign["brand"]>({tone:"",theme:"",colors:[],must_say:[],must_not_say:[]});
  const [forms, setForms] = useState<LockRequest["forms"]>([]);
  const [acks, setAcks] = useState<string[]>([]);
  const [canonicalConfirmed, setCanonicalConfirmed] = useState(false);
  const [formsConfirmed, setFormsConfirmed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [intentFailed, setIntentFailed] = useState(false);
  const [formsFailed, setFormsFailed] = useState(false);
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState(false);
  const lockKey = useRef("");
  const workspace = useWorkspace();
  const {setCampaign: publishCampaign, navigate, started, start, traceOpen, setTraceOpen, traces} = workspace;
  const [formLanguage, setFormLanguage] = useState<Lang>("en");
  const [factTab, setFactTab] = useState<"canonical" | "forms">("canonical");
  const [savedId, setSavedId] = useState("");
  const [advance, setAdvance] = useState<"facts-lock" | "brand-strategy" | null>(null);
  useEffect(() => { publishCampaign(campaign); }, [campaign, publishCampaign]);
  useEffect(() => { if (advance && workspace.campaign?.revision === campaign?.revision && workspace.campaign?.id === campaign?.id) { const timer = window.setTimeout(() => { navigate(advance); setAdvance(null); }, 0); return () => window.clearTimeout(timer); } }, [advance, campaign, workspace.campaign, navigate]);
  const receive = useCallback((next: Campaign) => {
    setCampaign(next); setTranscript(next.transcript); setLanguages(next.languages); setChannels(next.channels);
    setFacts(Object.fromEntries(next.facts.map((fact) => [fact.key, fact.canonical])));
    setTarget(next.target_audiences.join(", ")); setTone(next.brand.tone ?? ""); setBrandDraft(next.brand);
    setForms(next.facts.filter((fact) => fact.canonical).map((fact) => ({ key: fact.key, surface: fact.surface ?? {} })));
    setAcks(next.acknowledged_warning_ids); setDirty(false); setCanonicalConfirmed(false); setFormsConfirmed(false);
    localStorage.setItem("intent-locked-campaign", next.id);
    const url = new URL(window.location.href); url.searchParams.set("campaign", next.id); window.history.replaceState({}, "", url);
    lockKey.current = crypto.randomUUID();
  }, []);
  useEffect(() => {
    const id = new URL(window.location.href).searchParams.get("campaign") ?? localStorage.getItem("intent-locked-campaign");
    if (id) void campaignApi(`/${encodeURIComponent(id)}`).then(receive).catch(() => setError("Could not load the saved campaign. Retry loading or start a new draft."));
  }, [receive]);
  const locked = campaign?.status === "locked";
  const reviewBusy=!!busy || saved || inferenceDisabled;
  const transcriptChanged = !!campaign && transcript !== campaign.transcript;
  const latestReview = useRef({campaign, dirty, transcriptChanged, busy, saved});
  useLayoutEffect(() => { latestReview.current = {campaign, dirty, transcriptChanged, busy, saved}; }, [campaign, dirty, transcriptChanged, busy, saved]);
  useEffect(() => {
    const update = (raw: Event) => {
      const detail = (raw as CustomEvent).detail;
      if (!campaign || (detail?.source !== "poll" && detail?.event?.event !== "completed")) return;
      void campaignApi(`/${campaign.id}`).then(next => {
        const current = latestReview.current;
        if (current.saved || !current.campaign || next.id !== current.campaign.id || next.revision <= current.campaign.revision) return;
        if (current.dirty || current.transcriptChanged || current.busy) setMessage("Saved campaign changed. Your edits stay on screen; reload and review the current revision before continuing.");
        else receive(next);
      }).catch(() => { /* connection recovery is shown by Work and recovery */ });
    };
    window.addEventListener("workflow-update", update);
    return () => window.removeEventListener("workflow-update", update);
  }, [campaign, receive]);
  const changed = () => { setDirty(true); setCanonicalConfirmed(false); setFormsConfirmed(false); };
  const perform = async (label: string, action: () => Promise<Campaign>) => {
    setBusy(label); setError(""); setMessage(""); setIntentFailed(false); setFormsFailed(false);
    try { const next = await action(); receive(next); if (label === "Proposing facts" || label === "Saving brief for manual fact entry") setAdvance("facts-lock"); if (label === "Proposing localized forms") setFactTab("forms"); if (label === "Locking facts") setAdvance("brand-strategy"); setMessage(label === "Locking facts" ? "Facts and reviewed forms are locked together." : label === "Saving brief for manual fact entry" ? "Brief saved for manual entry. Fill in and review the facts; nothing has been interpreted or locked automatically." : "Saved. Review the next step below."); }
    catch (failure) {
      setIntentFailed(label === "Proposing facts" && failure instanceof WorkFailure && failure.job.kind === "intent");
      if (label === "Proposing localized forms" && failure instanceof WorkFailure && failure.job.kind === "forms" && campaign) {
        setFormsFailed(true);
        try {
          const current = latestReview.current;
          const next = await campaignApi(`/${campaign.id}`);
          if (current.campaign?.id === next.id && !current.dirty && !current.transcriptChanged && !current.saved) {
            const reviewStillCurrent = next.revision === failure.job.campaign_revision + 1 && next.status === "canonical_confirmed"
              && JSON.stringify(next.facts) === JSON.stringify(current.campaign.facts)
              && JSON.stringify(next.languages) === JSON.stringify(current.campaign.languages)
              && JSON.stringify(next.brand) === JSON.stringify(current.campaign.brand)
              && JSON.stringify(next.target_audiences) === JSON.stringify(current.campaign.target_audiences)
              && JSON.stringify(next.warnings) === JSON.stringify(current.campaign.warnings);
            receive(next);
            setCanonicalConfirmed(reviewStillCurrent && canonicalConfirmed);
            setMessage(reviewStillCurrent ? "Saved canonical confirmation loaded. Retry wording for this current revision." : "The saved facts changed. Review and confirm them before retrying wording.");
          }
        } catch { setCanonicalConfirmed(false); setMessage("Could not load the saved revision. Reload the draft before retrying wording."); }
      }
      setError(failure instanceof Error ? failure.message : "Request failed. Reload the saved draft before retrying.");
    }
    finally { setBusy(""); }
  };
  const draftBody = (current: Campaign): DraftRequest => ({
    expected_revision: current.revision,
    facts: current.facts.filter((fact) => fact.key !== "DAYS").map((fact) => ({ key: fact.key, canonical: facts[fact.key] ?? null })),
    languages: selectedLanguages, channels: selectedChannels,
    target_audiences: target.split(",").map((value) => value.trim()).filter(Boolean),
    brand: { ...brandDraft, tone }, acknowledged_warning_ids: acks,
  });
  const analyze = () => perform("Proposing facts", async () => {
    let current = campaign;
    if (!current) {
      current = await campaignApi("", "POST", { languages: selectedLanguages, channels: selectedChannels });
      // Keep the server-created id even if provider extraction fails.
      setCampaign(current); localStorage.setItem("intent-locked-campaign", current.id);
      const url = new URL(window.location.href); url.searchParams.set("campaign", current.id); window.history.replaceState({}, "", url);
    } else if (dirty) {
      current = await campaignApi(`/${current.id}/facts/draft`, "PUT", draftBody(current));
      setCampaign(current);
    }
    return campaignApi(`/${current.id}/intent`, "POST", { expected_revision: current.revision, transcript });
  });
  const save = () => campaign && perform("Saving draft", () => campaignApi(`/${campaign.id}/facts/draft`, "PUT", draftBody(campaign)));
  const enterFactsManually = () => campaign && perform("Saving brief for manual fact entry", () => {
    setFactTab("canonical");
    return campaignApi(`/${campaign.id}/facts/draft`, "PUT", { ...draftBody(campaign), transcript });
  });
  const proposeForms = () => campaign && perform("Proposing localized forms", () => campaignApi(`/${campaign.id}/facts/surface`, "POST", { expected_revision: campaign.revision, confirm_canonical: true }));
  useEffect(() => {
    const review = (event: Event) => {
      if ((event as CustomEvent).detail?.campaign !== campaign?.id) return;
      setFactTab("canonical"); setAdvance("facts-lock");
    };
    window.addEventListener("workspace-review-forms", review);
    return () => window.removeEventListener("workspace-review-forms", review);
  }, [campaign?.id]);
  const newDraft = () => {
    setCampaign(null); setFactTab("canonical"); setFormLanguage("en"); setBrandDraft({tone:"",theme:"",colors:[],must_say:[],must_not_say:[]}); setTranscript(""); setFacts({}); setForms([]); setTarget(""); setTone(""); setAcks([]);
    setDirty(false); setCanonicalConfirmed(false); setFormsConfirmed(false); setError(""); setMessage(""); setIntentFailed(false); setFormsFailed(false);
    localStorage.removeItem("intent-locked-campaign"); const url = new URL(window.location.href); url.searchParams.delete("campaign"); window.history.replaceState({}, "", url);
  };
  useEffect(() => {
    const reset = () => { if (busy || saved || inferenceDisabled) return; newDraft(); };
    window.addEventListener("workspace-new", reset);
    return () => window.removeEventListener("workspace-new", reset);
  });
  const canonicalText = campaign?.facts.filter((f) => f.canonical).map((f) => `${factNames[f.key]}: ${Object.entries(f.canonical!).filter(([key]) => !["kind", "original_phrase", "timezone"].includes(key)).map(([, value]) => Array.isArray(value) ? value.join(", ") : String(value)).join(" ")}`).join(". ") ?? "";
  const readyToPropose = campaign && !locked && !dirty && !transcriptChanged && canonicalConfirmed;
  return <section aria-label="Campaign workspace" className="space-y-6">
    {campaign && <WebsiteWizard key={campaign.id} campaignId={campaign.id} readOnly={saved || inferenceDisabled} />}
    {!campaign && !started && <>
      <div className="welcome-hero"><div><p className="eyebrow">THE OWNER-CONTROLLED CAMPAIGN WORKSPACE</p><h1>A campaign that<br/>keeps its word.</h1><p className="subtitle">Human controls truth. AI controls execution. Code enforces the boundary.</p><div className="welcome-actions"><Button onClick={start}>Start a campaign<ArrowRight size={17}/></Button><Button variant="secondary" onClick={()=>setTraceOpen(true)}>Load saved demo</Button></div><p className="hint mt-5">Speak in English, Kannada or Kanglish. Your approval makes the facts final.</p></div><div className="welcome-proof"><p className="eyebrow">A CLEAR BOUNDARY, AT EVERY STEP</p><h2>Creative freedom.<br/>Business truth.</h2><div className="proof-row"><span>Owner reviews the facts</span><LockKeyhole size={20}/></div><div className="proof-row"><span>Code checks every claim</span><ShieldCheck size={20}/></div><div className="proof-row"><span>You authorize the final export</span><FileCheck2 size={20}/></div><small>Real outputs, visible provenance, no silent approvals.</small></div></div>
      <div className="how-row">{[[AudioLines,"Speak your idea","An editable brief in your own words."],[LockKeyhole,"Lock the facts","Confirm names, numbers and conditions."],[FileCheck2,"Approve the campaign","Review the exact content before export."]].map(([Icon,title,text])=>{const Symbol=Icon as typeof AudioLines;return <div key={String(title)}><span className="how-icon"><Symbol size={20}/></span><div><strong>{String(title)}</strong><p>{String(text)}</p></div></div>;})}</div>
    </>}
    <Dialog drawer keepMounted open={traceOpen} onClose={()=>setTraceOpen(false)} title="Trace & saved work">
      {workspace.connection}
      {campaign ? <WorkflowStatus campaign={campaign.id} saved={saved} onSaved={value => { setSaved(value); if (!value) void campaignApi(`/${campaign.id}`).then(receive).catch(() => setError("Cannot reload the current workspace. Retry loading saved progress.")); window.dispatchEvent(new CustomEvent("workspace-mode", { detail: { saved: value } })); }} /> : <div className="space-y-4"><p>Load a persisted campaign by its ID. Saved output is explicitly labeled SAVED DEMO OUTPUT; no fixtures are silently substituted.</p>{error && <p role="alert" className="callout danger">{error}</p>}<label>Saved campaign ID<input className="field" value={savedId} onChange={e=>setSavedId(e.target.value)}/></label><Button disabled={!savedId.trim()} onClick={()=>void campaignApi(`/${encodeURIComponent(savedId.trim())}`).then(async next=>{await workRead(`/api/campaigns/${next.id}/saved-output`);receive(next);setSaved(true);window.dispatchEvent(new CustomEvent("workspace-mode",{detail:{saved:true}}));setTraceOpen(false);setAdvance("facts-lock");}).catch(()=>setError("No captured saved output is available for that campaign. Check the ID and backend connection."))}>Load SAVED DEMO OUTPUT</Button></div>}
      <details><summary>Global activity trace</summary><ol className="space-y-3">{traces.map(t=><li key={t.id} className="text-xs">#{t.id} · {t.message}</li>)}</ol></details>
    </Dialog>

    {inferenceDisabled && <p className="mode-banner">SAVED DEMO OUTPUT · Server inference is disabled. Saved facts and files remain readable.</p>}
    <fieldset hidden={!started && !campaign} data-saved={saved || inferenceDisabled} className="min-w-0 space-y-6"><legend className="sr-only">{saved || inferenceDisabled ? "Cached output. Inference and approvals disabled in this view." : "Current campaign workspace"}</legend>

    {campaign && <div className="fact-lock-banner text-sm" aria-live="polite"><strong><LockKeyhole size={16}/>{locked ? "Locked by owner" : campaign.status === "forms_review" ? "Forms awaiting owner approval" : "Editable draft"}</strong> · Revision {campaign.revision} · {campaign.mode.toUpperCase()}<p className="mt-1">Date reference: {campaign.reference_date} · {campaign.timezone}{campaign.demo_clock ? " · Explicit demo clock" : " · Server clock"}</p>{locked && <div className="hash-row mt-2"><span className="hint">Approved {campaign.approved_at}</span><code className="hash-chip" title={campaign.fact_hash ?? ""}>Fact hash {campaign.fact_hash}</code><CopyButton value={campaign.fact_hash ?? ""} label="Copy hash"/><details><summary>Full hash</summary><code className="break-all text-xs">{campaign.fact_hash}</code></details></div>}</div>}
    {error && <div role="alert" className="callout danger toast-error"><p>{error}</p><p className="mt-2 text-sm">Your edits remain on screen. Reload discards unsaved edits and fetches the current revision.</p>{intentFailed && campaign && <div className="mt-3 flex flex-wrap gap-3"><button className="secondary" disabled={reviewBusy || !transcript.trim()} onClick={analyze}>Retry this brief</button><button className="secondary" disabled={reviewBusy || !transcript.trim()} onClick={enterFactsManually}>Enter facts manually</button></div>}{formsFailed && campaign && <div className="mt-3 flex flex-wrap gap-3"><button className="secondary" disabled={reviewBusy || !readyToPropose} onClick={proposeForms}>Retry wording</button><button className="secondary" disabled={reviewBusy} onClick={() => {setFactTab("canonical"); navigate("facts-lock");}}>Review saved facts</button></div>}</div>}
    {campaign && <button className="text-sm underline" disabled={reviewBusy} onClick={() => perform("Reloading", () => campaignApi(`/${campaign.id}`))}>Reload saved draft</button>}
    {(busy || message) && <p role="status" className="text-sm">{busy ? `${busy}…` : message}</p>}
    <Stage id="speak-type"><fieldset disabled={saved || inferenceDisabled}><div id="speak-type" className="card space-y-5">
      <h2 className="text-xl font-semibold">Speak or type, then review</h2>
      <VoiceInput value={transcript} disabled={reviewBusy || !!locked} onChange={(value) => { setTranscript(value); setCanonicalConfirmed(false); setFormsConfirmed(false); }} />
      {!locked && <button className="text-sm underline" disabled={reviewBusy} onClick={() => setTranscript(example)}>Load a labeled example brief</button>}
      <p className="text-xs text-[#576353]">The example explicitly supplies “Namma Cafe”. Empty drafts never assume a café identity. “This weekend” uses the date reference shown above after extraction.</p>
      <fieldset disabled={reviewBusy || !!locked} className="flex flex-wrap gap-5"><legend className="mb-2 font-semibold">Languages to review</legend>{languages.map(([lang, name]) => <ToggleChip key={lang} selected={selectedLanguages.includes(lang)} onClick={()=>{setLanguages(selectedLanguages.includes(lang) ? selectedLanguages.filter(l=>l!==lang) : [...selectedLanguages,lang]);changed();}}>{name}</ToggleChip>)}</fieldset>
      <fieldset disabled={reviewBusy || !!locked} className="flex flex-wrap gap-5"><legend className="mb-2 font-semibold">Future campaign channels</legend>{channels.map((channel) => <ToggleChip key={channel} selected={selectedChannels.includes(channel)} onClick={()=>{setChannels(selectedChannels.includes(channel) ? selectedChannels.filter(c=>c!==channel) : [...selectedChannels,channel]);changed();}}>{channel}</ToggleChip>)}</fieldset>
      {!locked && <><button className="primary" disabled={reviewBusy || !transcript.trim() || !selectedLanguages.length || !selectedChannels.length} onClick={analyze}>{campaign?.transcript ? "Re-propose facts from transcript" : "Propose facts from transcript"}</button><p className="text-xs">Proposing again replaces current fact proposals. Nothing in a transcript can approve or lock this campaign.</p></>}
      {transcriptChanged && <p className="text-sm font-semibold">Transcript edited. Re-propose facts, or reload to discard these transcript edits, before approving facts.</p>}
    </div>
    </fieldset></Stage><Stage id="facts-lock"><div>
    {campaign && <div className="mb-5"><Tabs label="Fact review section" value={factTab} onChange={setFactTab} options={[{value:"canonical",label:"Canonical facts"},{value:"forms",label:"Approved wording"}]}/></div>}
    {!campaign && <div id="facts-lock" className="card"><h2 className="font-semibold">◷ Facts Lock · waiting for your brief</h2><p>Propose facts above, then review their numbers, dates and localized forms.</p></div>}
      {campaign && campaign.warnings.length > 0 && <fieldset disabled={reviewBusy || !!locked} className="space-y-3 rounded-xl bg-[#f4ead7] p-4"><legend className="font-semibold">Review notes</legend>{campaign.warnings.map((warning) => <label key={warning.id} className="flex items-start gap-3 text-sm"><input className="mt-1" type="checkbox" checked={acks.includes(warning.id)} onChange={(e) => { setAcks(e.target.checked ? [...acks, warning.id] : acks.filter((id) => id !== warning.id)); setFormsConfirmed(false); }} /><span>{warning.message}</span></label>)}</fieldset>}
    {campaign && <div hidden={factTab!=="canonical"} id="facts-lock" className="card space-y-5">
      <div><p className="eyebrow">02 / Canonical facts</p><h2 className="mt-2 text-xl font-semibold">Resolve the details</h2><p className="mt-2 text-sm">Café name, location, product, offer, and dates are required. Unspecified conditions remain unknown.</p></div>
      {!locked && campaign.clarifications.length > 0 && <div className="rounded-xl bg-[#f4ead7] p-4"><h3 className="font-semibold">Clarifications</h3><ul className="mt-2 list-disc space-y-2 pl-5">{campaign.clarifications.map((question) => <li key={question.key} className="rounded-xl bg-white/70 p-4"><strong>{question.required ? "Required · needs your answer" : "Optional"}:</strong> {question.question}{question.key==="ELIGIBILITY" && <div className="mt-3 flex flex-wrap gap-2">{(["all","students"] as const).map(scope=><ToggleChip key={scope} disabled={reviewBusy} selected={facts.ELIGIBILITY?.kind==="eligibility" && facts.ELIGIBILITY.scope===scope} onClick={()=>{setFacts({...facts,ELIGIBILITY:{kind:"eligibility",scope,description:""}});changed();}}>{scope==="all" ? "Open to all" : "Students only"}</ToggleChip>)}</div>}{question.key==="ID_RULE" && <div className="mt-3 flex flex-wrap gap-2">{[true,false].map(required=><ToggleChip key={String(required)} disabled={reviewBusy} selected={facts.ID_RULE?.kind==="id_rule" && facts.ID_RULE.required===required} onClick={()=>{setFacts({...facts,ID_RULE:{kind:"id_rule",required}});changed();}}>{required ? "ID required" : "No ID required"}</ToggleChip>)}</div>}</li>)}</ul><p className="mt-3 text-sm">Answer in the matching fields below and save the draft.</p></div>}
      {!locked && !!campaign.agent_questions?.length && <ul className="list-disc pl-5">{campaign.agent_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>}
      <fieldset disabled={reviewBusy || !!locked} className="grid gap-4 sm:grid-cols-2"><label>Target audiences (comma separated)<input className="field mt-2" value={target} onChange={(e) => { setTarget(e.target.value); changed(); }} /></label><label>Brand tone<input className="field mt-2" value={tone} onChange={(e) => { setTone(e.target.value); changed(); }} /></label></fieldset>
      <fieldset disabled={reviewBusy || !!locked}><BrandDraftEditor value={brandDraft} onChange={value=>{setBrandDraft(value);changed();}}/></fieldset>
      <div className="fact-grid">{campaign.facts.filter(f=>["CAFE","LOCATION","OFFER","PRODUCT","DAYS","DATES"].includes(f.key)).map((fact) => <FactEditor key={fact.key} fact={fact} value={facts[fact.key] ?? null} disabled={reviewBusy || !!locked} onChange={(value) => { setFacts({ ...facts, [fact.key]: value }); changed(); }} />)}</div>
      <h3 className="conditions-heading">Conditions <span className="hint font-normal">— unspecified stays unspecified</span></h3>
      <div className="fact-grid">{campaign.facts.filter(f=>!["CAFE","LOCATION","OFFER","PRODUCT","DAYS","DATES"].includes(f.key)).map(fact=><FactEditor key={fact.key} fact={fact} value={facts[fact.key] ?? null} disabled={reviewBusy || !!locked} onChange={value=>{setFacts({...facts,[fact.key]:value});changed();}}/>)}</div>
      <Readback text={canonicalText} />
      {!locked && <><div className="flex flex-wrap gap-3"><button className="secondary" disabled={reviewBusy || transcriptChanged} onClick={save}>Save editable facts</button>{dirty && <p className="self-center text-sm">Unsaved fact edits. Corresponding forms will be invalidated.</p>}</div><label className="flex items-start gap-3"><input type="checkbox" className="mt-1" checked={canonicalConfirmed} disabled={reviewBusy || dirty || transcriptChanged} onChange={(e) => setCanonicalConfirmed(e.target.checked)} /><span>I confirm the saved canonical facts, including names, numbers and dates.</span></label><button className="primary" disabled={reviewBusy || !readyToPropose} onClick={proposeForms}>Propose localized forms</button></>}
    </div>}
    {campaign && factTab==="forms" && campaign.status!=="forms_review" && !locked && <p className="callout warning">Save and confirm canonical facts, then propose localized forms to review the wording.</p>}
    {campaign && (campaign.status === "forms_review" || locked) && <div hidden={factTab!=="forms"} className="card space-y-5">
      <div><p className="eyebrow">02 / Localized-form review</p><h2 className="mt-2 text-xl font-semibold">Approve the words that carry the facts</h2><p className="mt-2 text-sm">Review each language and case form. Separate alternatives with |. Kannada native review has not been performed. Mock forms are development fixtures.</p></div>
      <Tabs label="Surface-form language" options={selectedLanguages.map(value=>({value,label:languages.find(([id])=>id===value)?.[1] ?? value}))} value={selectedLanguages.includes(formLanguage) ? formLanguage : selectedLanguages[0]} onChange={setFormLanguage}/>
      <div className="grid gap-4 md:grid-cols-2">{forms.map((entry, index) => <fieldset key={entry.key} disabled={reviewBusy || !!locked || dirty || transcriptChanged} className="min-w-0 rounded-xl border border-[#d3d8cd] p-4"><legend className="font-semibold">{factNames[entry.key]}</legend>{selectedLanguages.map((lang) => <div key={lang} hidden={lang !== (selectedLanguages.includes(formLanguage) ? formLanguage : selectedLanguages[0])} className="mt-3 space-y-2"><p className="font-semibold">{languages.find(([id]) => id === lang)?.[1]}</p>{(["nom", "dat", "gen", "loc"] as const).filter((grammaticalCase) => grammaticalCase === "nom" || !!entry.surface[lang]?.[grammaticalCase]).map((grammaticalCase) => <label key={grammaticalCase} className="block text-xs">{grammaticalCase}<input lang={lang} className="field mt-1 text-base" aria-label={`${entry.key} ${lang} ${grammaticalCase}`} value={entry.surface[lang]?.[grammaticalCase]?.join(" | ") ?? ""} onChange={(e) => { setForms(forms.map((form, i) => i !== index ? form : { ...form, surface: { ...form.surface, [lang]: { ...form.surface[lang]!, [grammaticalCase]: e.target.value.split("|").map((v) => v.trim()) } } })); setFormsConfirmed(false); }} /></label>)}</div>)}</fieldset>)}</div>
      {selectedLanguages.includes("kn") && <Readback language="kn-IN" text={forms.map((form) => form.surface.kn?.nom.join(", ")).filter(Boolean).join(". ")} />}
      {!locked && <><label className="flex items-start gap-3"><input type="checkbox" className="mt-1" checked={formsConfirmed} disabled={reviewBusy || dirty || transcriptChanged} onChange={(e) => setFormsConfirmed(e.target.checked)} /><span>I approve these canonical facts and all displayed localized forms. Lock this exact revision.</span></label><button className="primary" disabled={reviewBusy || dirty || transcriptChanged || !formsConfirmed} onClick={() => perform("Locking facts", () => campaignApi(`/${campaign.id}/facts/lock`, "POST", { expected_revision: campaign.revision, idempotency_key: lockKey.current, reviewed_fact_versions: Object.fromEntries(campaign.facts.map((fact) => [fact.key, fact.version])), forms, approve_canonical_and_forms: true, acknowledged_warning_ids: acks } satisfies LockRequest))}>Lock approved facts</button><p className="text-xs">A lock stores all facts, forms, versions, and approval together. Locking enables strategy and generation below.</p></>}
    </div>}
    </div></Stage>
    {campaign && locked && <CampaignMatrix key={`matrix:${campaign.id}:${campaign.revision}`} campaign={campaign} readOnly={saved || inferenceDisabled} />}
    {campaign && locked && <Stage id="guardian"><GuardianPanel key={`${campaign.id}:${campaign.revision}`} campaign={campaign} /></Stage>}
    {campaign && locked && <DeliveryPanel key={`delivery-${campaign.id}-${campaign.revision}`} campaign={campaign} onPublished={receive} saved={saved || inferenceDisabled} />}

    </fieldset>
  </section>;
}
