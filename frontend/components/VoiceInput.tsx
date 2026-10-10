"use client";
import { useEffect, useId, useRef, useState } from "react";
import { Mic, Square, Volume2 } from "lucide-react";
import { Tabs } from "./ui";

interface Recognition {
  lang: string; interimResults: boolean; continuous: boolean;
  start(): void; stop(): void; abort(): void;
  onresult: ((event: { resultIndex: number; results: { length: number; [key: number]: { isFinal: boolean; 0: { transcript: string } } } }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };

export function VoiceInput({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled: boolean }) {
  const inputId=useId();
  const [language, setLanguage] = useState("en-IN");
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [notice, setNotice] = useState("");
  const recognition = useRef<Recognition | null>(null);
  const current = useRef(value);
  useEffect(() => { current.current = value; }, [value]);
  useEffect(() => () => { recognition.current?.abort(); }, []);
  const start = () => {
    const Speech = (window as SpeechWindow).SpeechRecognition ?? (window as SpeechWindow).webkitSpeechRecognition;
    if (!Speech) { setNotice("Speech input is unavailable in this browser. Type or paste your brief below."); return; }
    const instance = new Speech(); recognition.current = instance;
    instance.lang = language; instance.continuous = true; instance.interimResults = true;
    instance.onresult = (event) => {
      let pending = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          current.current = `${current.current} ${event.results[i][0].transcript}`.trim().slice(0, 2000);
          onChange(current.current);
        } else pending += event.results[i][0].transcript;
      }
      setInterim(pending);
    };
    instance.onerror = (event) => { const denied = event.error === "not-allowed" || event.error === "service-not-allowed";
      setNotice(denied ? "Microphone permission denied. Allow microphone access in browser site settings and try again, or type below. No approval depends on speech." : "Speech input stopped. Check your microphone and connection, or continue with editable text."); setListening(false); };
    instance.onend = () => { setListening(false); setInterim(""); };
    try { instance.start(); setListening(true); setNotice("Listening. Stop and check names, numbers, and dates before proposing facts."); }
    catch { setNotice("Could not start speech input. Continue with typing."); }
  };
  return <div className="space-y-3">
    <div className="flex flex-wrap items-center gap-3">
      <fieldset disabled={disabled || listening}><legend className="sr-only">Speech language</legend><Tabs label="Speech language" options={[{value:"en-IN",label:"English (India)"},{value:"kn-IN",label:"Kannada"}]} value={language} onChange={setLanguage}/></fieldset>
      <button type="button" className={`secondary ${listening ? "mic-listening" : ""}`} disabled={disabled} onClick={() => listening ? recognition.current?.stop() : start()}>{listening ? <Square size={17}/> : <Mic size={17}/>} {listening ? "Stop microphone" : "Use microphone"}</button>
    </div>
    <p className="text-xs text-[#576353]">Optional browser speech may be processed by your browser vendor. Typing supports the complete flow.</p>
    <label className="block font-semibold" htmlFor={inputId}>Your brief · review the transcript</label>
    <textarea id={inputId} className="field min-h-48 text-lg leading-7" maxLength={2000} value={value} disabled={disabled} onChange={(event) => { current.current = event.target.value; onChange(event.target.value); }} placeholder="Tell us the café name, location, product, offer and dates. Who is it for?" />
    {interim && <div><p aria-live="polite" className="text-sm italic">Heard so far (not saved): {interim}</p><button className="secondary" type="button" onClick={() => { recognition.current?.stop(); onChange(`${current.current} ${interim}`.trim().slice(0, 2000)); setInterim(""); }}>Keep interim words for editing</button></div>}
    <p className="text-xs">{value.length}/2000 characters. Speech can confuse fifteen and fifty; confirm the number in the facts editor.</p>
    {notice && <p role="status" className="text-sm">{notice}</p>}
  </div>;
}

export function Readback({ text, language = "en-IN" }: { text: string; language?: string }) {
  const [notice, setNotice] = useState("");
  useEffect(() => () => { window.speechSynthesis?.cancel(); }, []);
  const speak = () => {
    if (!("speechSynthesis" in window)) { setNotice("Readback unavailable. Review the text on screen."); return; }
    const voice = window.speechSynthesis.getVoices().find((item) => item.lang.startsWith(language.split("-")[0]));
    if (language === "kn-IN" && !voice) { setNotice("No Kannada voice is installed. Review the Kannada forms as text."); return; }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text); utterance.lang = language;
    if (voice) utterance.voice = voice;
    utterance.onerror = () => setNotice("Readback unavailable. Continue with text review.");
    window.speechSynthesis.speak(utterance); setNotice("Readback does not approve or lock facts.");
  };
  return <div className="text-sm"><button type="button" className="secondary" onClick={speak}><Volume2 size={16}/>{language === "kn-IN" ? "Read Kannada forms aloud" : "Read facts aloud"}</button>{notice && <p role="status" className="mt-2">{notice}</p>}</div>;
}
