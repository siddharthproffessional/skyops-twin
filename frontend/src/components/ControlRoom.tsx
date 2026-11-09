import React, { useMemo } from "react";
import type { AgentEvent } from "../types";
import { AGENTS, AGENT_ORDER } from "../lib/agents";
import AgentFeed, { Avatar } from "./AgentFeed";

export type AgentStatusMap = Record<string, { status: string; note?: string; tools: number; msgs: number; last?: string; brain?: string }>;

export function deriveStatus(events: AgentEvent[]): AgentStatusMap {
  const m: AgentStatusMap = {};
  AGENT_ORDER.forEach(a => (m[a] = { status: "idle", tools: 0, msgs: 0 }));
  for (const e of events) {
    if (e.type === "agent_status" && e.agent && m[e.agent]) { m[e.agent].status = e.status ?? "idle"; if (e.note) m[e.agent].note = e.note; }
    if (e.type === "tool_call" && e.agent && m[e.agent]) m[e.agent].tools++;
    if (e.type === "message" && e.from && m[e.from]) {
      m[e.from].msgs++; m[e.from].last = e.text;
      const out = (e as any).output; if (out?.brain) m[e.from].brain = out.brain;
      if (e.kind === "fallback") m[e.from].brain = "deterministic (fallback)";
    }
  }
  return m;
}

const STATUS_STYLE: Record<string, string> = {
  idle: "text-slate-400 bg-slate-500/10 border-slate-500/30",
  working: "text-sky-300 bg-sky-500/10 border-sky-500/40",
  completed: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
  conflict: "text-red-300 bg-red-500/10 border-red-500/40",
  replanning: "text-amber-300 bg-amber-500/10 border-amber-500/40",
  failed: "text-red-300 bg-red-500/20 border-red-500/60",
};

export function StatusChip({ s }: { s: string }) {
  return <span className={`relative inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-bold tracking-wider uppercase ${STATUS_STYLE[s] ?? STATUS_STYLE.idle}`}>
    <span className={`relative w-1.5 h-1.5 rounded-full bg-current ${s === "working" || s === "replanning" ? "pulse-dot" : ""}`} />{s}
  </span>;
}

function NegotiationGraph({ events, status }: { events: AgentEvent[]; status: AgentStatusMap }) {
  const cx = 260, cy = 200, R = 150;
  const ring = AGENT_ORDER.filter(a => a !== "orchestrator");
  const pos: Record<string, [number, number]> = { orchestrator: [cx, cy] };
  ring.forEach((a, i) => { const ang = -Math.PI / 2 + (i / ring.length) * Math.PI * 2; pos[a] = [cx + R * Math.cos(ang), cy + R * Math.sin(ang)]; });
  const recent = useMemo(() => events.filter(e => e.type === "message").slice(-7), [events]);
  const edges: { a: string; b: string; kind: string; age: number }[] = [];
  recent.forEach((e, i) => {
    const tos = (e.to ?? "").split(",").flatMap(x => x === "all" ? ring : [x.trim()]);
    tos.forEach(t => { if (pos[t] && pos[e.from ?? ""] && t !== e.from) edges.push({ a: e.from!, b: t, kind: e.kind ?? "", age: recent.length - 1 - i }); });
  });
  const col = (k: string) => k === "conflict" ? "#f87171" : k === "reassess" ? "#fbbf24" : k === "proposal" ? "#34d399" : k === "decision" ? "#22d3ee" : "#38bdf8";
  return (
    <svg viewBox="0 0 520 400" className="w-full h-full">
      <circle cx={cx} cy={cy} r={R} fill="none" stroke="rgba(100,140,210,0.12)" strokeDasharray="3 6" />
      {edges.map((e, i) => {
        const [x1, y1] = pos[e.a], [x2, y2] = pos[e.b];
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={col(e.kind)} strokeWidth={e.age === 0 ? 2.4 : 1.2}
          opacity={Math.max(0.12, 1 - e.age * 0.17)} className="flow-line" />;
      })}
      {AGENT_ORDER.map(a => {
        const [x, y] = pos[a]; const s = status[a]?.status ?? "idle"; const ag = AGENTS[a];
        const glow = s === "working" || s === "replanning" ? ag.color : s === "conflict" ? "#ef4444" : undefined;
        const r = a === "orchestrator" ? 34 : 26;
        return (
          <g key={a} transform={`translate(${x},${y})`}>
            {glow && <circle r={r + 8} fill={glow} opacity={0.18}><animate attributeName="r" values={`${r + 4};${r + 12};${r + 4}`} dur="1.4s" repeatCount="indefinite" /></circle>}
            <circle r={r} fill="#0b1832" stroke={s === "conflict" ? "#ef4444" : ag.color} strokeWidth={s === "idle" ? 1 : 2} opacity={s === "idle" ? 0.6 : 1} />
            <text textAnchor="middle" y={4} fontSize={a === "orchestrator" ? 15 : 12} fontWeight={800} fill={ag.color} className="mono">{ag.short}</text>
            <text textAnchor="middle" y={r + 14} fontSize={10} fill="#9fb5dc">{ag.title.replace(" Agent", "")}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function ControlRoom({ events }: { events: AgentEvent[] }) {
  const status = useMemo(() => deriveStatus(events), [events]);
  const versions = events.filter(e => e.type === "state_version");
  const tools = events.filter(e => e.type === "tool_call").length;
  const msgs = events.filter(e => e.type === "message").length;
  const conflicts = events.filter(e => e.type === "conflict").length;
  return (
    <div className="grid grid-cols-12 gap-3 h-full min-h-0">
      <div className="col-span-7 flex flex-col gap-3 min-h-0">
        <div className="grid grid-cols-4 gap-2">
          {AGENT_ORDER.map(a => {
            const ag = AGENTS[a]; const s = status[a];
            return (
              <div key={a} className="panel p-2.5">
                <div className="flex items-center gap-2"><Avatar id={a} size={28} />
                  <div className="min-w-0"><div className="text-[12px] font-semibold truncate" style={{ color: ag.color }}>{ag.title}</div>
                    <div className="text-[10px] text-slate-500 truncate">{ag.role}</div></div></div>
                <div className="flex items-center justify-between mt-2"><StatusChip s={s.status} />
                  <span className="text-[10px] text-slate-500 mono">{s.tools} tools · {s.msgs} msgs</span></div>
                <div className="text-[10px] text-slate-500 mt-1 mono truncate">brain: {s.brain ?? (a === "orchestrator" ? "task workflow" : "–")}</div>
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-5 gap-3 flex-1 min-h-0">
          <div className="panel col-span-3 p-3 flex flex-col min-h-0">
            <div className="flex items-center justify-between"><div className="panel-title">Live negotiation graph</div>
              <div className="text-[10px] text-slate-500 mono">{msgs} messages · {tools} tool calls · {conflicts} conflicts</div></div>
            <div className="flex-1 min-h-0"><NegotiationGraph events={events} status={status} /></div>
          </div>
          <div className="panel col-span-2 p-3 flex flex-col min-h-0">
            <div className="panel-title mb-2">Shared plan versions</div>
            <div className="space-y-2 overflow-auto scroll-thin flex-1">
              {versions.length === 0 && <div className="text-[12px] text-slate-500">No plan drafted yet.</div>}
              {versions.map((v, i) => (
                <div key={i} className="feed-in relative pl-4 border-l border-cyan-500/30">
                  <div className="absolute -left-[5px] top-1 w-2.5 h-2.5 rounded-full bg-cyan-400" />
                  <div className="text-[11px] font-bold text-cyan-300 mono">v{v.state_version}</div>
                  <div className="flex flex-wrap gap-1 mt-0.5">{(v.labels ?? []).map(l => <span key={l} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-400/10 text-cyan-100">{l}</span>)}</div>
                  <div className="text-[10.5px] text-slate-400 mt-0.5">{v.reason}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="col-span-5 panel p-3 flex flex-col min-h-0">
        <div className="panel-title mb-2">Message bus · tool invocations (click to inspect)</div>
        <div className="overflow-auto scroll-thin flex-1 min-h-0 pr-1"><AgentFeed events={events} /></div>
      </div>
    </div>
  );
}
