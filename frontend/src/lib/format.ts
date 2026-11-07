// Formatting and on-screen masking. Masking only changes what is shown, never the data.
export const fmt = (n: number) => Number(n).toLocaleString("en-US");
export const pct = (x: number | null | undefined, digits = 0) => (x == null ? "–" : `${(100 * x).toFixed(digits)}%`);
export const plural = (n: number, word: string, many = `${word}s`) => `${fmt(n)} ${n === 1 ? word : many}`;
export const when = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
export const clip = (v: unknown, n = 120) => { const t = String(v ?? ""); return t.length > n ? `${t.slice(0, n - 1)}…` : t; };
export const mb = (bytes: number) => (bytes / 2 ** 20).toFixed(bytes < 10 * 2 ** 20 ? 1 : 0);


/** Plain words for each privacy role. */
export const ROLE_LABEL: Record<string, string> = {
  direct_identifier: "identifies a person", quasi_identifier: "outsider may know it", sensitive_attribute: "sensitive fact",
  technical_identifier: "link / code", record_key: "row key", free_text: "free text", non_sensitive: "harmless",
};
export const ROLE_TONE: Record<string, string> = {
  direct_identifier: "text-risk font-semibold", quasi_identifier: "text-warn", sensitive_attribute: "text-safe",
};
