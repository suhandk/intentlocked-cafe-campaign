"use client";

import type { components } from "@/lib/api.generated";

type Run = components["schemas"]["GenerationRun"];
const explanations: Record<string, string> = {
  G02: "Dates and weekdays must use the approved fact slots.",
  G05: "Required business facts or conditions are missing from the visible copy.",
  G07: "A factual claim appears outside an approved fact slot.",
  G08: "Unsupported wording changes or adds a business claim.",
  G11: "The draft does not match the selected language script.",
};

export default function CopyReadinessNotice({run, onReview}: {run: Run; onReview?: () => void}) {
  const pending = ["queued", "running"].includes(run.status);
  const reasons = [...new Set(run.cells.flatMap(cell => cell.reasons ?? []))];
  return <aside role="status" className="rounded-xl border border-[#cbd1c3] bg-[#f7f4ed] p-4 space-y-2">
    <p className="font-semibold">{pending ? "Copy generation is still in progress" : "No validated copy drafts for this selection"}</p>
    <p>{pending ? "Completed drafts appear as each batch passes validation." : "Posters and scores need a draft that passes Guardian. Review the copy findings and explicitly retry unfinished drafts."}</p>
    {!pending && <ul className="text-sm space-y-1">{reasons.map(reason => <li key={reason}>{explanations[reason] ?? `Validation stopped: ${reason.replaceAll("_", " ").toLowerCase()}.`}</li>)}</ul>}
    {onReview && <button className="secondary" onClick={onReview}>Review campaign copy</button>}
  </aside>;
}
