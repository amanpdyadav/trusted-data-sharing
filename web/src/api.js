// All data comes from the FastAPI backend. Relative URLs work both through the Vite proxy and when FastAPI serves dist/.
export async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} for ${path}${body ? `: ${body.slice(0, 200)}` : ""}`);
  }
  return res.json();
}

export const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : n);
export const pct = (x, digits = 0) => (x == null ? "–" : `${(x * 100).toFixed(digits)}%`);

export const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
