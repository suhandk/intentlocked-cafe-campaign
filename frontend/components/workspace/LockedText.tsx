import type { components } from "@/lib/api.generated";
export default function LockedText({text,field,rendered}:{text:string;field:string;rendered:NonNullable<components["schemas"]["GuardianReport"]["rendered"]>}) {
  const letters=Array.from(text); let position=0;
  const parts:React.ReactNode[]=[];
  for(const span of rendered.spans.filter(s=>s.field===field).sort((a,b)=>a.start-b.start)) {
    parts.push(letters.slice(position,span.start).join(""));
    parts.push(<span key={`${span.start}:${span.key}`} className="locked-span" title={`🔒 from locked fact: ${span.key} v${span.version}, ${span.language}/${span.case}`}>{letters.slice(span.start,span.end).join("")}</span>);
    position=span.end;
  }
  parts.push(letters.slice(position).join(""));
  return <>{parts}</>;
}
