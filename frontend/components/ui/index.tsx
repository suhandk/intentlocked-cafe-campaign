"use client";
import { useEffect, useId, useRef, useState, useSyncExternalStore, type ButtonHTMLAttributes, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Check, Copy, LoaderCircle, ShieldCheck, TriangleAlert, X } from "lucide-react";

export function useMotionSafe() { return !useReducedMotion(); }
export function Button({ variant = "primary", loading = false, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" | "accent"; loading?: boolean }) {
  return <button {...props} disabled={props.disabled || loading} className={`ui-button ${variant} ${className}`} aria-busy={loading}>{loading && <LoaderCircle size={17} className="spinner" aria-hidden="true" />}{children}</button>;
}
export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" | "danger" | "warning" | "info" }) { return <span className={`status-badge ${tone}`}>{tone === "danger" || tone === "warning" ? <TriangleAlert size={13} aria-hidden="true" /> : tone === "success" ? <Check size={13} aria-hidden="true" /> : <span aria-hidden="true">•</span>}{children}</span>; }
export function ToggleChip({ selected, children, onClick, disabled = false }: { selected: boolean; children: ReactNode; onClick: () => void; disabled?: boolean }) { return <button type="button" className={`toggle-chip ${selected ? "selected" : ""}`} aria-pressed={selected} disabled={disabled} onClick={onClick}>{selected && <Check size={15} aria-hidden="true" />}{children}</button>; }
export function Tabs<T extends string>({ options, value, onChange, label }: { options: {value:T; label:string}[]; value:T; onChange:(value:T)=>void; label:string }) {
  const id = useId();
  return <div className="ui-tabs" role="group" aria-label={label}>{options.map(option => <button type="button" className={value === option.value ? "active" : ""} key={option.value} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{value === option.value && <motion.span className="tab-indicator" layoutId={id} transition={{duration:0.18}} /> }<span>{option.label}</span></button>)}</div>;
}
export function Card({ children, className = "" }: {children:ReactNode; className?:string}) { return <div className={`card ${className}`}>{children}</div>; }
export function Callout({ children, tone = "info" }: {children:ReactNode; tone?:"info"|"danger"|"warning"|"success"}) { return <div className={`callout ${tone}`}>{tone === "danger" || tone === "warning" ? <TriangleAlert size={18} aria-hidden="true" /> : <ShieldCheck size={18} aria-hidden="true" />}<div>{children}</div></div>; }
export function EmptyState({ title, children, action }: {title:string; children:ReactNode; action?:ReactNode}) { return <div className="empty-state"><ShieldCheck size={30} aria-hidden="true" /><h2>{title}</h2><p>{children}</p>{action}</div>; }
export function Skeleton() { return <div className="skeleton" aria-label="Loading" role="status" />; }
export function CopyButton({ value, label = "Copy" }: {value:string; label?:string}) {
  const [notice, setNotice] = useState("");
  return <><Button variant="ghost" title={label} onClick={() => void navigator.clipboard.writeText(value).then(() => setNotice("Copied"), () => setNotice("Clipboard unavailable; select and copy the displayed text."))}><Copy size={15} aria-hidden="true" />{label}</Button>{notice && <span role="status" className="text-xs">{notice}</span>}</>;
}
export function Dialog({ open, onClose, title, children, drawer = false, keepMounted = false }: {open:boolean; onClose:()=>void; title:string; children:ReactNode; drawer?:boolean; keepMounted?:boolean}) {
  const mounted=useSyncExternalStore(subscribeToHydration,()=>true,()=>false);
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  const id = useId();
  const safe = useMotionSafe();
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const scroll = document.body.style.overflow;
    const root = document.getElementById("workspace-root");
    if (root) root.inert = true;
    document.body.style.overflow = "hidden";
    const timer = setTimeout(() => panel.current?.focus(), 0);
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close.current(); }
      if (event.key === "Tab") {
        const elements = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]') ?? []).filter(el => el.getClientRects().length > 0);
        const first = elements[0], last = elements.at(-1);
        if (!first) { event.preventDefault(); panel.current?.focus(); }
        else if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", keyboard, true);
    return () => { clearTimeout(timer); document.removeEventListener("keydown", keyboard, true); if (root) root.inert = false; document.body.style.overflow = scroll; previous?.focus(); };
  }, [open]);
  if (!mounted) return null;
  return createPortal(<AnimatePresence>{(open || keepMounted) && <motion.div hidden={!open} className={`dialog-backdrop ${drawer ? "drawer-backdrop" : ""}`} initial={{opacity:0}} animate={{opacity:open ? 1 : 0}} exit={{opacity:0}} transition={{duration:safe ? .18 : 0}} onClick={e => {if (e.target === e.currentTarget) onClose();}}><motion.div ref={panel} tabIndex={-1} role={open ? "dialog" : undefined} aria-modal={open ? true : undefined} aria-labelledby={id} className={drawer ? "trace-drawer" : "dialog-panel"} initial={{x:drawer && safe ? 32 : 0, y:!drawer && safe ? 12 : 0}} animate={{x:0,y:0}}><header className="dialog-heading"><h2 id={id}>{title}</h2><Button variant="ghost" aria-label="Close dialog" onClick={onClose}><X size={20} /></Button></header>{children}</motion.div></motion.div>}</AnimatePresence>, document.body);
}
function subscribeToHydration() {return ()=>{};}
export function ProgressRing({ value, tone="success" }: {value:number;tone?:"success"|"danger"|"warning"}) { return <div className="integrity-ring"><svg viewBox="0 0 100 100" role="img" aria-label={`Intent integrity ${value.toFixed(1)} percent`}><circle cx="50" cy="50" r="42" fill="none" stroke="var(--border)" strokeWidth="7" /><motion.circle cx="50" cy="50" r="42" fill="none" stroke={`var(--${tone})`} strokeWidth="7" strokeDasharray="264" animate={{strokeDashoffset:264*(1-value/100)}} transform="rotate(-90 50 50)" /></svg><strong>{value.toFixed(0)}<small>%</small></strong></div>; }
