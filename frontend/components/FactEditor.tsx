import type { ReactNode } from "react";
import type { Canonical, Fact } from "@/lib/campaign-api";
import { LockKeyhole } from "lucide-react";
import { StatusBadge } from "./ui";

const names: Record<Fact["key"], string> = { CAFE: "Café name", LOCATION: "Location", PRODUCT: "Product", OFFER: "Offer", DATES: "Dates", DAYS: "Days (calculated)", ELIGIBILITY: "Offer eligibility", ID_RULE: "ID required", TIME_WINDOW: "Daily time window", DINE_IN_RULE: "Dine-in / takeaway", MIN_PURCHASE_RULE: "Minimum purchase", COMBINE_RULE: "Combine with other offers" };
export { names as factNames };
export function FactEditor({ fact, value, onChange, disabled }: { fact: Fact; value: Canonical | null; onChange: (value: Canonical | null) => void; disabled: boolean }) {
  const label = names[fact.key];
  let editor: ReactNode;
  const input = (name: string, val: string | number, change: (value: string) => void, type = "text") => <input className="field" aria-label={name} type={type} value={val} onChange={(e) => change(e.target.value)} />;
  const select = (val: string, options: [string, string][], change: (value: string) => void, name = label) => <select className="field" aria-label={name} value={val} onChange={(e) => change(e.target.value)}><option value="">Not specified</option>{options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select>;
  switch (fact.key) {
    case "CAFE": case "LOCATION": case "PRODUCT":
      editor = input(label, value?.kind === "text" ? value.value : "", (v) => onChange(v ? { kind: "text", value: v } : null)); break;
    case "OFFER":
      editor = <div className="space-y-2">{select(value?.kind ?? "", [["percent_off", "Percent off"], ["amount_off", "Amount off (INR)"], ["buy_get", "Buy / get"]], (v) => onChange(v === "percent_off" ? { kind: v, value: 0, unit: "percent" } : v === "amount_off" ? { kind: v, amount: 0, currency: "INR" } : v === "buy_get" ? { kind: v, buy: 1, get: 1 } : null), "Offer type")}
        {value?.kind === "percent_off" && input("Percent off", value.value, (v) => onChange({ ...value, value: Number(v) }), "number")}
        {value?.kind === "amount_off" && input("Amount off INR", value.amount, (v) => onChange({ ...value, amount: Number(v) }), "number")}
        {value?.kind === "buy_get" && <>{input("Buy quantity", value.buy, (v) => onChange({ ...value, buy: Number(v) }), "number")}{input("Get quantity", value.get, (v) => onChange({ ...value, get: Number(v) }), "number")}</>}
      </div>; break;
    case "DATES": {
      const dates = value?.kind === "dates" ? value : { kind: "dates" as const, start: "", end: "", original_phrase: "owner entered", timezone: "Asia/Kolkata" as const };
      editor = <div className="space-y-2">{input("Start date", dates.start, (v) => onChange({ ...dates, start: v }), "date")}{input("End date", dates.end, (v) => onChange({ ...dates, end: v }), "date")}<p className="text-xs">Asia/Kolkata. Days update when saved.</p></div>; break;
    }
    case "DAYS": editor = <p>{value?.kind === "days" ? value.weekdays.join(", ") : "Waiting for dates"}</p>; break;
    case "ELIGIBILITY":
      editor = <>{select(value?.kind === "eligibility" ? value.scope : "", [["all", "Open to all"], ["students", "Students only"], ["custom", "Other restriction"]], (v) => onChange(v ? { kind: "eligibility", scope: v as "all" | "students" | "custom", description: "" } : null))}{value?.kind === "eligibility" && value.scope === "custom" && input("Exact eligibility restriction", value.description ?? "", (v) => onChange({ ...value, description: v }))}<p className="mt-2 text-xs">Targeting students does not make an offer student-only.</p></>; break;
    case "ID_RULE":
      editor = select(value?.kind === "id_rule" ? String(value.required) : "", [["true", "ID is required"], ["false", "No ID required"]], (v) => onChange(v ? { kind: "id_rule", required: v === "true" } : null)); break;
    case "COMBINE_RULE":
      editor = select(value?.kind === "combine_rule" ? String(value.allowed) : "", [["true", "Can combine"], ["false", "Cannot combine"]], (v) => onChange(v ? { kind: "combine_rule", allowed: v === "true" } : null)); break;
    case "DINE_IN_RULE":
      editor = select(value?.kind === "dine_in_rule" ? value.scope : "", [["dine_in_only", "Dine-in only"], ["takeaway_only", "Takeaway only"], ["both", "Both"]], (v) => onChange(v ? { kind: "dine_in_rule", scope: v as "dine_in_only" | "takeaway_only" | "both" } : null)); break;
    case "MIN_PURCHASE_RULE":
      editor = input("Minimum purchase INR", value?.kind === "minimum_purchase" ? value.amount : "", (v) => onChange(v === "" ? null : { kind: "minimum_purchase", amount: Number(v), currency: "INR" }), "number"); break;
    case "TIME_WINDOW": {
      const time = value?.kind === "time_window" ? value : { kind: "time_window" as const, start: "", end: "" };
      editor = <div className="space-y-2"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!value} onChange={e=>onChange(e.target.checked ? null : {kind:"time_window",start:"",end:""})}/>Leave time unspecified</label>{value ? <><label className="block text-sm">From{input("Daily start time", time.start, (v) => onChange({ ...time, start: v }), "time")}</label><label className="block text-sm">Until{input("Daily end time", time.end, (v) => onChange({ ...time, end: v }), "time")}</label></> : <p className="hint">No daily time restriction has been supplied.</p>}</div>; break;
    }
  }
  return <fieldset disabled={disabled} className={`fact-editor min-w-0 ${fact.status === "locked" ? "locked" : ""}`}><legend className="px-1 font-semibold">{fact.status === "locked" && <LockKeyhole size={14}/>} {label}</legend><div className="mb-3"><StatusBadge tone={fact.status === "locked" ? "success" : fact.status === "proposed" ? "warning" : "neutral"}>{fact.status.replaceAll("_", " ")} · v{fact.version}</StatusBadge></div>{editor}{fact.source_span && <p className="evidence break-words">Evidence: “{fact.source_span.quote}”</p>}<details><summary>Source details</summary>Version {fact.version} · {fact.source}</details></fieldset>;
}
