export interface FlightRow {
  id: string; airline: string; aircraft: string; size: string; origin: string; destination: string;
  pax: number; connecting: number; sta: number; std: number; eta: number; planned_gate: string;
  land: number | null; arr_runway: string | null; hold: number; diverted: boolean;
  gate: string | null; gate_kind: string | null; in_request: number | null; gate_in: number | null;
  apron_wait: number; crew: string | null; ta_start: number | null; ta_end: number | null;
  ready: number | null; off_block: number | null; takeoff: number | null; dep_runway: string | null;
  arr_delay: number; dep_delay: number;
}

export interface Metrics { [k: string]: number }

export interface Plan {
  id: string; name: string; source: string; levers: Record<string, unknown>; lever_labels: string[];
  metrics: Metrics; objective: number; feasible: boolean; violations: unknown[];
  actions: { kind: string; flight: string; text: string }[]; recommended?: boolean;
}

export interface AgentEvent {
  type: string; ts?: number; incident?: string; iteration?: number; state_version?: number;
  agent?: string; status?: string; note?: string; from?: string; to?: string; kind?: string; text?: string;
  findings?: string[]; tool?: string; args?: unknown; result?: unknown; ms?: number; between?: string[];
  candidate?: Record<string, unknown>; labels?: string[]; reason?: string; plans?: Plan[];
  [k: string]: unknown;
}

export interface Review {
  reviewer: string; verdict: string; summary: string; findings: string[]; disagreement: string | null;
  alternative: string | null; escalated_to_human?: boolean;
  python_validation: { feasible: boolean; violations: unknown[]; checks: string[] };
}

export interface Disruption {
  label: string; kind: string; start: number; end: number;
  runway_closures: { runway: string; start: number; end: number }[];
  capacity_overrides: { runway: string; capacity_per_hour: number; start: number; end: number }[];
  turnaround_factor: number; gate_closures: { gate: string; start: number; end: number }[];
  crews_unavailable: string[]; flight_delays: Record<string, number>; visibility_m: number | null; wind_kt: number | null;
}

export interface AiStatus {
  mode: string;
  claude: { enabled: boolean; orchestrator_model: string; specialist_model: string };
  openai: { enabled: boolean; reviewer_model: string };
}

export interface StateResp {
  ai: AiStatus; version: number; disruption: Disruption; schedule_name: string; schedule: FlightRow[];
  approved_plan: string | null; running: boolean;
  incident: null | { id: string; label: string; status: string; events: AgentEvent[]; plans: Plan[];
    review: Review | null; recommendation: string | null };
}

export interface Gate { id: string; size: string; zone: string; kind: string }
