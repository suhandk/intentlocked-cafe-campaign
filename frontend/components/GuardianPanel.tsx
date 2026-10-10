"use client";
import ErrorNotice from "./ui/ErrorNotice";
import { errorMessage } from "@/lib/error-message";

import { useEffect, useRef, useState } from "react";
import { useWorkspace } from "./workspace/WorkspaceShell";
import type { components } from "@/lib/api.generated";
import type { Campaign, Channel, Lang } from "@/lib/campaign-api";
import { ProgressRing, StatusBadge, Tabs } from "./ui";

type Report = components["schemas"]["GuardianReport"];
type Content = components["schemas"]["TemplateContent"];
const initial: Content = { headline: "", body: "", cta: "", hashtags: [], alt_text: "" };

export default function GuardianPanel({ campaign, readOnly=false }: { campaign: Campaign; readOnly?:boolean }) {
  const {recordStage}=useWorkspace();
  const [template, setTemplate] = useState<Content>(initial);
  const [mode, setMode] = useState<"fragment" | "asset">("fragment");
  const [language, setLanguage] = useState<Lang>(campaign.languages[0]);
  const [channel, setChannel] = useState<Channel>(campaign.channels[0]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editorField, setEditorField] = useState<"headline" | "body" | "cta" | "alt_text" | "hashtags">("body");
  const generation = useRef(0);
  useEffect(()=>recordStage("guardian",report?.status==="BLOCKED" ? "Blocked ⚠" : report ? "Needs your review" : "Not started",`${campaign.id}:${campaign.revision}`),[campaign.id,campaign.revision,report,recordStage]);
  const invalidate = () => { generation.current++; setReport(null); setError(""); };
  const run = async () => {
    const revision = ++generation.current;
    setBusy(true); setError(""); setReport(null);
    try {
      const response = await fetch("/api/guardian/check", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: campaign.id, expected_revision: campaign.revision,
          mode, language, channel, template }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(errorMessage(result,"Guardian check failed. Reload and retry."));
      if (revision === generation.current) setReport(result);
    } catch (failure) {
      if (revision === generation.current) setError(failure instanceof Error ? failure.message : "Check failed");
    } finally { setBusy(false); }
  };
  return <section id="guardian" className="card space-y-5" aria-labelledby="guardian-heading">
    <h2 id="guardian-heading" className="text-xl font-semibold">Guardian · Check the copy</h2>
    <p className="text-sm">Use approved fact slots such as {"{{OFFER}}"} and {"{{PRODUCT|dat}}"}. A fragment checks a short piece of copy. A complete asset also requires the channel’s facts and disclosures.</p>
    <div className="grid gap-4 sm:grid-cols-3">
      <label>Check mode<select className="field" value={mode} onChange={e => { invalidate(); setMode(e.target.value as typeof mode); }}><option value="fragment">Short fragment</option><option value="asset">Complete channel asset</option></select></label>
      <label>Language<select className="field" value={language} onChange={e => { invalidate(); setLanguage(e.target.value as Lang); }}>{campaign.languages.map(l => <option key={l}>{l}</option>)}</select></label>
      <label>Channel<select className="field" value={channel} onChange={e => { invalidate(); setChannel(e.target.value as Channel); }}>{campaign.channels.map(c => <option key={c}>{c}</option>)}</select></label>
    </div>
    <Tabs label="Copy field" value={editorField} onChange={setEditorField} options={[{value:"headline",label:"Headline"},{value:"body",label:"Copy"},{value:"cta",label:"Call to action"},{value:"alt_text",label:"Alt text"},{value:"hashtags",label:"Hashtags"}]}/>
    {(["headline", "body", "cta", "alt_text"] as const).map(field => <label key={field} hidden={editorField!==field} className="block">{({ headline: "Headline", body: "Copy", cta: "Call to action", alt_text: "Alt text" })[field]}<textarea className="field mt-1 min-h-32" lang={language} value={template[field]} maxLength={12000} onChange={e => { invalidate(); setTemplate({ ...template, [field]: e.target.value }); }} /></label>)}
    <label hidden={editorField!=="hashtags"} className="block">Hashtags (one per line)<textarea className="field mt-1" value={template.hashtags.join("\n")} onChange={e => { invalidate(); setTemplate({ ...template, hashtags: e.target.value ? e.target.value.split("\n") : [] }); }} /></label>
    <button className="primary" disabled={busy || readOnly} onClick={() => void run()}>{busy ? "Checking…" : "Check copy"}</button>
    {error && <ErrorNotice message={error}/>}
    {report && <div className="space-y-4" role="status">
      <div className={`verdict ${report.status==="BLOCKED" ? "block" : report.status==="PASS" ? "pass" : ""}`}><StatusBadge tone={report.status==="BLOCKED" ? "danger" : report.status==="PASS" ? "success" : "warning"}>{report.status}</StatusBadge> · {report.mode === "fragment" ? "Fragment diagnostic only" : "Complete asset diagnostic"}</div>
      <div className="flex flex-wrap items-center gap-6">{report.integrity !== null && <ProgressRing value={report.integrity} tone={report.status==="BLOCKED" ? "danger" : report.status==="INCOMPLETE" ? "warning" : "success"}/>}<div><p>{report.checks.filter(c=>c.completed && c.passed===true).length} passed checks · {report.checks.filter(c=>c.completed && c.passed===false && c.severity==="BLOCK").length} blocking checks</p><p className="hint">Integrity covers completed applicable checks. Pending checks do not count as passed.</p></div></div>
      {report.missing_checks.length > 0 && <p>Pending checks: {report.missing_checks.join(", ")}</p>}
      {(["BLOCK","WARN","INFO"] as const).map(severity=><div key={severity}>{report.checks.filter(c=>c.completed && c.passed===false && c.severity===severity).map(check=><div className="mb-3 rounded-xl border p-4" key={check.rule}><StatusBadge tone={severity==="BLOCK" ? "danger" : severity==="WARN" ? "warning" : "info"}>{severity} · {check.rule}</StatusBadge>{(check.findings ?? []).map((finding,i)=><p className="mt-2 text-sm" key={i}>{finding.field}: {finding.message} {finding.quote && <><mark>{finding.quote}</mark> ({finding.start}–{finding.end})</>}</p>)}</div>)}</div>)}
      <details><summary>All rule results and readiness</summary><ul className="space-y-2">{report.checks.map(check => <li key={check.rule}><strong>{check.rule}</strong> · {!check.applicable ? "Not applicable" : !check.completed ? "Pending" : check.passed ? "Passed" : check.severity}</li>)}</ul></details>
      {report.rendered && <details><summary>Server-rendered draft and fact provenance</summary>{Object.entries(report.rendered.fields).filter(([, text]) => text).map(([field, text]) => <p className="mt-2 whitespace-pre-wrap" lang={language} key={field}><strong>{field}:</strong> {text}</p>)}<ul className="mt-3 text-sm">{report.rendered.spans.map((span, i) => <li key={i}>{span.field} {span.start}–{span.end}: {span.key} v{span.version}, {span.language}/{span.case}</li>)}</ul></details>}
    </div>}
    <p className="hint">This diagnostic cannot approve or export an asset. Complete outputs need the persisted customer audit; an absent G14 result is pending. Kannada native review is separate. Poster exports use validated stored bytes.</p>
  </section>;
}
