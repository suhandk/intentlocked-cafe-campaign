"use client";

import { useCallback, useEffect, useState } from "react";
import type { components } from "@/lib/api.generated";
import CampaignFlow from "@/components/CampaignFlow";
import WorkspaceShell from "@/components/workspace/WorkspaceShell";
type Health = components["schemas"]["Health"];
type Cost = components["schemas"]["Cost"];
type Trace = components["schemas"]["TraceEvent"];

async function readSnapshot(signal?: AbortSignal): Promise<{ health: Health; cost: Cost; traces: Trace[] }> {
  const responses = await Promise.all(["ready", "cost", "traces"].map(
    (route) => fetch(`/api/${route}`, { signal, cache: "no-store" }),
  ));
  if (responses.some((r) => !r.ok)) throw new Error("Backend unavailable");
  const [health, cost, traces] = await Promise.all(responses.map((r) => r.json()));
  return { health, cost, traces };
}

export default function Workspace() {
  const [health, setHealth] = useState<Health | null>(null);
  const [cost, setCost] = useState<Cost | null>(null);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const receive = useCallback((snapshot: Awaited<ReturnType<typeof readSnapshot>>) => {
    setHealth(snapshot.health); setCost(snapshot.cost); setTraces(snapshot.traces);
    setError(""); setLoading(false);
  }, []);
  const fail = useCallback(() => {
    setHealth(null); setCost(null); setTraces([]); setLoading(false);
    setError("Cannot reach the local backend. Start FastAPI on port 8000, then retry.");
  }, []);
  const refresh = () => { setLoading(true); void readSnapshot().then(receive, fail); };
  useEffect(() => {
    const controller = new AbortController();
    const update = () => { void readSnapshot(controller.signal).then(
      (snapshot) => { if (!controller.signal.aborted) receive(snapshot); },
      () => { if (!controller.signal.aborted) fail(); },
    ); };
    update();
    const timer = setInterval(update, 3000);
    window.addEventListener("workflow-update", update);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener("workflow-update", update); };
  }, [receive, fail]);

  return <WorkspaceShell health={health} cost={cost} traces={traces} error={error} loading={loading} refresh={refresh}><CampaignFlow inferenceDisabled={health?.mode === "SAVED DEMO OUTPUT"} /></WorkspaceShell>;
}
