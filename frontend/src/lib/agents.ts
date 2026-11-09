export const AGENTS: Record<string, { title: string; short: string; color: string; role: string }> = {
  orchestrator: { title: "Operations Orchestrator", short: "OR", color: "#38bdf8", role: "Coordinates, versions the plan, resolves conflicts" },
  weather: { title: "Weather Agent", short: "WX", color: "#a78bfa", role: "Turns weather into operating restrictions" },
  runway: { title: "Runway Agent", short: "RW", color: "#f472b6", role: "Capacity, holding and diversion risk" },
  flight: { title: "Flight Agent", short: "FL", color: "#34d399", role: "Sequencing by passengers and connections" },
  gate: { title: "Gate Agent", short: "GT", color: "#fbbf24", role: "Stands, compatibility and conflicts" },
  ground: { title: "Ground Ops Agent", short: "GO", color: "#fb923c", role: "Turnaround crews and bottlenecks" },
  recovery: { title: "Recovery Agent", short: "RC", color: "#22d3ee", role: "Searches, simulates and ranks plans" },
  reviewer: { title: "Independent Reviewer", short: "RV", color: "#e879f9", role: "Critiques the plan (OpenAI when configured)" },
};
export const AGENT_ORDER = ["orchestrator", "weather", "runway", "flight", "gate", "ground", "recovery", "reviewer"];

export const KIND_STYLE: Record<string, { label: string; cls: string }> = {
  task: { label: "TASK", cls: "bg-sky-500/15 text-sky-300 border-sky-500/30" },
  finding: { label: "FINDING", cls: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
  proposal: { label: "PROPOSAL", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  conflict: { label: "CONFLICT", cls: "bg-red-500/15 text-red-300 border-red-500/40" },
  reassess: { label: "REASSESS", cls: "bg-amber-500/15 text-amber-300 border-amber-500/40" },
  decision: { label: "DECISION", cls: "bg-cyan-500/15 text-cyan-300 border-cyan-500/40" },
  fallback: { label: "FALLBACK", cls: "bg-zinc-500/15 text-zinc-300 border-zinc-500/40" },
};
