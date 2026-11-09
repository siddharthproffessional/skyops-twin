import type { FlightRow } from "../types";

// ---------------------------------------------------------------- layout (SVG units, viewBox 1200 x 640)
export const W = 1200, H = 640;
export const RWY = { "30L": 60, "30R": 580 } as Record<string, number>;
export const TWY = { "30L": 108, "30R": 532 } as Record<string, number>;
export const RWY_X0 = 140, RWY_X1 = 1000;   // threshold for runway 30 is the east end (x1)
export const EXIT_X = 600;
export const LANE_N = 150, LANE_S = 490, CROSS_X = 1032, REMOTE_X = 214;
export const STACK = { x: 1118, y: 320, rx: 52, ry: 118 };
const MAX_HOLD = 45;

export type Pt = [number, number];

const gateX = (id: string): number => {
  const n = parseInt(id.slice(1), 10);
  if (id[0] === "A") return 330 + (n - 1) * 56;
  if (id[0] === "B") return 360 + (n - 1) * 62;
  return 170;
};
const remoteY = (id: string) => [0, 238, 292, 350, 404][parseInt(id.slice(1), 10)];

export const standPos = (id: string): Pt => {
  if (id[0] === "A") return [gateX(id), 190];
  if (id[0] === "B") return [gateX(id), 452];
  return [168, remoteY(id)];
};
export const standHeading = (id: string) => (id[0] === "A" ? 90 : id[0] === "B" ? -90 : 180);

/** Taxi route from a runway exit to a stand. Returns [main path..., laneEntry] and [laneEntry ... stand]. */
function routeToStand(rw: string, gate: string): { main: Pt[]; final: Pt[] } {
  const ty = TWY[rw];
  const start: Pt[] = [[EXIT_X, RWY[rw]], [EXIT_X - 20, ty]];
  const north = rw === "30L";
  if (gate[0] === "R") {
    const ry = remoteY(gate);
    const lane = north ? LANE_N : LANE_S;
    return { main: [...start, [REMOTE_X, ty], [REMOTE_X, lane]], final: [[REMOTE_X, lane], [REMOTE_X, ry], [168, ry]] };
  }
  const gx = gateX(gate);
  const gateNorth = gate[0] === "A";
  const lane = gateNorth ? LANE_N : LANE_S;
  const sy = gateNorth ? 190 : 452;
  if (north === gateNorth) {
    return { main: [...start, [gx, ty], [gx, lane]], final: [[gx, lane], [gx, sy]] };
  }
  // cross the field via the east crossing taxiway
  return { main: [...start, [CROSS_X, ty], [CROSS_X, lane], [gx + 0.01, lane]], final: [[gx, lane], [gx, sy]] };
}

function routeToRunway(gate: string, rw: string): Pt[] {
  const ty = TWY[rw];
  const north = rw === "30L";
  if (gate[0] === "R") {
    const ry = remoteY(gate);
    const lane = north ? LANE_N : LANE_S;
    return [[168, ry], [REMOTE_X, ry], [REMOTE_X, lane], [REMOTE_X, ty], [RWY_X1 - 6, ty], [RWY_X1, RWY[rw]]];
  }
  const gx = gateX(gate);
  const gateNorth = gate[0] === "A";
  const lane = gateNorth ? LANE_N : LANE_S;
  const sy = gateNorth ? 190 : 452;
  if (north === gateNorth) {
    return [[gx, sy], [gx, lane], [gx + 0.01, ty], [RWY_X1 - 6, ty], [RWY_X1, RWY[rw]]];
  }
  return [[gx, sy], [gx, lane], [CROSS_X - 0.01, lane], [CROSS_X, ty], [RWY_X1 + 4, ty], [RWY_X1, RWY[rw]]];
}

const lerp = (a: Pt, b: Pt, u: number): Pt => [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
const clamp = (u: number) => Math.max(0, Math.min(1, u));

function along(path: Pt[], u: number): Pt {
  u = clamp(u);
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    const d = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    seg.push(d); total += d;
  }
  if (total === 0) return path[0];
  let target = u * total;
  for (let i = 0; i < seg.length; i++) {
    if (target <= seg[i] || i === seg.length - 1) return lerp(path[i], path[i + 1], seg[i] ? target / seg[i] : 0);
    target -= seg[i];
  }
  return path[path.length - 1];
}

const ease = (u: number) => u * u * (3 - 2 * u);

export type Phase = "inbound" | "holding" | "final" | "landing" | "taxi-in" | "apron-hold" | "on-stand" |
  "taxi-out" | "takeoff" | "climb" | "diverting" | "hidden";

export interface AcState { pos: Pt; phase: Phase; visible: boolean }

/** Pure function: where is this flight at sim time t, according to its schedule row. */
export function aircraftAt(f: FlightRow, t: number, idx: number): AcState {
  const hidden: AcState = { pos: [-100, -100], phase: "hidden", visible: false };
  const edge: Pt = [W + 20, STACK.y + ((idx % 5) - 2) * 40];
  const orbit = (tt: number, phase0: number): Pt => {
    const a = (tt / 4) * Math.PI * 2 + phase0;
    return [STACK.x + STACK.rx * Math.cos(a), STACK.y + STACK.ry * Math.sin(a)];
  };
  const ph0 = idx * 1.37;
  if (f.diverted) {
    const enter = f.eta - 7, s0 = f.eta - 4, leave = f.eta - 4 + MAX_HOLD;
    if (t < enter || t > leave + 3) return hidden;
    if (t < s0) return { pos: lerp(edge, orbit(s0, ph0), ease((t - enter) / 3)), phase: "inbound", visible: true };
    if (t < leave) return { pos: orbit(t, ph0), phase: "holding", visible: true };
    return { pos: lerp(orbit(leave, ph0), [W + 40, -40], (t - leave) / 3), phase: "diverting", visible: true };
  }
  if (f.land == null || f.gate == null || f.gate_in == null || f.off_block == null || f.takeoff == null ||
      f.arr_runway == null || f.dep_runway == null || f.in_request == null) return hidden;
  const rw = f.arr_runway, ry = RWY[rw];
  const appStart: Pt = [RWY_X1 + 150, ry + (ry < 300 ? 60 : -60)];
  const holding = f.hold > 0.5;
  const finalStart = f.land - 4;
  const enter = (holding ? f.eta : finalStart) - 3;
  if (t < enter) return hidden;
  if (t < enter + 3) {
    const target = holding ? orbit(f.eta, ph0) : appStart;
    return { pos: lerp(edge, target, ease((t - enter) / 3)), phase: "inbound", visible: true };
  }
  if (holding && t < finalStart) return { pos: orbit(t, ph0), phase: "holding", visible: true };
  if (t < f.land) {
    const from = holding ? orbit(finalStart, ph0) : appStart;
    const u = (t - finalStart) / 4;
    const mid: Pt = [RWY_X1 + 70, ry];
    return { pos: u < 0.5 ? lerp(from, mid, u * 2) : lerp(mid, [RWY_X1, ry], (u - 0.5) * 2), phase: "final", visible: true };
  }
  const rollEnd = f.land + 1.2;
  if (t < rollEnd) {
    const u = (t - f.land) / 1.2;
    return { pos: [RWY_X1 - (RWY_X1 - EXIT_X) * (1 - (1 - u) * (1 - u)), ry], phase: "landing", visible: true };
  }
  const r = routeToStand(rw, f.gate);
  const taxiEnd = Math.max(rollEnd + 0.5, f.in_request - 0.8);
  if (t < taxiEnd) return { pos: along(r.main, (t - rollEnd) / (taxiEnd - rollEnd)), phase: "taxi-in", visible: true };
  const enterStand = f.gate_in - 0.8;
  if (t < enterStand) return { pos: r.main[r.main.length - 1], phase: "apron-hold", visible: true };
  if (t < f.gate_in) return { pos: along(r.final, (t - enterStand) / 0.8), phase: "taxi-in", visible: true };
  if (t < f.off_block) return { pos: standPos(f.gate), phase: "on-stand", visible: true };
  const roll0 = f.takeoff - 1;
  if (t < roll0) return { pos: along(routeToRunway(f.gate, f.dep_runway), (t - f.off_block) / Math.max(0.5, roll0 - f.off_block)), phase: "taxi-out", visible: true };
  const dry = RWY[f.dep_runway];
  if (t < f.takeoff) {
    const u = (t - roll0);
    return { pos: [RWY_X1 - (RWY_X1 - 470) * u * u, dry], phase: "takeoff", visible: true };
  }
  if (t < f.takeoff + 1.6) {
    const u = (t - f.takeoff) / 1.6;
    return { pos: lerp([470, dry], [20, dry + (dry < 300 ? -70 : 70)], u), phase: "climb", visible: true };
  }
  return hidden;
}

export function headingAt(f: FlightRow, t: number, idx: number, s: AcState): number {
  if (s.phase === "on-stand" && f.gate) return standHeading(f.gate);
  const a = aircraftAt(f, t + 0.06, idx).pos;
  const dx = a[0] - s.pos[0], dy = a[1] - s.pos[1];
  if (Math.hypot(dx, dy) < 0.05) {
    if (s.phase === "apron-hold") return -90;
    return 180;
  }
  return (Math.atan2(dy, dx) * 180) / Math.PI;
}

export interface TwinKpis { airborne: number; holding: number; onStand: number; taxiing: number; departed: number;
  delayedDeps: number; diverted: number; onTimeDeps: number }

export function kpisAt(rows: FlightRow[], t: number): TwinKpis {
  const k: TwinKpis = { airborne: 0, holding: 0, onStand: 0, taxiing: 0, departed: 0, delayedDeps: 0, diverted: 0, onTimeDeps: 0 };
  rows.forEach((f, i) => {
    const s = aircraftAt(f, t, i);
    if (["inbound", "final", "holding", "diverting"].includes(s.phase)) k.airborne++;
    if (s.phase === "holding") k.holding++;
    if (s.phase === "on-stand") k.onStand++;
    if (["taxi-in", "taxi-out", "apron-hold", "landing", "takeoff"].includes(s.phase)) k.taxiing++;
    if (f.diverted && t > f.eta - 4 + MAX_HOLD) k.diverted++;
    if (!f.diverted && f.off_block != null && t >= f.off_block) {
      k.departed++;
      if (f.dep_delay > 15) k.delayedDeps++; else k.onTimeDeps++;
    }
  });
  return k;
}
