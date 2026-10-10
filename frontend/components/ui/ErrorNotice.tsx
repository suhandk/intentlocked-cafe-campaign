"use client";
import { TriangleAlert } from "lucide-react";
import { Button } from ".";
import { useWorkspace } from "../workspace/WorkspaceShell";
export default function ErrorNotice({message}:{message:string}) {
  const {setTraceOpen}=useWorkspace();
  return <div className="callout danger toast-error" role="alert"><TriangleAlert size={19}/><div><p>{message.split(" · code ")[0]}</p><p className="hint mt-2">Completed work stays saved. Review the error before explicitly retrying.</p><Button variant="ghost" onClick={()=>setTraceOpen(true)}>Review retry options</Button><details><summary>Error details</summary><p className="break-words text-xs">{message}</p></details></div></div>;
}
