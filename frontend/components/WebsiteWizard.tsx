"use client";
import { useEffect, useRef, useState } from "react";
import { Button, Dialog } from "./ui";
import { parseMenuCsv, websiteApi, websiteDraftError, websiteDraftIssue, websiteInputError, type WebsiteBundle, type WebsiteDraft, type WebsiteFields, type WebsiteJob } from "@/lib/website-api";

const steps = ["Basics", "Offer", "Visit info", "Menu", "Look", "Review", "Publish"];
type Offer = { locked: boolean; edit_url: string; facts: { key: string; canonical: unknown }[]; revision: number };
type Config = { providers: string[]; publish_enabled: boolean; remember_available: boolean; permissions_note: string;
  design: { provider: string; model: string; mode: string; available: boolean } };
type Connection = { connection_id: string; masked_suffix: string; message: string; remembered: boolean };

export default function WebsiteWizard({ campaignId, readOnly = false }: { campaignId: string; readOnly?: boolean }) {
  const [open, setOpen] = useState(false); const [draft, setDraft] = useState<WebsiteDraft | null>(null);
  const [fields, setFields] = useState<WebsiteFields | null>(null); const [step, setStep] = useState(0);
  const [offer, setOffer] = useState<Offer | null>(null); const [config, setConfig] = useState<Config | null>(null);
  const [bundle, setBundle] = useState<WebsiteBundle | null>(null); const [error, setError] = useState("");
  const [busy, setBusy] = useState(false); const [saveStatus, setSaveStatus] = useState("");
  const [saveError, setSaveError] = useState(""); const [closeRequested, setCloseRequested] = useState(false);
  const [token, setToken] = useState(""); const [remember, setRemember] = useState(false);
  const [remembered, setRemembered] = useState(false); const [useRemembered, setUseRemembered] = useState(false);
  const [connection, setConnection] = useState<Connection | null>(null); const [approvedHash, setApprovedHash] = useState("");
  const [job, setJob] = useState<WebsiteJob | null>(null); const [csv, setCsv] = useState("");
  const [https, setHttps] = useState(false);
  const version = useRef(1); const saveQueue = useRef<Promise<unknown>>(Promise.resolve());
  const latest = useRef<{ fields: WebsiteFields; step: number } | null>(null);
  const savedJson = useRef("");
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void Promise.all([websiteApi<WebsiteDraft>(`/campaigns/${campaignId}/website`), websiteApi<Config>("/website/config"),
      websiteApi<{ remembered: boolean }>("/website/token")]).then(async ([value, cfg, status]) => {
      if (cancelled) return; version.current = value.version; setDraft(value); setFields(value.fields); setStep(value.step);
      latest.current = { fields: value.fields, step: value.step }; savedJson.current = JSON.stringify(latest.current);
      setConfig(cfg); setRemembered(status.remembered); setSaveStatus("Draft saved"); setSaveError("");
      const currentOffer = await websiteApi<Offer>(`/websites/${value.id}/offer`); if (!cancelled) setOffer(currentOffer);
      if (value.bundle_id) { const result = await websiteApi<WebsiteBundle>(`/websites/${value.id}/bundle`);
        if (!cancelled) setBundle(result); }
    }).catch(() => { if (!cancelled) setError("Could not resume the website draft or bundle. Reload and review Facts Lock."); });
    return () => { cancelled = true; setToken(""); };
  }, [open, campaignId]);
  useEffect(() => {
    if (!job || !["queued", "publishing", "verifying"].includes(job.status)) return;
    const timer = setInterval(() => { void websiteApi<WebsiteJob>(`/website/jobs/${job.id}`).then(setJob).catch(() => setError("Publish status unavailable. Check Netlify before submitting again.")); }, 1500);
    return () => clearInterval(timer);
  }, [job]);
  function persist(snapshot: { fields: WebsiteFields; step: number }) {
    if (!draft) return Promise.resolve();
    const invalid = websiteDraftError(snapshot.fields);
    if (invalid) return Promise.reject(new Error(invalid));
    const encoded = JSON.stringify(snapshot);
    const run = saveQueue.current.catch(() => undefined).then(async () => {
      // Superseded typing snapshots need not wait for another transport timeout.
      if (latest.current && JSON.stringify(latest.current) !== encoded) return;
      if (savedJson.current === encoded) return;
      setSaveStatus("Saving draft…");
      const value = await websiteApi<WebsiteDraft>(`/websites/${draft.id}`, "PUT", { expected_version: version.current, ...snapshot });
      version.current = value.version; savedJson.current = encoded; setDraft(value);
      // A completed older save must not label a newer incomplete edit as saved.
      const pending = latest.current;
      if (!pending || JSON.stringify(pending) === encoded) { setSaveStatus("Draft saved"); setSaveError(""); }
      else { const invalid = websiteDraftError(pending.fields); setSaveStatus(invalid ? `Edits not saved yet: ${invalid}.` : "Saving draft…"); }
    });
    saveQueue.current = run;
    return run;
  }
  // Owner fields only. Provider tokens are never part of this draft or any storage call.
  function update(next: WebsiteFields) {
    setFields(next); latest.current = { fields: next, step }; setBundle(null); setConnection(null); setApprovedHash("");
    setError(""); setSaveError(""); setCloseRequested(false);
    const invalid = websiteDraftError(next);
    if (invalid) { setSaveStatus(`Edits not saved yet: ${invalid}.`); return; }
    void persist(latest.current).catch(saveFailure);
  }
  function saveFailure(cause: unknown) { setSaveStatus("Draft not saved"); setSaveError(`${cause instanceof Error ? cause.message : "Could not save the draft"}. Your edits remain in this window.`); }
  async function changeStep(next: number) {
    if (!fields) return;
    const snapshot = { fields, step: next }; setStep(next); latest.current = snapshot; setError(""); setCloseRequested(false);
    const invalid = websiteDraftError(fields);
    if (invalid) { setSaveStatus(`Edits not saved yet: ${invalid}.`); return; }
    setBusy(true);
    try { await persist(snapshot); } catch (e) { saveFailure(e); } finally { setBusy(false); }
  }
  function finishClose() { setOpen(false); setToken(""); setConnection(null); setApprovedHash(""); setCloseRequested(false); }
  async function close() {
    const invalid = latest.current && websiteDraftError(latest.current.fields);
    if (invalid) { setError(`Cannot save yet: ${invalid}.`); setCloseRequested(true); return; }
    setBusy(true);
    try { if (latest.current) await persist(latest.current); finishClose(); }
    catch (e) { saveFailure(e); setCloseRequested(true); } finally { setBusy(false); }
  }
  async function retrySave() { if (!latest.current) return; setBusy(true); setError(""); setSaveError("");
    try { await persist(latest.current); } catch (e) { saveFailure(e); } finally { setBusy(false); } }
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); try { await work(); }
    catch (e) { setError(e instanceof Error ? e.message : "Website operation failed"); } finally { setBusy(false); } }
  async function generate() { if (!draft || !fields) return;
    const invalid = websiteInputError(fields); if (invalid) { setError(invalid); return; }
    if (!offer?.locked) { setError("Lock the offer in Facts Lock before generating"); return; }
    await action(async () => { await persist({ fields, step: 5 }); setStep(5);
      const result = await websiteApi<WebsiteBundle>(`/websites/${draft.id}/generate`, "POST", { expected_version: version.current });
      setBundle(result); setApprovedHash(""); setConnection(null); }); }
  async function upload(file: File, logo: boolean) {
    if (!draft || !fields) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 5_000_000) { setError("Images must be PNG, JPEG or WebP, up to 5 MB"); return; }
    await action(async () => { const encoded = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error("Image could not be read")); reader.readAsDataURL(file); });
      const result = await websiteApi<{ id: string }>(`/websites/${draft.id}/images`, "POST", { mime: file.type, base64: encoded });
      update(logo ? { ...fields, logo_id: result.id } : { ...fields, photo_ids: [...fields.photo_ids, result.id] }); });
  }
  return <div className="card space-y-3">
    <Button variant="secondary" disabled={readOnly} onClick={() => { setError(""); setSaveError(""); setCloseRequested(false); setDraft(null); setFields(null); setOffer(null); setBundle(null); latest.current = null; setSaveStatus("Loading website draft…"); setHttps(window.location.protocol === "https:"); setOpen(true); }}>Create website</Button>
    <p className="hint">Optional website wizard. Your campaign stays unchanged.</p>
    <Dialog open={open} onClose={() => { if (!busy) void close(); }} title="Create website">
      <p role="status">{saveStatus}</p>{(error || saveError) && <p role="alert" className="callout danger">{error || saveError}</p>}
      {fields && websiteDraftIssue(fields) && <Button variant="secondary" disabled={busy} onClick={() => void changeStep(websiteDraftIssue(fields)!.step)}>{websiteDraftIssue(fields)!.action}</Button>}
      {saveError && fields && !websiteDraftError(fields) && <Button variant="secondary" disabled={busy} onClick={() => void retrySave()}>Retry save</Button>}
      {closeRequested && <div className="callout"><p>Unsaved edits will be lost if you discard them. Saved website data stays available.</p><Button variant="secondary" disabled={busy} onClick={() => { setCloseRequested(false); setError(""); }}>Keep editing</Button><Button variant="secondary" disabled={busy} onClick={finishClose}>Discard unsaved edits and close</Button></div>}
      <nav aria-label="Website wizard steps" className="flex flex-wrap gap-2">{steps.map((name, i) => <button key={name} className="field" aria-current={step === i ? "step" : undefined} disabled={busy || !draft} onClick={() => void changeStep(i)}>{i + 1}. {name}</button>)}</nav>
      {draft && fields && <fieldset disabled={busy} className="space-y-4 mt-4"><h3>{steps[step]}</h3>
        {step === 0 && <><label>Café name (required)<input className="field" required maxLength={120} value={fields.name} onChange={e => update({ ...fields, name: e.target.value })}/></label>
          <label>City/area (required)<input className="field" required maxLength={200} value={fields.area} onChange={e => update({ ...fields, area: e.target.value })}/></label>
          <p>Use the café name and city/area from Facts Lock.</p><label>Description (optional)<textarea className="field" maxLength={1000} value={fields.description} onChange={e => update({ ...fields, description: e.target.value })}/></label>
          <Button variant="secondary" onClick={() => void action(async () => { const result = await websiteApi<{ description: string }>(`/websites/${draft.id}/suggest`, "POST"); update({ ...fields, description: result.description }); })}>Suggest one</Button>
          <fieldset><legend>Languages (optional)</legend>{(["en", "kn", "kn-Latn"] as const).map(language => <label key={language}><input type="checkbox" checked={fields.languages.includes(language)} onChange={e => { const selected = e.target.checked ? [...fields.languages, language] : fields.languages.filter(v => v !== language); if (selected.length) update({ ...fields, languages: selected }); }}/>{language}</label>)}</fieldset></>}
        {step === 1 && <>{offer?.locked ? <><p>Read-only offer · Facts Lock revision {offer.revision}</p><dl>{offer.facts.map(f => <div key={f.key}><dt>{f.key}</dt><dd>{JSON.stringify(f.canonical)}</dd></div>)}</dl></> : <p role="alert">No facts are locked. Lock the offer before generation.</p>}
          <a className="underline" href={offer?.edit_url ?? `/?campaign=${campaignId}#facts-lock`} onClick={() => { setToken(""); }}>Edit in Facts Lock</a></>}
        {step === 2 && <><label>Address (optional)<textarea className="field" maxLength={500} value={fields.address} onChange={e => update({ ...fields, address: e.target.value })}/></label>
          {(["phone", "whatsapp"] as const).map(key => <label key={key}>{key === "phone" ? "Phone" : "WhatsApp"} (optional)<input className="field" type="tel" value={fields[key]} onChange={e => update({ ...fields, [key]: e.target.value })}/></label>)}
          <fieldset><legend>Opening hours (optional; same-day)</legend>{fields.hours.map((hours, i) => <div key={hours.day} className="flex gap-2"><span>{hours.day}</span>{(["open", "close"] as const).map(key => <label key={key}>{key}<input type="time" className="field" value={hours[key]} onChange={e => update({ ...fields, hours: fields.hours.map((h, n) => n === i ? { ...h, [key]: e.target.value } : h) })}/></label>)}<button onClick={() => update({ ...fields, hours: fields.hours.filter((_, n) => n !== i) })}>Remove day</button></div>)}
            <label>Add opening day<select className="field" value="" onChange={e => { if (e.target.value) update({ ...fields, hours: [...fields.hours, { day: e.target.value as WebsiteFields["hours"][number]["day"], open: "", close: "" }] }); }}><option value="">Choose day</option>{(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"] as const).filter(day => !fields.hours.some(h => h.day === day)).map(day => <option key={day}>{day}</option>)}</select></label></fieldset>
          <label>Social links (optional, one HTTPS URL per line)<textarea className="field" value={fields.social_links.join("\n")} onChange={e => update({ ...fields, social_links: e.target.value.split("\n").filter(v => v.trim()) })}/></label></>}
        {step === 3 && <><p>Optional menu, prices in INR. Empty menu omits the section.</p>{fields.menu.map((item, i) => <div key={i} className="flex gap-2"><label>Menu item {i + 1}<input className="field" maxLength={100} value={item.name} onChange={e => update({ ...fields, menu: fields.menu.map((m, n) => n === i ? { ...m, name: e.target.value } : m) })}/></label><label>Price {i + 1}<input className="field" type="number" min="0" max="1000000" value={Number.isFinite(item.price) ? item.price : ""} onChange={e => update({ ...fields, menu: fields.menu.map((m, n) => n === i ? { ...m, price: e.target.value === "" ? NaN : Number(e.target.value) } : m) })}/></label><button onClick={() => update({ ...fields, menu: fields.menu.filter((_, n) => n !== i) })}>Remove item</button></div>)}
          <Button variant="secondary" disabled={fields.menu.length >= 100} onClick={() => update({ ...fields, menu: [...fields.menu, { name: "", price: NaN }] })}>Add menu row</Button>
          <label>CSV (name,price)<textarea className="field" value={csv} onChange={e => setCsv(e.target.value)}/></label><Button variant="secondary" onClick={() => { try { update({ ...fields, menu: parseMenuCsv(csv) }); } catch (e) { setError(e instanceof Error ? e.message : "Invalid CSV"); } }}>Import CSV</Button></>}
        {step === 4 && <><label>Style<select className="field" value={fields.style} onChange={e => update({ ...fields, style: e.target.value as WebsiteFields["style"] })}>{["simple", "warm", "modern"].map(style => <option key={style}>{style}</option>)}</select></label>
          <label>Colour<input type="color" value={fields.colour} onChange={e => update({ ...fields, colour: e.target.value })}/></label>
          <label>Logo (optional)<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file, true); }}/></label>{fields.logo_id && <button onClick={() => update({ ...fields, logo_id: null })}>Remove logo</button>}
          <label>Photo (optional, up to 5)<input type="file" disabled={fields.photo_ids.length >= 5} accept="image/png,image/jpeg,image/webp" onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file, false); }}/></label>{fields.photo_ids.map((id, i) => <button key={id} onClick={() => update({ ...fields, photo_ids: fields.photo_ids.filter(v => v !== id) })}>Remove photo {i + 1}</button>)}</>}
        {step === 5 && <><p className="callout">DRAFT - NOT PUBLISHED</p><p>Website layout: {config?.design.provider} · {config?.design.model} · {config?.design.mode}</p>{!config?.design.available && <p role="alert">Website design service is not configured on the server. Your saved draft stays available.</p>}<Button disabled={!offer?.locked || !!websiteInputError(fields) || !config?.design.available} onClick={() => void generate()}>Generate website</Button>{!offer?.locked && <p>Generation requires locked facts.</p>}{websiteInputError(fields) && <p>{websiteInputError(fields)}</p>}
          {bundle && <><h4>Guardian report</h4><p>Source: {bundle.report.campaign_source} · layout: {bundle.report.design?.mode ?? "BASIC"} {bundle.report.design?.model ?? ""}</p><p>{bundle.report.scope}</p><p>Semantic audit: {bundle.report.semantic_audit} · native review: {bundle.report.native_review}. Missing checks: {bundle.report.missing_checks.join(", ")}. This does not approve a campaign.</p><ul>{bundle.report.reports.map((r, i) => <li key={i}>{r.language}: {r.status}</li>)}</ul>
            <iframe title="DRAFT - NOT PUBLISHED website preview" sandbox="" src={`/api/websites/${draft.id}/preview/index.html`} style={{ width: "100%", height: 420, border: "1px solid #bbb" }}/><p className="break-all">Bundle SHA-256: {bundle.sha256}</p></> }</>}
        {step === 6 && <><p>Publishing is optional. Zip download needs no hosting token.</p>{bundle ? <><p>Bundle source: {bundle.report.campaign_source}. Semantic/native review pending; website hash approval does not mark these checks passed.</p><a className="underline" href={`/api/websites/${draft.id}/download.zip`}>Download website (zip)</a></> : <p>Generate the current website in Review first.</p>}
          {!config?.publish_enabled && <p>Publishing is disabled by default. Zip export stays available.</p>}{!https && <p>Publishing credentials require HTTPS. Token entry is disabled here.</p>}
          <fieldset disabled={!https || !config?.publish_enabled || !bundle}><legend>Publish</legend><label>Hosting provider<select className="field"><option value="netlify">Netlify</option></select></label><p>{config?.permissions_note}</p>
            {remembered && <label><input type="checkbox" checked={useRemembered} onChange={e => { setUseRemembered(e.target.checked); setToken(""); setConnection(null); setApprovedHash(""); }}/>Use remembered Netlify token</label>}
            {!useRemembered && <label>Netlify API token<input className="field" type="password" autoComplete="off" spellCheck={false} value={token} onChange={e => { setToken(e.target.value); setConnection(null); setApprovedHash(""); }}/></label>}
            <label><input type="checkbox" disabled={!config?.remember_available || useRemembered} checked={remember} onChange={e => setRemember(e.target.checked)}/>Remember for next time (encrypted on server)</label>
            <Button variant="secondary" disabled={!token && !useRemembered} onClick={() => void action(async () => { if (!bundle) return; const entered = token; setToken(""); const result = await websiteApi<Connection>(`/websites/${draft.id}/connection`, "POST", { provider: "netlify", ...(useRemembered ? { use_remembered: true } : { token: entered }), remember, bundle_hash: bundle.sha256 }); setConnection(result); setRemembered(result.remembered); })}>Test connection</Button>
            {connection && <><p>{connection.message} · {connection.masked_suffix}</p><p className="break-all">Approve exact bundle SHA-256: {bundle?.sha256}</p><label><input type="checkbox" checked={!!bundle && approvedHash === bundle.sha256} onChange={e => setApprovedHash(e.target.checked && bundle ? bundle.sha256 : "")}/>I approve publication of this exact website bundle</label></>}
            <Button disabled={!connection || !bundle || approvedHash !== bundle.sha256 || !!job && ["queued", "publishing", "verifying"].includes(job.status)} onClick={() => void action(async () => { if (!bundle || !connection) return; const result = await websiteApi<WebsiteJob>(`/websites/${draft.id}/publish`, "POST", { connection_id: connection.connection_id, bundle_hash: bundle.sha256, approve_exact_bundle: true }); setJob(result); setConnection(null); setApprovedHash(""); setToken(""); })}>Publish</Button>
          </fieldset>
          {(remembered || connection) && <Button variant="secondary" disabled={!https} onClick={() => void action(async () => { await websiteApi("/website/token", "DELETE"); setRemembered(false); setUseRemembered(false); setConnection(null); setToken(""); setApprovedHash(""); })}>Disconnect / delete token</Button>}
          {job && <p role="status">{job.message}{job.status === "published" && job.url && <a className="underline" href={job.url} target="_blank" rel="noopener noreferrer"> Open verified website</a>}</p>}
        </>}
        <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={step === 0} onClick={() => void changeStep(step - 1)}>Back</Button>{step < 6 && <Button variant="secondary" onClick={() => void changeStep(step + 1)}>Next</Button>}<Button variant="secondary" onClick={() => void close()}>Save and close</Button></div>
      </fieldset>}
    </Dialog>
  </div>;
}
