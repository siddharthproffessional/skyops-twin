export const hhmm = (t: number | null | undefined): string => {
  if (t === null || t === undefined || Number.isNaN(t)) return "--:--";
  const m = Math.round(t) + 14 * 60;
  return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(((m % 60) + 60) % 60).padStart(2, "0")}`;
};
export const fmt = (n: number | undefined, d = 0) =>
  n === undefined || n === null ? "–" : n.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
