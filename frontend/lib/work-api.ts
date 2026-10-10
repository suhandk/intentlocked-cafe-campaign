import { errorMessage } from "@/lib/error-message";
import type { components } from "./api.generated";

export type Work = components["schemas"]["WorkJob"];
export type WorkSnapshot = components["schemas"]["WorkSnapshot"];
type Kind = components["schemas"]["WorkRequest"]["kind"];
export class WorkFailure extends Error {
  constructor(public readonly job: Work) {
    super(job.kind === "intent" && job.error_code === "INTENT_UNAVAILABLE"
      ? `The model could not interpret this brief. Edit it and retry, or enter facts manually. Existing facts have not changed. Work id ${job.id}.`
      : job.kind === "forms" && job.error_code === "SURFACES_UNAVAILABLE"
      ? `The wording could not be prepared. Your canonical facts are saved. Review them and retry wording; nothing is locked. Work id ${job.id}.`
      : `${job.status}: ${job.error_code ?? "Work stopped"} · work id ${job.id}. Completed outputs remain saved. Reload to review before explicitly retrying.${job.error_code === "SUBMISSION_UNCERTAIN" ? " Media submission may have succeeded; do not resubmit without checking." : ""}`);
    this.name = "WorkFailure";
  }
}
const active = (job: Work) => ["queued", "running"].includes(job.status);
export async function workRead<T>(url: string, body?: unknown): Promise<T> {
  try {
    const response = await fetch(url, { method: body === undefined ? "GET" : "POST", cache: "no-store",
      headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    const value = await response.json();
    if (!response.ok) throw new Error(errorMessage(value,"Request rejected. Reload saved progress before retrying."));
    return value as T;
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError) throw new Error("Backend unavailable. Start FastAPI on port 8000, then reload saved progress. Work is not automatically repeated.");
    throw error;
  }
}

export async function submitWork<T>(campaign: string, kind: Kind, input: unknown, target_id?: string): Promise<T> {
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify({ campaign, kind, input, target_id }))))).map(v => v.toString(16).padStart(2, "0")).join("");
  const storage = `intent-work-${hash}`;
  const key = localStorage.getItem(storage) ?? crypto.randomUUID();
  localStorage.setItem(storage, key);
  let job = await workRead<Work>(`/api/campaigns/${campaign}/work`, { kind, input, target_id: target_id ?? null, idempotency_key: key });
  window.dispatchEvent(new CustomEvent("workflow-update", { detail: { campaign } }));
  while (active(job)) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    job = await workRead<Work>(`/api/work/${job.id}`);
  }
  localStorage.removeItem(storage);
  window.dispatchEvent(new CustomEvent("workflow-update", { detail: { campaign } }));
  if (!["completed", "partial"].includes(job.status) || !job.result) {
    throw new WorkFailure(job);
  }
  return job.result as T;
}

// Existing APIs keep their schemas; only long operations use durable admission.
export function routedWork<T>(path: string, body: unknown): Promise<T> | null {
  const match = path.match(/^\/api\/campaigns\/([^/]+)\/(.*)$/);
  if (!match) return null;
  const [, campaign, suffix] = match;
  const kinds: Record<string, Kind> = { intent: "intent", "facts/surface": "forms", strategy: "strategy", generate: "generate", optimize: "optimize", backgrounds: "background", "assets/render": "render", change: "change", "red-team": "red_team" };
  if (kinds[suffix]) return submitWork<T>(campaign, kinds[suffix], body);
  const item = suffix.match(/^delivery\/([^/]+)\/audit$/);
  if (item) return submitWork<T>(campaign, "item_audit", body, item[1]);
  const forms = suffix.match(/^change\/([^/]+)\/surface$/);
  if (forms) return submitWork<T>(campaign, "change_forms", body, forms[1]);
  return null;
}
