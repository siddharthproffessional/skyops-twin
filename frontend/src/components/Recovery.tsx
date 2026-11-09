import React, { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, LabelList } from "recharts";
import type { FlightRow, Plan, Review } from "../types";
import { api } from "../api";
import { fmt, hhmm } from "../lib/time";

const METRICS: { key: string; label: string; unit?: string; good: "low" | "high" }[] = [
  { key: "diversions", label: "Diversions", good: "low" },
  { key: "passenger_delay_hours", label: "Passenger-delay hours", good: "low" },
  { key: "connections_at_risk", label: "Connections at risk", good: "low" },
  { key: "total_departure_delay_min", label: "Departure delay (min)", good: "low" },
  { key: "disrupted_flights", label: "Flights delayed or diverted", good: "low" },
  { key: "max_airborne_hold_min", label: "Max airborne hold (min)", good: "low" },
];

const pct = (b: number, p: number) => (b === 0 ? (p === 0 ? "±0%" : "+∞") : `${p <= b ? "−" : "+"}${Math.abs(Math.round(((p - b) / b) * 100))}%`);

function MiniChart({ plans, k, label }: { plans: Plan[]; k: string; label: string }) {
  const data = plans.map(p => ({ name: p.id === "baseline" ? "Baseline" : p.name.split(" - ")[0], v: p.metrics[k], rec: p.recommended, base: p.id === "baseline" }));
  return (
    <div className="panel p-2.5">
      <div className="text-[10.5px] text-slate-400 font-semibold mb-1">{label}</div>
      <div className="h-[92px]">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 14, right: 4, left: -24, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fill: "#7f97c4", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#4b6391", fontSize: 9 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={{ background: "#0b1730", border: "1px solid #24406e", fontSize: 11 }} />
            <Bar dataKey="v" radius={[3, 3, 0, 0]}>
              {data.map((d, i) => <Cell key={i} fill={d.base ? "#ef4444" : d.rec ? "#22d3ee" : "#3b5b8f"} />)}
              <LabelList dataKey="v" position="top" style={{ fill: "#cbd5e1", fontSize: 10 }} formatter={(v: number) => fmt(v)} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function Recovery({ plans, review, recommendation, approved, status, onApproved }: {
  plans: Plan[]; review: Review | null; recommendation: string | null; approved: string | null; status?: string;
  onApproved: (id: string) => void;
}) {
  const rec = plans.find(p => p.recommended);
  const base = plans.find(p => p.id === "baseline");
  const [sel, setSel] = useState<string | undefined>(rec?.id);
  const [rows, setRows] = useState<{ base: FlightRow[]; plan: FlightRow[] } | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { if (!sel && rec) setSel(rec.id); }, [rec?.id]);
  const plan = plans.find(p => p.id === sel) ?? rec;
  useEffect(() => {
    if (!plan || !base) return;
    Promise.all([api.schedule("baseline"), api.schedule(plan.id)]).then(([b, p]) => setRows({ base: b, plan: p })).catch(() => {});
  }, [plan?.id, plans.length]);

  if (!plans.length || !base || !plan) return (
    <div className="h-full grid place-items-center text-slate-500"><div className="text-center"><div className="text-4xl mb-3 opacity-50">⛭</div>
      No recovery plans yet. Inject a disruption and let the agents work.</div></div>
  );
  const bm = base.metrics, pm = plan.metrics;
  const decide = async (approve: boolean) => {
    setErr("");
    try {
      if (approve) { await api.approve(plan.id, note); onApproved(plan.id); }
      else await api.reject(plan.id, note);
    } catch (e: any) { setErr(e.message); }
  };
  const byId = new Map((rows?.base ?? []).map(r => [r.id, r]));
  return (
    <div className="grid grid-cols-12 gap-3 h-full min-h-0">
      <div className="col-span-8 flex flex-col gap-3 min-h-0 overflow-auto scroll-thin pr-1">
        {/* hero comparison */}
        <div className="panel p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="panel-title">Recommendation · measured by the simulation engine</div>
              <div className="text-[15px] text-slate-100 mt-1.5 leading-snug max-w-3xl">{recommendation}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-[10px] text-slate-500 tracking-widest">OBJECTIVE</div>
              <div className="text-2xl font-black text-cyan-300 mono">{fmt(plan.objective)}</div>
              <div className="text-[11px] text-slate-500 mono">baseline {fmt(base.objective)}</div>
            </div>
          </div>
          <div className="grid grid-cols-6 gap-2 mt-4">
            {METRICS.map(m => {
              const b = bm[m.key], p = pm[m.key];
              const better = p < b, same = p === b;
              return (
                <div key={m.key} className="rounded-lg bg-black/25 border border-white/5 p-2.5">
                  <div className="text-[10px] text-slate-400 leading-tight h-6">{m.label}</div>
                  <div className="flex items-baseline gap-1.5 mt-1">
                    <span className="text-slate-500 line-through text-[12px] mono">{fmt(b)}</span>
                    <span className="text-[20px] font-black mono text-slate-50">{fmt(p)}</span>
                  </div>
                  <div className={`text-[12px] font-bold mono ${same ? "text-slate-400" : better ? "text-emerald-400" : "text-red-400"}`}>{pct(b, p)}</div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {METRICS.map(m => <MiniChart key={m.key} plans={plans} k={m.key} label={m.label} />)}
        </div>
        {/* plan cards */}
        <div className="grid grid-cols-4 gap-2">
          {plans.map(p => (
            <button key={p.id} onClick={() => setSel(p.id)}
              className={`panel p-3 text-left transition ${sel === p.id ? "ring-2 ring-cyan-400/70" : "hover:ring-1 hover:ring-slate-500/50"}`}>
              <div className="flex items-center justify-between">
                <div className="text-[12.5px] font-bold text-slate-100">{p.name}</div>
                {p.recommended && <span className="text-[9px] font-black tracking-widest px-1.5 py-0.5 rounded bg-cyan-400/20 text-cyan-200">RECOMMENDED</span>}
                {approved === p.id && <span className="text-[9px] font-black tracking-widest px-1.5 py-0.5 rounded bg-emerald-400/20 text-emerald-200">APPROVED</span>}
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">{p.source}</div>
              <div className="flex flex-wrap gap-1 mt-2 min-h-[38px]">
                {(p.lever_labels.length ? p.lever_labels : ["No mitigation"]).map(l => <span key={l} className="text-[9.5px] px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-300">{l}</span>)}
              </div>
              <div className="grid grid-cols-3 gap-1 mt-2 text-[10px] mono">
                <div><div className="text-slate-500">div</div><div className="text-slate-100 text-[13px] font-bold">{p.metrics.diversions}</div></div>
                <div><div className="text-slate-500">pax-h</div><div className="text-slate-100 text-[13px] font-bold">{fmt(p.metrics.passenger_delay_hours)}</div></div>
                <div><div className="text-slate-500">valid</div><div className={`text-[13px] font-bold ${p.feasible ? "text-emerald-400" : "text-red-400"}`}>{p.feasible ? "✓" : "✗"}</div></div>
              </div>
            </button>
          ))}
        </div>
        {/* per-flight */}
        <div className="panel p-3">
          <div className="panel-title mb-2">Flight-by-flight: {plan.name} vs baseline</div>
          <div className="max-h-72 overflow-auto scroll-thin">
            <table className="w-full text-[11px] mono">
              <thead className="text-slate-500 sticky top-0 bg-[#0b1730]"><tr>
                {["Flight", "Type", "Pax", "Gate", "Landing", "Off-block", "Baseline delay", "Plan delay", "Δ"].map(h => <th key={h} className="text-left font-semibold py-1 px-1.5">{h}</th>)}
              </tr></thead>
              <tbody>
                {(rows?.plan ?? []).map(r => {
                  const b = byId.get(r.id);
                  const bd = b?.diverted ? null : b?.dep_delay ?? 0;
                  const d = bd === null ? null : r.dep_delay - bd;
                  return (
                    <tr key={r.id} className="border-t border-white/5">
                      <td className="py-1 px-1.5 text-slate-200">{r.id}</td>
                      <td className="px-1.5 text-slate-400">{r.aircraft}</td>
                      <td className="px-1.5 text-slate-400">{r.pax}</td>
                      <td className="px-1.5">{r.planned_gate === r.gate ? <span className="text-slate-300">{r.gate}</span> : <span className="text-amber-300">{r.planned_gate}→{r.gate}</span>}</td>
                      <td className="px-1.5 text-slate-300">{hhmm(r.land)}{r.hold > 1 && <span className="text-orange-300"> (+{Math.round(r.hold)} hold)</span>}</td>
                      <td className="px-1.5 text-slate-300">{hhmm(r.off_block)}</td>
                      <td className="px-1.5">{b?.diverted ? <span className="text-red-400 font-bold">DIVERTED</span> : <span className={bd! > 15 ? "text-amber-300" : "text-slate-400"}>{Math.round(bd!)}m</span>}</td>
                      <td className={`px-1.5 ${r.dep_delay > 15 ? "text-amber-300" : "text-slate-300"}`}>{r.diverted ? "DIVERTED" : `${Math.round(r.dep_delay)}m`}</td>
                      <td className={`px-1.5 font-bold ${d === null ? "text-emerald-400" : d < -1 ? "text-emerald-400" : d > 1 ? "text-red-400" : "text-slate-500"}`}>
                        {d === null ? "saved" : `${d > 0 ? "+" : ""}${Math.round(d)}m`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* right column */}
      <div className="col-span-4 flex flex-col gap-3 min-h-0 overflow-auto scroll-thin">
        <div className="panel p-3">
          <div className="panel-title">Human approval · operations controller</div>
          <div className="text-[12px] text-slate-300 mt-1.5">Selected: <b className="text-slate-100">{plan.name}</b></div>
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Decision note (audit trail)"
            className="w-full mt-2 bg-slate-900/80 border border-slate-600/50 rounded-md text-[12px] px-2 py-1.5 text-slate-100 placeholder:text-slate-500" />
          <div className="grid grid-cols-2 gap-2 mt-2">
            <button disabled={plan.id === "baseline" || !plan.feasible || approved === plan.id} onClick={() => decide(true)}
              className="py-2 rounded-md bg-gradient-to-b from-emerald-500 to-emerald-700 text-white font-bold text-[13px] disabled:opacity-40 shadow-[0_0_24px_rgba(16,185,129,0.25)]">
              {approved === plan.id ? "Approved ✓" : "Approve plan"}</button>
            <button onClick={() => decide(false)} disabled={plan.id === "baseline"}
              className="py-2 rounded-md bg-slate-800 border border-red-500/40 text-red-200 font-bold text-[13px] disabled:opacity-40">Reject</button>
          </div>
          {err && <div className="text-[11px] text-red-300 mt-1.5">{err}</div>}
          <div className="text-[10px] text-slate-500 mt-2">Simulated planning decision. Not a certified aviation safety decision.</div>
        </div>

        {review && (
          <div className="panel p-3">
            <div className="flex items-center justify-between">
              <div className="panel-title">Independent review</div>
              <span className="text-[10px] mono text-fuchsia-300">{review.reviewer}</span>
            </div>
            <div className="text-[12.5px] text-slate-100 mt-1.5">{review.summary}</div>
            <ul className="mt-1.5 space-y-1">{review.findings.map((f, i) => <li key={i} className="text-[11.5px] text-slate-400 flex gap-1.5"><span className="text-fuchsia-400">▸</span>{f}</li>)}</ul>
            {review.disagreement && (
              <div className="mt-2 p-2 rounded-md border border-amber-500/40 bg-amber-500/10">
                <div className="text-[10px] font-black tracking-widest text-amber-300">MODEL DISAGREEMENT · ESCALATED TO CONTROLLER</div>
                <div className="text-[11.5px] text-amber-100 mt-1">{review.disagreement}</div>
              </div>
            )}
          </div>
        )}

        {review && (
          <div className="panel p-3">
            <div className="panel-title mb-1.5">Python constraint validation</div>
            <div className="grid grid-cols-1 gap-1">
              {review.python_validation.checks.map(c => (
                <div key={c} className="flex items-center gap-2 text-[11.5px]"><span className={plan.feasible ? "text-emerald-400" : "text-red-400"}>{plan.feasible ? "✓" : "✗"}</span><span className="text-slate-300">{c}</span></div>
              ))}
            </div>
            <div className="text-[10px] text-slate-500 mt-1.5">AI models never write operational state. Every plan is re-validated by deterministic code.</div>
          </div>
        )}

        <div className="panel p-3 flex-1 min-h-[200px]">
          <div className="panel-title mb-1.5">Operational actions · {plan.name} ({plan.actions.length})</div>
          <div className="space-y-1 max-h-[340px] overflow-auto scroll-thin">
            {plan.actions.length === 0 && <div className="text-[12px] text-slate-500">No changes from standard procedures.</div>}
            {plan.actions.map((a, i) => {
              const icon = a.kind === "diversion_avoided" ? "🛡" : a.kind === "remote_stand" ? "🚌" : a.kind === "gate_change" ? "⇄" : "⇡";
              const cls = a.kind === "diversion_avoided" ? "text-emerald-300" : a.kind === "remote_stand" ? "text-amber-200" : "text-slate-300";
              return <div key={i} className={`text-[11.5px] mono flex gap-2 ${cls}`}><span className="w-4">{icon}</span>{a.text}</div>;
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
