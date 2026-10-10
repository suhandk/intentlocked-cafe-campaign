import { errorMessage } from "@/lib/error-message";
import type { components } from "./api.generated";
import { routedWork } from "./work-api";

export type Campaign = components["schemas"]["Campaign"];
export type Fact = components["schemas"]["Fact"];
export type Canonical = NonNullable<Fact["canonical"]>;
export type Lang = Campaign["languages"][number];
export type Channel = Campaign["channels"][number];
export type DraftRequest = components["schemas"]["DraftRequest"];
export type LockRequest = components["schemas"]["LockRequest"];
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function campaignApi(path: string, method = "GET", body?: unknown): Promise<Campaign> {
  const job = method === "POST" && body !== undefined ? routedWork<Campaign>(`/api/campaigns${path}`, body) : null;
  if (job) return job;
  const response = await fetch(`/api/campaigns${path}`, {
    method, cache: "no-store", headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, errorMessage(data,"The request could not be completed."));
  return data as Campaign;
}
