export type WebsiteFields = {
  name: string; area: string; description: string; languages: ("en" | "kn" | "kn-Latn")[];
  address: string; hours: { day: "MON" | "TUE" | "WED" | "THU" | "FRI" | "SAT" | "SUN"; open: string; close: string }[];
  phone: string; whatsapp: string; menu: { name: string; price: number }[];
  social_links: string[]; logo_id: string | null; photo_ids: string[];
  style: "simple" | "warm" | "modern"; colour: string;
};
export type WebsiteDraft = { id: string; campaign_id: string; version: number; step: number; fields: WebsiteFields; bundle_id: string | null };
export type WebsiteBundle = { id: string; sha256: string; draft_version: number; facts_revision: number; report: {
  status: string; campaign_source: string; semantic_audit: string; native_review: string; scope: string; missing_checks: string[];
  reports: { language: string; status: string; rendered: { fields: Record<string, string> } | null }[];
  design: { provider: string | null; model: string | null; mode: string; calls?: number };
} };
export type WebsiteJob = { id: string; status: string; message: string; url: string | null; bundle_hash: string };
export async function websiteApi<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { method, cache: "no-store", signal: AbortSignal.timeout(15_000), headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch { throw new Error("Website server did not respond. Check the backend and retry"); }
  let result;
  try { result = await response.json(); }
  catch { throw new Error("Website server returned an unreadable response. Check the backend and retry"); }
  if (!response.ok) throw new Error(typeof result?.message === "string" ? result.message : "Website operation failed");
  return result as T;
}

// CSV uses exactly name,price. Quoted commas/newlines and escaped quotes supported.
export function parseMenuCsv(text: string): WebsiteFields["menu"] {
  if (text.length > 50_000) throw new Error("CSV is too large");
  const rows: string[][] = []; let row: string[] = []; let cell = ""; let quoted = false; let closed = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') { quoted = false; closed = true; } else cell += ch; continue; }
    if (ch === '"') { if (cell || closed) throw new Error("Malformed CSV quotes"); quoted = true; }
    else if (ch === ",") { row.push(cell); cell = ""; closed = false; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); if (row.some(v => v.trim())) rows.push(row); row = []; cell = ""; closed = false; }
    else { if (closed && ch.trim()) throw new Error("Malformed CSV quotes"); cell += ch; }
  }
  if (quoted) throw new Error("Unclosed CSV quote");
  row.push(cell); if (row.some(v => v.trim())) rows.push(row);
  if (rows[0]?.map(v => v.trim().toLowerCase()).join(",") === "name,price") rows.shift();
  if (rows.length > 100) throw new Error("Maximum 100 menu rows");
  return rows.map(r => { const name = r[0]?.trim(); const value = r[1]?.trim(); const price = Number(value);
    if (r.length !== 2 || !name || name.length > 100 || !value || !Number.isFinite(price) || price < 0 || price > 1_000_000)
      throw new Error("Each CSV row needs a name and a numeric INR price"); return { name, price }; });
}

export function websiteDraftIssue(fields: WebsiteFields): { message: string; step: number; action: string } | null {
  if ([fields.phone, fields.whatsapp].some(v => v && !/^\+?[1-9][0-9]{6,14}$/.test(v))) return { message: "Phone needs 7–15 digits, optionally starting with +", step: 2, action: "Fix phone number" };
  if (fields.hours.some(h => !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(h.open) || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(h.close))) return { message: "Finish each opening time and closing time, or remove that day", step: 2, action: "Fix opening hours" };
  if (fields.hours.some(h => h.close <= h.open)) return { message: "Opening hours need a closing time after the opening time on the same day", step: 2, action: "Fix opening hours" };
  if (fields.menu.some(m => !m.name.trim() || !Number.isFinite(m.price) || m.price < 0 || m.price > 1_000_000)) return { message: "Finish each menu name and INR price, or remove that row", step: 3, action: "Fix menu row" };
  if (fields.social_links.length > 5) return { message: "Use at most five social links", step: 2, action: "Fix social links" };
  for (const link of fields.social_links) { try { const url = new URL(link); if (link.length > 500 || url.protocol !== "https:" || url.username || url.password || url.port && url.port !== "443") return { message: "Social links must be HTTPS URLs on the default port", step: 2, action: "Fix social links" }; } catch { return { message: "Finish the social URL before saving", step: 2, action: "Fix social links" }; } }
  return null;
}

export function websiteDraftError(fields: WebsiteFields): string | null {
  return websiteDraftIssue(fields)?.message ?? null;
}

export function websiteInputError(fields: WebsiteFields): string | null {
  if (!fields.name.trim() || !fields.area.trim()) return "Café name and city/area are required";
  if (fields.name.length > 120 || fields.area.length > 200) return "Name or city/area is too long";
  return websiteDraftError(fields);
}
