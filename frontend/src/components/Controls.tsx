import React, { useState } from "react";
import { api } from "../api";
import type { FlightRow } from "../types";

const Btn = ({ children, onClick, tone = "slate", disabled }: { children: React.ReactNode; onClick: () => void; tone?: string; disabled?: boolean }) => {
  const tones: Record<string, string> = {
    amber: "bg-gradient-to-b from-amber-500/90 to-orange-600/90 text-white border-amber-400/50 shadow-[0_0_24px_rgba(245,158,11,0.25)] hover:brightness-110",
    slate: "bg-slate-800/70 text-slate-200 border-slate-600/50 hover:bg-slate-700/80",
    red: "bg-red-900/40 text-red-200 border-red-500/40 hover:bg-red-800/50",
  };
  return <button disabled={disabled} onClick={onClick}
    className={`px-2.5 py-1.5 rounded-md border text-[12px] font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]}`}>{children}</button>;
};

export default function Controls({ running, flights, onError, onInfo }: {
  running: boolean; flights: FlightRow[]; onError: (s: string) => void; onInfo: (s: string) => void;
}) {
  const [text, setText] = useState("");
  const [metar, setMetar] = useState("OSKY 091420Z 31038G45KT 0600 BLSA VV005 34/12 Q1002");
  const [fid, setFid] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async (p: Promise<any>) => {
    setBusy(true);
    try {
      const r = await p;
      if (r && r.accepted === false) onError(r.message || "Event not accepted");
      else if (r?.spec) onInfo(`Event mapped (${r.method}): ${r.spec.type}`);
    } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };
  const dis = running || busy;
  return (
    <div className="space-y-3">
      <Btn tone="amber" disabled={dis} onClick={() => go(api.scenario("sandstorm"))}>
        <span className="flex items-center gap-2 text-[13px]"><span>🌪</span> Inject OPERATION SANDSTORM</span>
      </Btn>
      <div className="grid grid-cols-2 gap-1.5">
        <Btn disabled={dis} onClick={() => go(api.disruption("runway_closure", { runway: "30L", start_min: 30, duration_min: 60 }))}>Close 30L (60 min)</Btn>
        <Btn disabled={dis} onClick={() => go(api.disruption("capacity_reduction", { runway: "30R", capacity_per_hour: 14, start_min: 20, duration_min: 90 }))}>30R → 14 mvts/h</Btn>
        <Btn disabled={dis} onClick={() => go(api.disruption("crew_unavailable", { count: 3 }))}>Remove 3 crews</Btn>
        <Btn disabled={dis} onClick={() => go(api.disruption("gate_closure", { gate: "A2", duration_min: 150 }))}>Close gate A2</Btn>
      </div>
      <div className="flex gap-1.5">
        <select value={fid} onChange={e => setFid(e.target.value)}
          className="flex-1 bg-slate-900/80 border border-slate-600/50 rounded-md text-[12px] px-2 py-1.5 text-slate-200 mono">
          <option value="">Delay a flight…</option>
          {flights.map(f => <option key={f.id} value={f.id}>{f.id} · {f.aircraft} · {f.origin}</option>)}
        </select>
        <Btn disabled={dis || !fid} onClick={() => go(api.disruption("flight_delay", { flight_id: fid, minutes: 50 }))}>+50 min</Btn>
      </div>
      <div>
        <div className="panel-title mb-1">Judge's event (free text)</div>
        <div className="flex gap-1.5">
          <input value={text} onChange={e => setText(e.target.value)} placeholder='e.g. "Debris on 30L, closed 45 min at 14:40"'
            onKeyDown={e => { if (e.key === "Enter" && text.trim().length > 2 && !dis) go(api.freetext(text)); }}
            className="flex-1 bg-slate-900/80 border border-slate-600/50 rounded-md text-[12px] px-2 py-1.5 text-slate-100 placeholder:text-slate-500" />
          <Btn disabled={dis || text.trim().length < 3} onClick={() => go(api.freetext(text))}>Send</Btn>
        </div>
      </div>
      <div>
        <div className="panel-title mb-1">Live weather feed (METAR adapter)</div>
        <div className="flex gap-1.5">
          <input value={metar} onChange={e => setMetar(e.target.value)}
            className="flex-1 bg-slate-900/80 border border-slate-600/50 rounded-md text-[11px] px-2 py-1.5 text-slate-100 mono" />
          <Btn disabled={dis} onClick={() => go(api.metar(metar))}>Ingest</Btn>
        </div>
      </div>
      <div className="pt-1 flex justify-end">
        <Btn tone="red" onClick={() => go(api.reset())}>Reset day</Btn>
      </div>
    </div>
  );
}
