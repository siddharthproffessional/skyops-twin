/**
 * Serverless mode (e.g. Vercel): no WebSocket and no server-side session.
 * The backend runs the whole agent incident in one request (/api/run) and returns the real
 * event log; this module streams that log into the UI at a readable pace and keeps the
 * session state (approval etc.) in the browser.
 */
import type { AgentEvent, FlightRow, Plan, StateResp } from "../types";

type Listener = (ev: AgentEvent) => void;
const BASE: string = (import.meta as any).env?.VITE_API_BASE ?? "";
const post = async (path: string, body: unknown) => {
  const r = await fetch(BASE + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
};

const listeners = new Set<Listener>();
const emit = (ev: AgentEvent) => listeners.forEach(l => l(ev));

interface Session {
  ai: any; version: number; disruption: any; baseline: FlightRow[]; nominal: FlightRow[];
  incident: null | { id: string; label: string; status: string; events: AgentEvent[]; plans: (Plan & { schedule: FlightRow[] })[];
    review: any; recommendation: string | null };
  approved: string | null; running: boolean; runId: number;
}
const NONE = { label: "Normal operations", kind: "none", start: 0, end: 0, runway_closures: [], capacity_overrides: [],
  turnaround_factor: 1, gate_closures: [], crews_unavailable: [], flight_delays: {}, visibility_m: null, wind_kt: null };
const S: Session = { ai: null, version: 1, disruption: NONE, baseline: [], nominal: [], incident: null, approved: null, running: false, runId: 0 };

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
const PACE: Record<string, number> = { message: 420, agent_status: 160, conflict: 500, tool_call: 120, state_version: 500 };

async function ensureInit() {
  if (!S.ai) S.ai = (await fetch(BASE + "/api/health").then(r => r.json())).ai;
  if (!S.nominal.length) S.nominal = await fetch(BASE + "/api/schedules/nominal").then(r => r.json());
}

async function start(body: Record<string, unknown>) {
  if (S.running) throw new Error("Agents are still working on the current incident.");
  await ensureInit();
  const pre = await post("/api/preview", body);
  const id = ++S.runId;
  S.disruption = pre.disruption; S.baseline = pre.schedule; S.approved = null; S.running = true; S.version++;
  S.incident = { id: "…", label: pre.label, status: "running", events: [], plans: [], review: null, recommendation: null };
  emit({ type: "disruption", disruption: pre.disruption });
  const pending: AgentEvent = { type: "search", status: "running", text: "Agents are negotiating on the server (serverless mode: the real message log streams in when the run completes)" };
  S.incident.events.push(pending); emit(pending);
  let run: any;
  try { run = await post("/api/run", body); }
  catch (e) { S.running = false; if (S.incident) S.incident.status = "failed"; emit({ type: "incident_status", status: "failed" }); throw e; }
  if (id !== S.runId || !S.incident) return pre;
  S.incident.id = run.incident; S.ai = run.ai;
  S.incident.events = S.incident.events.filter(e => e !== pending);
  for (const ev of run.events as AgentEvent[]) {
    if (id !== S.runId) return pre;
    S.incident.events.push(ev);
    if (ev.type === "plans") { S.incident.plans = run.plans; }
    if (ev.type === "review") S.incident.review = run.review;
    if (ev.type === "recommendation") { S.incident.recommendation = run.recommendation; S.incident.status = "awaiting_approval"; S.running = false; }
    emit(ev);
    await sleep(PACE[ev.type] ?? 80);
  }
  S.incident.plans = run.plans; S.incident.review = run.review; S.incident.recommendation = run.recommendation;
  S.incident.status = "awaiting_approval"; S.running = false;
  emit({ type: "incident_status", status: "awaiting_approval" });
  return { accepted: true, spec: run.spec, method: run.method };
}

export const serverless = {
  airport: () => fetch(BASE + "/api/airport").then(r => r.json()),
  subscribe(l: Listener) { listeners.add(l); setTimeout(() => l({ type: "hello" }), 0); return () => listeners.delete(l); },
  async state(): Promise<StateResp> {
    await ensureInit();
    const inc = S.incident;
    let name = "Normal operations", sched = S.nominal;
    if (inc && S.approved) { const p = inc.plans.find(p => p.id === S.approved)!; name = p.name; sched = p.schedule; }
    else if (S.disruption.kind !== "none") { name = "Baseline response (unmitigated)"; sched = S.baseline; }
    return {
      ai: S.ai, version: S.version, disruption: S.disruption, schedule_name: name, schedule: sched, approved_plan: S.approved,
      running: S.running,
      incident: inc ? { id: inc.id, label: inc.label, status: inc.status, events: inc.events,
        plans: inc.plans.map(({ schedule, ...p }) => p as Plan), review: inc.review, recommendation: inc.recommendation } : null,
    };
  },
  scenario: (id: string) => start({ scenario_id: id }),
  disruption: (type: string, params: Record<string, unknown>) => start({ type, params }),
  freetext: (text: string) => start({ text }),
  metar: (raw: string) => start({ metar: raw }),
  async schedule(id: string) {
    await ensureInit();
    if (id === "nominal") return S.nominal;
    const p = S.incident?.plans.find(p => p.id === id);
    if (!p) throw new Error("unknown plan");
    return p.schedule;
  },
  async approve(id: string, note = "") {
    const p = S.incident?.plans.find(p => p.id === id);
    if (!p || !p.feasible) throw new Error("plan cannot be approved");
    S.approved = id; S.version++; S.incident!.status = "approved";
    const ev = { type: "approval", decision: "approved", plan_id: id, plan_name: p.name, note };
    S.incident!.events.push(ev); emit(ev); return ev;
  },
  async reject(id: string, note = "") {
    if (!S.incident) throw new Error("no incident");
    S.incident.status = "rejected";
    const ev = { type: "approval", decision: "rejected", plan_id: id, note };
    S.incident.events.push(ev); emit(ev); return ev;
  },
  async reset() {
    S.runId++; S.disruption = NONE; S.incident = null; S.approved = null; S.running = false; S.version = 1;
    emit({ type: "reset" }); return { ok: true };
  },
};
