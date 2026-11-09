import React, { useMemo } from "react";
import type { Disruption, FlightRow, Gate } from "../types";
import { aircraftAt, headingAt, standPos, RWY, TWY, RWY_X0, RWY_X1, LANE_N, LANE_S, CROSS_X, REMOTE_X, STACK, W, H } from "../lib/twin";
import { hhmm } from "../lib/time";

const SCALE: Record<string, number> = { F: 1.35, E: 1.12, C: 0.86 };

function Plane({ x, y, rot, size, color, label, ring, dim }: {
  x: number; y: number; rot: number; size: string; color: string; label: string; ring?: string; dim?: boolean;
}) {
  const s = SCALE[size] ?? 1;
  return (
    <g transform={`translate(${x},${y})`} opacity={dim ? 0.75 : 1}>
      {ring && <circle r={13 * s} fill="none" stroke={ring} strokeWidth={1.2} opacity={0.7} />}
      <g transform={`rotate(${rot}) scale(${s})`}>
        <path d="M11 0 L4 -1.6 L-1 -9 L-3.4 -9 L-0.6 -1.6 L-6.5 -1.4 L-8.6 -4.4 L-10 -4.4 L-8.6 0 L-10 4.4 L-8.6 4.4 L-6.5 1.4 L-0.6 1.6 L-3.4 9 L-1 9 L4 1.6 Z"
          fill={color} stroke="#020617" strokeWidth={0.6} />
      </g>
      <text x={10 * s} y={-8 * s} fontSize={8.5} fill={color} className="mono" opacity={0.95}>{label}</text>
    </g>
  );
}

export default function AirportTwin({ rows, t, gates, disruption, title, compact, highlight }: {
  rows: FlightRow[]; t: number; gates: Gate[]; disruption: Disruption; title?: string; compact?: boolean; highlight?: string;
}) {
  const stormOn = disruption.kind !== "none" && disruption.end > disruption.start && t >= disruption.start && t < disruption.end;
  const dusty = stormOn && (disruption.kind === "sandstorm" || (disruption.visibility_m ?? 9999) < 1500);
  const closedRw = disruption.runway_closures.filter(c => t >= c.start && t < c.end).map(c => c.runway);
  const capRw = disruption.capacity_overrides.filter(c => t >= c.start && t < c.end);
  const closedGates = new Set(disruption.gate_closures.filter(c => t >= c.start && t < c.end).map(c => c.gate));
  const occupied = useMemo(() => {
    const m = new Map<string, FlightRow>();
    rows.forEach(f => { if (f.gate && f.gate_in != null && f.off_block != null && t >= f.gate_in && t < f.off_block) m.set(f.gate, f); });
    return m;
  }, [rows, t]);

  const planes = rows.map((f, i) => {
    const s = aircraftAt(f, t, i);
    if (!s.visible) return null;
    const rot = headingAt(f, t, i, s);
    let color = "#7dd3fc";
    let ring: string | undefined;
    if (s.phase === "holding") { color = "#fb923c"; ring = "#fb923c"; }
    if (s.phase === "apron-hold") { color = "#fbbf24"; ring = "#fbbf24"; }
    if (s.phase === "on-stand") color = f.dep_delay > 15 ? "#fbbf24" : "#a5b4fc";
    if (["taxi-out", "takeoff", "climb"].includes(s.phase) && f.dep_delay > 15) color = "#fbbf24";
    if (f.diverted) { color = "#f87171"; ring = "#ef4444"; }
    if (highlight === f.id) ring = "#ffffff";
    return <Plane key={f.id} x={s.pos[0]} y={s.pos[1]} rot={rot} size={f.size} color={color} ring={ring}
      label={s.phase === "diverting" ? `${f.id} DIVERT` : f.id} dim={s.phase === "on-stand"} />;
  });
  const holding = rows.filter((f, i) => aircraftAt(f, t, i).phase === "holding").length;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0H0V40" fill="none" stroke="rgba(120,160,230,0.06)" strokeWidth="1" />
        </pattern>
        <pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="5" height="10" fill="rgba(239,68,68,0.55)" />
        </pattern>
        <filter id="dust" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.006 0.018" numOctaves="3" seed="4">
            <animate attributeName="seed" values="1;2;3;4;5;6" dur="3s" repeatCount="indefinite" />
          </feTurbulence>
          <feColorMatrix values="0 0 0 0 0.78  0 0 0 0 0.52  0 0 0 0 0.24  0 0 0 0.9 -0.18" />
        </filter>
        <radialGradient id="glow" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor="rgba(56,189,248,0.10)" />
          <stop offset="100%" stopColor="rgba(56,189,248,0)" />
        </radialGradient>
      </defs>
      <rect width={W} height={H} fill="#060f22" />
      <rect width={W} height={H} fill="url(#grid)" />
      <rect width={W} height={H} fill="url(#glow)" />

      {/* runways */}
      {(["30L", "30R"] as const).map(rw => {
        const y = RWY[rw];
        const closed = closedRw.includes(rw);
        const cap = capRw.find(c => c.runway === rw);
        return (
          <g key={rw}>
            <rect x={RWY_X0} y={y - 12} width={RWY_X1 - RWY_X0} height={24} rx={2} fill="#1b2335" stroke="#2b3a57" />
            <line x1={RWY_X0 + 20} x2={RWY_X1 - 20} y1={y} y2={y} stroke="#e2e8f0" strokeWidth={1.4} strokeDasharray="18 14" opacity={0.55} />
            {[0, 1, 2, 3, 4, 5].map(i => <rect key={i} x={RWY_X1 - 30} y={y - 9 + i * 3.2} width={18} height={1.6} fill="#e2e8f0" opacity={0.7} />)}
            <text x={RWY_X1 - 52} y={y + 4} fontSize={10} fill="#cbd5e1" className="mono" opacity={0.8}>{rw === "30L" ? "30L" : "30R"}</text>
            <text x={RWY_X0 + 8} y={y + 4} fontSize={10} fill="#cbd5e1" className="mono" opacity={0.8}>{rw === "30L" ? "12R" : "12L"}</text>
            {closed && <>
              <rect x={RWY_X0} y={y - 12} width={RWY_X1 - RWY_X0} height={24} fill="url(#hatch)" />
              <rect x={(RWY_X0 + RWY_X1) / 2 - 92} y={y - 11} width={184} height={22} rx={3} fill="#7f1d1d" stroke="#ef4444" />
              <text x={(RWY_X0 + RWY_X1) / 2} y={y + 4.5} fontSize={12} textAnchor="middle" fill="#fecaca" fontWeight={700} letterSpacing={2}>RUNWAY {rw} CLOSED</text>
            </>}
            {cap && !closed && <>
              <rect x={(RWY_X0 + RWY_X1) / 2 - 110} y={y + (rw === "30L" ? 14 : -36)} width={220} height={20} rx={3} fill="rgba(120,53,15,0.85)" stroke="#f59e0b" />
              <text x={(RWY_X0 + RWY_X1) / 2} y={y + (rw === "30L" ? 28 : -22)} fontSize={11} textAnchor="middle" fill="#fde68a" fontWeight={600} letterSpacing={1}>LVP · {cap.capacity_per_hour} MOVEMENTS/H</text>
            </>}
          </g>
        );
      })}

      {/* taxiways */}
      <g stroke="#1e3a5f" strokeWidth={7} fill="none" strokeLinecap="round" opacity={0.9}>
        <line x1={REMOTE_X} x2={RWY_X1} y1={TWY["30L"]} y2={TWY["30L"]} />
        <line x1={REMOTE_X} x2={RWY_X1} y1={TWY["30R"]} y2={TWY["30R"]} />
        <line x1={REMOTE_X} x2={CROSS_X} y1={LANE_N} y2={LANE_N} />
        <line x1={REMOTE_X} x2={CROSS_X} y1={LANE_S} y2={LANE_S} />
        <line x1={CROSS_X} x2={CROSS_X} y1={TWY["30L"]} y2={TWY["30R"]} />
        <line x1={REMOTE_X} x2={REMOTE_X} y1={TWY["30L"]} y2={TWY["30R"]} />
        <line x1={600} x2={580} y1={RWY["30L"]} y2={TWY["30L"]} />
        <line x1={600} x2={580} y1={RWY["30R"]} y2={TWY["30R"]} />
        <line x1={RWY_X1} x2={RWY_X1 - 6} y1={RWY["30L"]} y2={TWY["30L"]} />
        <line x1={RWY_X1} x2={RWY_X1 - 6} y1={RWY["30R"]} y2={TWY["30R"]} />
      </g>
      <g stroke="#facc15" strokeWidth={0.8} fill="none" opacity={0.35}>
        <line x1={REMOTE_X} x2={RWY_X1} y1={TWY["30L"]} y2={TWY["30L"]} />
        <line x1={REMOTE_X} x2={RWY_X1} y1={TWY["30R"]} y2={TWY["30R"]} />
        <line x1={REMOTE_X} x2={CROSS_X} y1={LANE_N} y2={LANE_N} />
        <line x1={REMOTE_X} x2={CROSS_X} y1={LANE_S} y2={LANE_S} />
        <line x1={CROSS_X} x2={CROSS_X} y1={TWY["30L"]} y2={TWY["30R"]} />
      </g>

      {/* terminal and piers */}
      <rect x={300} y={222} width={676} height={18} rx={4} fill="#13284a" stroke="#2c4a7c" />
      <rect x={330} y={400} width={622} height={18} rx={4} fill="#13284a" stroke="#2c4a7c" />
      <rect x={470} y={258} width={350} height={124} rx={10} fill="#0f2242" stroke="#2c4a7c" />
      <text x={645} y={312} textAnchor="middle" fontSize={15} fill="#7aa2e3" letterSpacing={5} fontWeight={700}>TERMINAL 1</text>
      <text x={645} y={332} textAnchor="middle" fontSize={10} fill="#5873a3" letterSpacing={2}>SKYOPS INTERNATIONAL · SYNTHETIC</text>
      <text x={638} y={234.5} textAnchor="middle" fontSize={8.5} fill="#6f8fc4" letterSpacing={3}>CONCOURSE A · WIDE-BODY</text>
      <text x={641} y={412.5} textAnchor="middle" fontSize={8.5} fill="#6f8fc4" letterSpacing={3}>CONCOURSE B · NARROW-BODY</text>
      <text x={120} y={220} fontSize={9} fill="#5873a3" letterSpacing={2}>REMOTE</text>

      {/* stands */}
      {gates.map(g => {
        const [x, y] = standPos(g.id);
        const occ = occupied.get(g.id);
        const closed = closedGates.has(g.id);
        const w = g.size === "F" ? 40 : g.size === "E" ? 34 : 28;
        const horizontal = g.id[0] !== "R";
        const fill = closed ? "rgba(127,29,29,0.6)" : occ ? "rgba(56,189,248,0.16)" : "rgba(30,58,95,0.35)";
        const stroke = closed ? "#ef4444" : occ ? (occ.dep_delay > 15 ? "#f59e0b" : "#38bdf8") : "#28456f";
        return (
          <g key={g.id}>
            {horizontal
              ? <rect x={x - w / 2} y={y - 18} width={w} height={36} rx={3} fill={fill} stroke={stroke} strokeDasharray={g.kind === "remote" ? "3 2" : undefined} />
              : <rect x={x - 18} y={y - w / 2} width={36} height={w} rx={3} fill={fill} stroke={stroke} strokeDasharray="3 2" />}
            {closed && <path d={`M${x - 10} ${y - 10} L${x + 10} ${y + 10} M${x + 10} ${y - 10} L${x - 10} ${y + 10}`} stroke="#f87171" strokeWidth={2} />}
            <text x={horizontal ? x : x - 26} y={horizontal ? (g.id[0] === "A" ? y - 22 : y + 30) : y + 3} fontSize={8.5}
              textAnchor="middle" fill={closed ? "#fca5a5" : "#6b8bc2"} className="mono">{g.id}</text>
          </g>
        );
      })}

      {/* holding stack */}
      <ellipse cx={STACK.x} cy={STACK.y} rx={STACK.rx} ry={STACK.ry} fill="none" stroke={holding ? "#fb923c" : "#334d78"}
        strokeDasharray="4 5" strokeWidth={1.2} opacity={holding ? 0.9 : 0.5} />
      <text x={STACK.x} y={STACK.y - STACK.ry - 10} textAnchor="middle" fontSize={9} fill={holding ? "#fdba74" : "#5873a3"} letterSpacing={2}>
        HOLDING STACK
      </text>
      {holding > 0 && <text x={STACK.x} y={STACK.y + 5} textAnchor="middle" fontSize={20} fill="#fb923c" fontWeight={800}>{holding}</text>}
      {/* approach guide */}
      <line x1={RWY_X1} x2={W} y1={RWY["30L"]} y2={RWY["30L"]} stroke="#1e3a5f" strokeDasharray="2 6" />
      <line x1={RWY_X1} x2={W} y1={RWY["30R"]} y2={RWY["30R"]} stroke="#1e3a5f" strokeDasharray="2 6" />

      {planes}

      {dusty && <>
        <rect width={W} height={H} filter="url(#dust)" opacity={0.3} style={{ mixBlendMode: "screen" }} />
        <rect width={W} height={H} fill="rgba(200,120,40,0.07)" />
      </>}

      {/* overlay labels */}
      {title && <text x={16} y={H - 14} fontSize={compact ? 22 : 13} fill="#9fb5dc" fontWeight={700} letterSpacing={2}>{title}</text>}
      <text x={W - 16} y={H - 14} fontSize={compact ? 22 : 13} fill="#9fb5dc" textAnchor="end" className="mono">{hhmm(t)} LT</text>
      {stormOn && (
        <g>
          <rect x={W / 2 - 160} y={H / 2 - 42} width={320} height={0} />
        </g>
      )}
    </svg>
  );
}
