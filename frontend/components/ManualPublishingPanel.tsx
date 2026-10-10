"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink } from "lucide-react";
import type { components } from "@/lib/api.generated";
import { errorMessage } from "@/lib/error-message";

type Profiles = components["schemas"]["SocialProfiles"];
type Pack = components["schemas"]["ExportPack"];
const platforms = ["instagram", "facebook", "whatsapp"] as const;
const names = {instagram:"Instagram profile",facebook:"Facebook Page",whatsapp:"WhatsApp café chat"};
const hints = {instagram:"https://www.instagram.com/your_cafe/",facebook:"https://www.facebook.com/YourCafe",whatsapp:"https://wa.me/ followed by your international number (no + or spaces)"};
const empty = {instagram:"",facebook:"",whatsapp:""};

async function profilesRequest(body?: unknown): Promise<Profiles> {
  const response = await fetch("/api/social-profiles", {method:body ? "PUT" : "GET",
    cache:"no-store",headers:{"Content-Type":"application/json"},
    body:body ? JSON.stringify(body) : undefined});
  const value = await response.json();
  if (!response.ok) throw new Error(errorMessage(value,"Social links unavailable. Reload and try again."));
  return value;
}

export default function ManualPublishingPanel({ pack }: {pack?: Pack}) {
  const [profiles,setProfiles] = useState<Profiles>();
  const [draft,setDraft] = useState(empty);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [message,setMessage] = useState("");
  const guard = useRef(false);
  const install = (next: Profiles) => {
    setProfiles(next);
    setDraft({instagram:next.instagram ?? "",facebook:next.facebook ?? "",whatsapp:next.whatsapp ?? ""});
  };
  useEffect(()=>{
    let active=true;
    void profilesRequest().then(next=>{if(active) install(next);}).catch(()=>{if(active) setError("Social links could not load. Start the backend, then reload links.");});
    return ()=>{active=false;};
  },[]);
  async function action(save: boolean) {
    if(guard.current) return;
    guard.current=true; setBusy(true); setError(""); setMessage("");
    try {
      const next = await profilesRequest(save ? {expected_version:profiles?.version ?? 0,
        ...Object.fromEntries(platforms.map(p=>[p,draft[p].trim() || null]))} : undefined);
      install(next); setMessage(save ? "Social links saved. Approved campaign content is unchanged." : "Saved social links reloaded.");
    } catch(e) {setError(e instanceof Error ? e.message : "Could not save links. Reload before retrying.");}
    finally {guard.current=false;setBusy(false);}
  }
  return <section className="card space-y-4" aria-label="Manual social publishing">
    <h3 className="text-xl font-semibold">Your social profiles</h3>
    <p>Save the café’s links once. After approval, download the poster, copy the approved description and open your account to publish manually.</p>
    <form className="space-y-3" onSubmit={e=>{e.preventDefault();void action(true);}}>
      <fieldset disabled={busy} className="grid gap-3 md:grid-cols-3">
        {platforms.map(p=><label key={p} className="min-w-0">{names[p]} URL (optional)
          <input className="field mt-1" type="url" maxLength={500} autoComplete="off" value={draft[p]}
            placeholder={p === "whatsapp" ? "https://wa.me/…" : hints[p]}
            onChange={e=>{setDraft({...draft,[p]:e.target.value});setMessage("");}}
            aria-describedby={`social-hint-${p}`} />
          <span id={`social-hint-${p}`} className="mt-1 block break-words text-xs">{hints[p]}</span>
        </label>)}
      </fieldset>
      <div className="flex flex-wrap gap-3"><button className="secondary" type="submit" disabled={busy || !profiles}>{busy ? "Saving / loading…" : "Save social links"}</button>
        <button className="secondary" type="button" disabled={busy} onClick={()=>void action(false)}>Reload social links</button></div>
    </form>
    {error && <p role="alert" className="callout danger">{error} Use a direct HTTPS profile/Page URL or wa.me chat link. Reload links if another tab changed them.</p>}
    {message && <p role="status">{message}</p>}
    {pack ? <div className="space-y-3 rounded-xl border p-4" aria-label="Publish approved output manually">
      <h4 className="text-lg font-semibold">Publish your approved post</h4>
      <p>{pack.mode.toUpperCase()} · Approved revision {pack.campaign_revision}. Use the approved downloads and descriptions above.</p>
      <ol className="list-decimal space-y-1 pl-5"><li>Download the approved poster and copy its matching approved description.</li><li>Open your saved profile and sign in to the café’s account.</li><li>Create a post, upload the saved image, paste the description and review before publishing.</li></ol>
      <div className="flex flex-wrap gap-3">{platforms.map(p=>profiles?.[p]
        ? <a key={p} className="secondary" href={profiles[p]!} target="_blank" rel="noopener noreferrer">Open {names[p]} <ExternalLink size={16}/></a>
        : <p key={p} className="text-sm">{names[p]} link not set — add it above and save.</p>)}</div>
      <a className="secondary" href="https://web.whatsapp.com/" target="_blank" rel="noopener noreferrer">Open WhatsApp Web <ExternalLink size={16}/></a>
      <p className="text-sm">A café WhatsApp link opens a chat. To publish a Status, open WhatsApp and add the downloaded image manually. Profile links do not attach images, prefill Instagram/Facebook posts, send messages or publish anything.</p>
    </div> : <p className="callout">Approve and authorize your selected output to unlock profile-opening buttons. After reload, choose “Show approved final output”.</p>}
  </section>;
}
