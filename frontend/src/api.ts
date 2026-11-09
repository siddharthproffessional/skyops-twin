const BASE: string = (import.meta as any).env?.VITE_API_BASE ?? "";
const j = async (r: Response) => {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
};
const remote = {
  state: () => fetch(BASE + "/api/state").then(j),
  airport: () => fetch(BASE + "/api/airport").then(j),
  scenario: (id: string) => fetch(`${BASE}/api/scenarios/${id}/inject`, { method: "POST" }).then(j),
  disruption: (type: string, params: Record<string, unknown>) =>
    fetch(BASE + "/api/disruptions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ type, params }) }).then(j),
  freetext: (text: string) =>
    fetch(BASE + "/api/events/freetext", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }) }).then(j),
  metar: (raw: string) =>
    fetch(BASE + "/api/adapters/metar", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ raw }) }).then(j),
  schedule: (id: string) => fetch(`${BASE}/api/schedules/${id}`).then(j),
  approve: (id: string, note = "") =>
    fetch(`${BASE}/api/plans/${id}/approve`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ note }) }).then(j),
  reject: (id: string, note = "") =>
    fetch(`${BASE}/api/plans/${id}/reject`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ note }) }).then(j),
  reset: () => fetch(BASE + "/api/reset", { method: "POST" }).then(j),
};
export const wsUrl = () => {
  if (BASE) return BASE.replace(/^http/, "ws") + "/ws/operations";
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/operations`;
};

import { serverless } from "./lib/serverless";
export const SERVERLESS = (import.meta as any).env?.VITE_SERVERLESS === "1";
export const api: typeof remote = SERVERLESS ? (serverless as unknown as typeof remote) : remote;

/** Live event stream: WebSocket on a normal server, in-browser replay in serverless mode. */
export function connectStream(onEvent: (ev: any) => void, onStatus: (up: boolean) => void): () => void {
  if (SERVERLESS) { onStatus(true); return serverless.subscribe(onEvent); }
  let ws: WebSocket | null = null; let alive = true; let retry: number | undefined;
  const open = () => {
    ws = new WebSocket(wsUrl());
    ws.onopen = () => onStatus(true);
    ws.onclose = () => { onStatus(false); if (alive) retry = window.setTimeout(open, 1500); };
    ws.onmessage = (m) => onEvent(JSON.parse(m.data));
  };
  open();
  return () => { alive = false; window.clearTimeout(retry); ws?.close(); };
}
