import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, connectStream } from "./api";
import type { AgentEvent, FlightRow, Gate, StateResp } from "./types";
import AirportTwin from "./components/AirportTwin";
import AgentFeed from "./components/AgentFeed";
import Controls from "./components/Controls";
import ControlRoom, { deriveStatus, StatusChip } from "./components/ControlRoom";
import Recovery from "./components/Recovery";
import { kpisAt } from "./lib/twin";
import { hhmm, fmt } from "./lib/time";
import { AGENTS, AGENT_ORDER } from "./lib/agents";

type Tab = "command" | "agents" | "recovery";
const SPEEDS = [1, 3, 6, 12];

function Kpi({ label, value, tone = "slate", sub }: { label: string; value: React.ReactNode; tone?: string; sub?: string }) {
  const c: Record<string, string> = { slate: "text-slate-50", amber: "text-amber-300", red: "text-red-400", cyan: "text-cyan-300", green: "text-emerald-300", orange: "text-orange-300" };
  return (
    <div className="panel px-3 py-2">
      <div className="text-[9.5px] tracking-[0.14em] uppercase text-slate-500 font-semibold">{label}</div>
      <div className={`text-[22px] leading-tight font-black mono ${c[tone]}`}>{value}</div>
      {sub && <div className="text-[10px] text-slate-500 -mt-0.5">{sub}</div>}
    </div>
  );
}

function Logo() {
  return (
    <svg width="34" height="34" viewBox="0 0 34 34">
      <circle cx="17" cy="17" r="15" fill="#0b1730" stroke="#38bdf8" strokeWidth="1.5" />
      <circle cx="17" cy="17" r="9" fill="none" stroke="#38bdf8" strokeOpacity=".35" />
      <path d="M17 17 L17 3 A14 14 0 0 1 29 10 Z" fill="#38bdf8" opacity=".25">
        <animateTransform attributeName="transform" type="rotate" from="0 17 17" to="360 17 17" dur="4s" repeatCount="indefinite" />
      </path>
      <path d="M17 8 L19.5 17 L17 26 L14.5 17Z" fill="#e0f2fe" />
    </svg>
  );
}

export default function App() {
  const [st, setSt] = useState<StateResp | null>(null);
  const [gates, setGates] = useState<Gate[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [tab, setTab] = useState<Tab>("command");
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(3);
  const [compare, setCompare] = useState<{ base: FlightRow[]; plan: FlightRow[]; name: string; bm?: Record<string, number>; pm?: Record<string, number> } | null>(null);
  const [toast, setToast] = useState<{ text: string; tone: string } | null>(null);
  const [connected, setConnected] = useState(false);
  const tRef = useRef(0);
  tRef.current = t;

  const refresh = useCallback(async () => {
    const s: StateResp = await api.state();
    setSt(s);
    if (s.incident) setEvents(s.incident.events);
    return s;
  }, []);

  useEffect(() => {
    api.airport().then(a => setGates(a.gates));
    refresh();
  }, [refresh]);

  const startCompare = useCallback(async (planId: string, s?: StateResp) => {
    const [b, p] = await Promise.all([api.schedule("baseline"), api.schedule(planId)]);
    const st2 = s ?? (await api.state());
    const pl = st2.incident?.plans.find((x: { id: string }) => x.id === planId);
    const bl = st2.incident?.plans.find((x: { id: string }) => x.id === "baseline");
    setCompare({ base: b, plan: p, name: pl?.name ?? planId, bm: bl?.metrics, pm: pl?.metrics });
    setT(Math.max(0, (st2.disruption.start ?? 0) - 4));
    setSpeed(3);
    setPlaying(true);
    setTab("command");
  }, []);

  // live event stream (WebSocket, or in-browser replay in serverless mode)
  useEffect(() => {
    const onEvent = async (ev: AgentEvent) => {
      if (ev.type === "hello") return;
      if (ev.type === "reset") { setEvents([]); setCompare(null); setT(0); setPlaying(false); refresh(); return; }
      if (ev.type === "disruption") {
        setEvents([]); setCompare(null);
        const s = await refresh();
        setT(Math.max(0, (s.disruption.start ?? 0) - 6)); setSpeed(1); setPlaying(true);
        return;
      }
      setEvents(prev => [...prev, ev]);
      if (["plans", "review", "recommendation", "incident_status"].includes(ev.type)) refresh();
      if (ev.type === "recommendation") setToast({ text: "Recovery plan ready — awaiting controller approval", tone: "cyan" });
      if (ev.type === "approval" && ev.decision === "approved") { const s = await refresh(); startCompare(String(ev.plan_id), s); }
    };
    return connectStream(onEvent, setConnected);
  }, [refresh, startCompare]);

  // sim clock
  useEffect(() => {
    if (!playing) return;
    let raf = 0; let last = performance.now();
    const loop = (now: number) => {
      const dt = (now - last) / 1000; last = now;
      const nt = tRef.current + dt * speed;
      if (nt >= 300) { setT(300); setPlaying(false); return; }
      setT(nt);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed]);

  useEffect(() => { if (toast) { const id = setTimeout(() => setToast(null), 4500); return () => clearTimeout(id); } }, [toast]);

  const rows = st?.schedule ?? [];
  const k = useMemo(() => kpisAt(rows, t), [rows, t]);
  const d = st?.disruption;
  const inc = st?.incident;
  const status = useMemo(() => deriveStatus(events), [events]);
  const working = AGENT_ORDER.filter(a => ["working", "replanning"].includes(status[a]?.status));
  const rwOpen = d ? 2 - new Set(d.runway_closures.filter(c => t >= c.start && t < c.end).map(c => c.runway)).size : 2;
  const stormNow = d && d.kind !== "none" && t >= d.start && t < d.end;

  if (!st) return <div className="h-full grid place-items-center text-slate-400">Connecting to SkyOps Twin backend…</div>;

  const incidentBadge = !inc ? null : inc.status === "running"
    ? <span className="text-sky-300 blink">● AGENTS WORKING · {working.map(a => AGENTS[a].short).join(" ")}</span>
    : inc.status === "awaiting_approval" ? <span className="text-amber-300">● AWAITING CONTROLLER APPROVAL</span>
    : inc.status === "approved" ? <span className="text-emerald-300">● PLAN APPROVED · {st.schedule_name}</span>
    : <span className="text-red-300">● {inc.status.toUpperCase()}</span>;

  return (
    <div className="h-full flex flex-col p-3 gap-3 bg-[radial-gradient(ellipse_at_top,_#0d1d3d_0%,_#050b18_60%)]">
      {/* header */}
      <header className="flex items-center gap-4">
        <Logo />
        <div>
          <div className="text-[19px] font-black tracking-[0.22em] text-slate-50">SKYOPS <span className="text-sky-400">TWIN</span></div>
          <div className="text-[10.5px] text-slate-400 tracking-wider">AUTONOMOUS MULTI-AGENT AIRPORT RECOVERY · SKYOPS INTERNATIONAL (SYNTHETIC HUB)</div>
        </div>
        <nav className="ml-6 flex gap-1 p-1 rounded-lg bg-slate-900/70 border border-slate-700/50">
          {([["command", "Command Centre"], ["agents", "Agent Control Room"], ["recovery", "Recovery & Analytics"]] as [Tab, string][]).map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`px-3 py-1.5 rounded-md text-[12px] font-semibold transition ${tab === id ? "bg-sky-500/20 text-sky-200 ring-1 ring-sky-400/40" : "text-slate-400 hover:text-slate-200"}`}>
              {label}{id === "recovery" && inc?.status === "awaiting_approval" && <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-amber-400 blink" />}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] text-slate-500 tracking-widest">SIM CLOCK</div>
            <div className="text-[24px] leading-none font-black mono text-slate-50">{hhmm(t)}</div>
          </div>
          <div className="panel px-2.5 py-1.5 text-[10.5px] leading-tight">
            <div className="text-slate-500 tracking-widest">AI ENGINE</div>
            {st.ai.claude.enabled
              ? <div className="text-emerald-300 font-semibold">Claude {st.ai.claude.specialist_model}{st.ai.openai.enabled ? " · OpenAI reviewer" : ""}</div>
              : <div className="text-amber-200 font-semibold" title="Set ANTHROPIC_API_KEY and OPENAI_API_KEY to run live models">Deterministic agent policy</div>}
          </div>
          <div className="panel px-2.5 py-1.5 text-[10.5px] leading-tight">
            <div className="text-slate-500 tracking-widest">STATE</div>
            <div className="text-slate-200 mono font-semibold">v{st.version} · <span className={connected ? "text-emerald-400" : "text-red-400"}>{connected ? "LIVE" : "OFFLINE"}</span></div>
          </div>
        </div>
      </header>

      {/* disruption banner */}
      {d && d.kind !== "none" && (
        <div className={`rounded-lg px-4 py-2 flex items-center gap-4 border ${stormNow ? "bg-gradient-to-r from-amber-900/60 via-orange-900/40 to-transparent border-amber-500/40" : "bg-slate-900/60 border-slate-600/40"}`}>
          <div className={`text-[13px] font-black tracking-[0.2em] ${stormNow ? "text-amber-300" : "text-slate-300"}`}>⚠ {d.label.toUpperCase()}</div>
          <div className="text-[11.5px] text-amber-100/80 mono flex flex-wrap gap-x-4">
            {d.visibility_m && <span>VIS {d.visibility_m} m</span>}
            {d.wind_kt && <span>WIND {d.wind_kt} kt</span>}
            {d.runway_closures.map((c, i) => <span key={i}>{c.runway} CLOSED {hhmm(c.start)}–{hhmm(c.end)}</span>)}
            {d.capacity_overrides.map((c, i) => <span key={i}>{c.runway} {c.capacity_per_hour}/h</span>)}
            {d.turnaround_factor > 1 && <span>TURNAROUND ×{d.turnaround_factor}</span>}
            {d.gate_closures.length > 0 && <span>GATES {d.gate_closures.map(g => g.gate).join("/")} CLOSED</span>}
            {d.crews_unavailable.length > 0 && <span>CREWS −{d.crews_unavailable.length}</span>}
          </div>
          <div className="ml-auto text-[11.5px] font-bold tracking-wider">{incidentBadge}</div>
        </div>
      )}

      <main className="flex-1 min-h-0">
        {tab === "command" && (
          <div className="h-full flex flex-col gap-3 min-h-0">
            {!compare && (
              <div className="grid grid-cols-8 gap-2">
                <Kpi label="Flights today" value={rows.length} sub={st.schedule_name} />
                <Kpi label="Airborne inbound" value={k.airborne} tone="cyan" />
                <Kpi label="In holding" value={k.holding} tone={k.holding ? "orange" : "slate"} />
                <Kpi label="On stand" value={k.onStand} />
                <Kpi label="Departed" value={k.departed} tone="green" />
                <Kpi label="Delayed departures" value={k.delayedDeps} tone={k.delayedDeps ? "amber" : "slate"} sub=">15 min" />
                <Kpi label="Diversions" value={k.diverted} tone={k.diverted ? "red" : "slate"} />
                <Kpi label="Runways open" value={`${rwOpen}/2`} tone={rwOpen < 2 ? "red" : "green"} />
              </div>
            )}
            {compare ? (
              <div className="flex-1 min-h-0 grid grid-cols-2 gap-3">
                {[{ title: "WITHOUT SKYOPS · standard procedures", rows: compare.base, tone: "red", m: compare.bm },
                  { title: `WITH SKYOPS · ${compare.name}`, rows: compare.plan, tone: "cyan", m: compare.pm }].map(side => {
                  const kk = kpisAt(side.rows, t);
                  return (
                    <div key={side.title} className={`panel p-2 flex flex-col min-h-0 ${side.tone === "cyan" ? "ring-1 ring-cyan-400/40" : "ring-1 ring-red-500/30"}`}>
                      <div className="flex items-center justify-between px-1 pb-1.5">
                        <div className={`text-[12px] font-black tracking-widest ${side.tone === "cyan" ? "text-cyan-300" : "text-red-300"}`}>{side.title}</div>
                        <div className="flex gap-3 text-[11px] mono">
                          <span className="text-orange-300">HOLD {kk.holding}</span>
                          <span className="text-amber-300">DELAYED {kk.delayedDeps}</span>
                          <span className="text-red-400">DIVERTED {kk.diverted}</span>
                          <span className="text-emerald-300">DEP {kk.departed}</span>
                        </div>
                      </div>
                      <div className="flex-1 min-h-0 rounded-lg overflow-hidden bg-[#060f22]">
                        <AirportTwin rows={side.rows} t={t} gates={gates} disruption={d!} compact />
                      </div>
                      {side.m && (
                        <div className="grid grid-cols-4 gap-2 pt-2">
                          {[["Diversions", "diversions"], ["Passenger-delay hours", "passenger_delay_hours"], ["Connections at risk", "connections_at_risk"], ["Departure delay (min)", "total_departure_delay_min"]].map(([lab, key]) => (
                            <div key={key} className="rounded-lg bg-black/30 border border-white/5 px-3 py-2">
                              <div className="text-[9.5px] tracking-widest uppercase text-slate-500">Day total · {lab}</div>
                              <div className={`text-[26px] font-black mono ${side.tone === "cyan" ? "text-cyan-300" : "text-red-300"}`}>{fmt(side.m![key])}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex-1 min-h-0 grid grid-cols-12 gap-3">
                <div className="col-span-8 panel p-2 min-h-0 flex flex-col">
                  <div className="flex-1 min-h-0 rounded-lg overflow-hidden bg-[#060f22]">
                    <AirportTwin rows={rows} t={t} gates={gates} disruption={d!} title={st.schedule_name.toUpperCase()} />
                  </div>
                </div>
                <div className="col-span-4 flex flex-col gap-3 min-h-0">
                  <div className="panel p-3 flex-1 min-h-0 flex flex-col">
                    <div className="flex items-center justify-between mb-2">
                      <div className="panel-title">Live agent coordination</div>
                      {inc && <span className="text-[10px] mono text-slate-500">{inc.id}</span>}
                    </div>
                    <div className="flex gap-1 mb-2 flex-wrap">
                      {AGENT_ORDER.map(a => (
                        <div key={a} title={AGENTS[a].title} className="flex items-center gap-1 text-[9.5px] mono px-1.5 py-0.5 rounded border border-white/5 bg-black/20">
                          <span style={{ color: AGENTS[a].color }} className="font-bold">{AGENTS[a].short}</span>
                          <span className={`w-1.5 h-1.5 rounded-full ${status[a].status === "working" || status[a].status === "replanning" ? "bg-sky-400 blink" : status[a].status === "conflict" ? "bg-red-500" : status[a].status === "completed" ? "bg-emerald-400" : "bg-slate-600"}`} />
                        </div>
                      ))}
                    </div>
                    <div className="flex-1 overflow-auto scroll-thin pr-1 min-h-0"><AgentFeed events={events} showTools={false} /></div>
                    {inc?.status === "awaiting_approval" && (
                      <button onClick={() => setTab("recovery")} className="mt-2 py-2 rounded-md bg-gradient-to-r from-cyan-500 to-sky-600 text-white font-bold text-[13px] shadow-[0_0_28px_rgba(34,211,238,0.3)]">
                        Review recovery plan →</button>
                    )}
                  </div>
                  <div className="panel p-3">
                    <div className="panel-title mb-2">Disruption management</div>
                    <Controls running={st.running} flights={rows} onError={(s) => setToast({ text: s, tone: "red" })} onInfo={(s) => setToast({ text: s, tone: "cyan" })} />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
        {tab === "agents" && <ControlRoom events={events} />}
        {tab === "recovery" && <Recovery plans={inc?.plans ?? []} review={inc?.review ?? null} recommendation={inc?.recommendation ?? null}
          approved={st.approved_plan} status={inc?.status} onApproved={() => {}} />}
      </main>

      {/* playback */}
      <footer className="panel px-3 py-2 flex items-center gap-3">
        <button onClick={() => setPlaying(!playing)} className="w-9 h-9 rounded-full bg-sky-500/20 text-sky-200 ring-1 ring-sky-400/40 font-bold">{playing ? "❚❚" : "▶"}</button>
        <div className="flex gap-1">
          {SPEEDS.map(s => <button key={s} onClick={() => setSpeed(s)} className={`px-2 py-1 rounded text-[11px] mono ${speed === s ? "bg-sky-500/25 text-sky-200" : "text-slate-400 hover:text-slate-200"}`}>{s}×</button>)}
        </div>
        <span className="text-[10px] text-slate-500 mono">sim-min/s</span>
        <div className="flex-1 relative">
          <input type="range" min={0} max={300} step={0.5} value={t} onChange={e => setT(parseFloat(e.target.value))} className="w-full accent-sky-400" />
          {d && d.end > d.start && <div className="absolute top-0 h-1.5 bg-amber-500/50 rounded pointer-events-none" style={{ left: `${(d.start / 300) * 100}%`, width: `${((d.end - d.start) / 300) * 100}%` }} />}
        </div>
        <span className="text-[11px] mono text-slate-400 w-24 text-right">{hhmm(0)}–{hhmm(300)}</span>
        {compare && <button onClick={() => setCompare(null)} className="px-2.5 py-1.5 rounded-md text-[11.5px] font-semibold bg-slate-800 text-slate-200 border border-slate-600/50">Exit comparison</button>}
        {!compare && st.approved_plan && <button onClick={() => startCompare(st.approved_plan!)} className="px-2.5 py-1.5 rounded-md text-[11.5px] font-semibold bg-cyan-500/20 text-cyan-200 border border-cyan-400/40">Replay side-by-side</button>}
      </footer>
      <p className="text-center text-[10.5px] text-slate-500 mono">© 2026 Siddharth Dialani · SkyOps Twin · All rights reserved</p>

      {toast && (
        <div className={`fixed bottom-20 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-[13px] font-semibold shadow-2xl border ${toast.tone === "red" ? "bg-red-950/90 border-red-500/50 text-red-100" : "bg-slate-900/95 border-cyan-400/50 text-cyan-100"}`}>
          {toast.text}</div>
      )}
    </div>
  );
}
