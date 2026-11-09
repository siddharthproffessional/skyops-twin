import React, { useState } from "react";
import type { AgentEvent } from "../types";
import { AGENTS, KIND_STYLE } from "../lib/agents";

const Avatar = ({ id, size = 26 }: { id: string; size?: number }) => {
  const a = AGENTS[id] ?? { short: "??", color: "#94a3b8" };
  return (
    <div className="shrink-0 rounded-md grid place-items-center font-bold mono"
      style={{ width: size, height: size, fontSize: size * 0.38, color: a.color, background: `${a.color}1f`, border: `1px solid ${a.color}55` }}>
      {a.short}
    </div>
  );
};
export { Avatar };

const toName = (to?: string) => (to ?? "").split(",").map(x => (x === "all" ? "ALL" : AGENTS[x]?.short ?? x)).join(", ");

export function ToolLine({ ev, expandable = true }: { ev: AgentEvent; expandable?: boolean }) {
  const [open, setOpen] = useState(false);
  const a = AGENTS[ev.agent ?? ""];
  return (
    <div className="feed-in">
      <button onClick={() => expandable && setOpen(!open)}
        className="w-full text-left flex items-center gap-2 text-[11px] mono text-slate-400 hover:text-slate-200 py-0.5 pl-9">
        <span style={{ color: a?.color }}>⚙</span>
        <span className="text-slate-300">{ev.tool}</span>
        <span className="text-slate-500 truncate">{ev.args && Object.keys(ev.args as object).length ? JSON.stringify(ev.args) : "()"}</span>
        <span className="ml-auto text-slate-600">{ev.ms}ms</span>
      </button>
      {open && <pre className="ml-9 mb-1 p-2 rounded bg-black/40 text-[10px] leading-snug text-slate-300 max-h-60 overflow-auto scroll-thin">
        {JSON.stringify(ev.result, null, 1)}</pre>}
    </div>
  );
}

export function MessageCard({ ev }: { ev: AgentEvent }) {
  const from = ev.from ?? "orchestrator";
  const style = KIND_STYLE[ev.kind ?? "finding"] ?? KIND_STYLE.finding;
  const a = AGENTS[from];
  const isConflict = ev.kind === "conflict";
  return (
    <div className={`feed-in flex gap-2.5 p-2 rounded-lg ${isConflict ? "bg-red-500/[0.06] ring-1 ring-red-500/25" : ""}`}>
      <Avatar id={from} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[11px]">
          <span className="font-semibold" style={{ color: a?.color }}>{a?.title ?? from}</span>
          <span className="text-slate-600">→</span>
          <span className="text-slate-400 mono">{toName(ev.to)}</span>
          <span className={`ml-auto px-1.5 py-[1px] rounded border text-[9px] font-bold tracking-wider ${style.cls}`}>{style.label}</span>
        </div>
        {ev.text && <div className="text-[12.5px] text-slate-200 mt-0.5 leading-snug">{ev.text}</div>}
        {ev.findings && ev.findings.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {ev.findings.map((f, i) => <li key={i} className="text-[11.5px] text-slate-400 leading-snug flex gap-1.5"><span className="text-slate-600">▸</span>{f}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function AgentFeed({ events, showTools = true }: { events: AgentEvent[]; showTools?: boolean }) {
  const items = events.filter(e => e.type === "message" || (showTools && e.type === "tool_call") || e.type === "state_version" || e.type === "search" || e.type === "approval");
  if (!items.length) return (
    <div className="h-full grid place-items-center text-center text-slate-500 text-sm px-6">
      <div><div className="text-3xl mb-2 opacity-60">◎</div>Agents are idle. Inject a disruption to open an incident.</div>
    </div>
  );
  return (
    <div className="space-y-1">
      {items.slice().reverse().map((ev, i) => {
        if (ev.type === "tool_call") return <ToolLine key={i} ev={ev} />;
        if (ev.type === "state_version") return (
          <div key={i} className="feed-in mx-1 my-1.5 p-2 rounded-lg border border-cyan-500/25 bg-cyan-500/[0.05]">
            <div className="text-[10px] font-bold tracking-widest text-cyan-300">SHARED PLAN · v{ev.state_version}</div>
            <div className="flex flex-wrap gap-1 mt-1">{(ev.labels ?? []).map(l => <span key={l} className="text-[10.5px] px-1.5 py-0.5 rounded bg-cyan-400/10 text-cyan-200">{l}</span>)}</div>
            {ev.reason && <div className="text-[11px] text-slate-400 mt-1">{ev.reason}</div>}
          </div>
        );
        if (ev.type === "search") return ev.status === "running" ? (
          <div key={i} className="feed-in mx-1 p-2 rounded-lg border border-cyan-500/20 text-[11.5px] text-cyan-200 flex items-center gap-2">
            <span className="blink">◉</span>{ev.text}
          </div>) : null;
        if (ev.type === "approval") return (
          <div key={i} className={`feed-in mx-1 my-1.5 p-2 rounded-lg border text-[12px] font-semibold ${ev.decision === "approved" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200" : "border-red-500/40 bg-red-500/10 text-red-200"}`}>
            Controller {String(ev.decision).toUpperCase()} {String(ev.plan_name ?? ev.plan_id)}
          </div>);
        return <MessageCard key={i} ev={ev} />;
      })}
    </div>
  );
}
