// The local API (FastAPI on 127.0.0.1). Every number on screen comes from here.
export type Dict = Record<string, string>;

/** Columns that came without a real name (blank, a code like c07, or no header row) and the names given so far. */
export interface Naming {
  unnamed: { original: string; name: string | null; suggested_by: NameSource | null }[];
  headerless: boolean; headerless_guess: boolean;
}
export type NameSource = "rules" | "ai" | "person";
export interface NameSuggestion { column: string; name: string; meaning: string; source: NameSource | "none"; confidence: number; samples: string[] }
export interface NameSuggestions { suggestions: NameSuggestion[]; ai_calls: number; ai_error: string | null; model: string | null }
export interface TableOverview { name: string; rows: number; columns: string[]; preview: Dict[]; naming: Naming }
export interface SessionOverview {
  id: string; name: string; tables: TableOverview[]; released: boolean; ai: { on: boolean; model: string | null };
  steps: { scanned: boolean; planned: boolean; approved: boolean; released: boolean };
}
export interface ReleaseSummary {
  release_id: string; created_at: string; receiver: string; scenario_id: string; recipient: string; approved_by: string | null; plan_version?: number;
  k: number | null; epsilon: number | null; budget_cap: number | null; key_domain: string; files: string[];
  singled_out_before: number | null; singled_out_after: number | null; guess_chance_after: number | null;
  attack_outcome: string | null; attack_matches: number | null;
}
export interface SessionListItem {
  id: string; name: string; created_at: string; tables: string[]; bytes: number; receiver: string | null; released: boolean;
  steps: { scanned: boolean; planned: boolean; approved: boolean }; releases: number; last_release: ReleaseSummary | null;
}
export interface Receiver { id: string; title: string; recipient: string; purpose: string; trust_level: string; kind: "rows" | "statistics"; dataset: string; tables: string[] }
export interface Catalogue { samples: { name: string; tables: string[] }[]; receivers: Receiver[]; roles: string[]; subtypes: string[]; trust_levels: string[]; codelists: string[]; screens: string[] }

/** Release audit: every release made in this app, and the automatic planner measured on every receiver. */
export type AuditItem = ReleaseSummary & { session_id: string; dataset: string; published: boolean };
export interface ManifestPlan {
  scenario_id: string; approved_by: string | null; k_target: number; epsilon: number | null;
  actions: Action[]; aggregates: Aggregate[]; quasi_identifiers: Record<string, string[]>;
  column_names?: { table: string; original: string; name: string; suggested_by: string; model: string | null }[];
}
export interface AuditDetail {
  dataset: string; summary: ReleaseSummary; published: boolean; residual_risks: string[]; attack: Attack | null;
  manifest: { release_id: string; created_at: string; tool_version: string; key_domain: string; input_fingerprint: string;
    plan: ManifestPlan; files: { name: string; sha256: string; rows: number }[]; limitations: string[]; llm: { model: string; used_for: string[] } | null };
  scorecard: { run_id: string; scores: { privacy: number | null; utility: number | null; composite: number | null }; gates: { name: string; value: string; target: string; status: "PASS" | "FAIL" | "N/A" }[] } | null;
}
export interface ReceiverResult {
  id: string; dataset: string; recipient: string; trust_level: string; gets: "rows" | "statistics"; source: string;
  privacy: number | null; utility: number | null; composite: number | null; released_tables: number; epsilon: number | null;
  status: "ready" | "needs tuning" | "unscored" | "failed"; why: string; measured_at: string; commit: string;
  baselines: Baselines | null;
}
/** The organisers' reference baselines: privacy per dataset, usefulness per receiver (results/baselines.csv). */
export type BaselineScore = { privacy: number; utility: number };
export interface Baselines { generated: string; b0: BaselineScore; b2: BaselineScore; b2k: BaselineScore }
export interface ReceiversBenchmark { rows: ReceiverResult[]; measured_at: string | null; baselines_generated: string | null }
export interface Column { table: string; column: string; privacy_role: string; subtype: string; confidence: number; evidence: { kind: string; detail: string }[] }
export interface TableExposure {
  table: string; rows: number; direct_identifiers: string[]; outside_links: string[]; quasi_identifiers: string[];
  sensitive: string[]; free_text: string[]; unique_share: number; special_category: boolean;
}
export interface Link { from_table: string; from_column: string; to_table: string; to_column: string; overlap: number; meaning: string }
export interface AttackResult {
  table: string; rows: number; known: Dict; matches: number; usable: string[]; revealed: Dict; hidden: Dict; linked: Record<string, number>; outcome: string;
}
export interface Hop { table: string; rows: number; via: string; from_table: string; learnt: Dict }
export interface Attack { before: AttackResult; trail?: Hop[]; after: AttackResult | null }
export interface Scan { detections: { columns: Column[] }; risk: { links: Link[]; tables: TableExposure[]; person: Record<string, Dict[]> }; attack: Attack | null }
export interface Action { table: string; column: string; technique: string; params: Record<string, unknown>; reason: string }
export interface Aggregate { name: string; table: string; dimensions: { column: string; name?: string }[]; epsilon: number; reason: string }
export interface Plan {
  scenario_id: string; actions: Action[]; aggregates: Aggregate[]; quasi_identifiers: Record<string, string[]>; k_target: number;
  epsilon: number | null; approved: boolean; approved_by: string | null; differential_privacy: { unit: string; max_rows_per_unit: number } | null;
}
export interface PlanView { plan: Plan; scenario: (Receiver & { purpose: string }) | null; reviews: string[]; withheld_tables: string[] }
export interface PlanVersion { version: number; created_at: string; note: string; approved: boolean; approved_by: string | null; recipient: string; released_as: string | null }
export interface PlanVersions { current: number; versions: PlanVersion[] }
export interface PlanCompare { changes: { what: string; before: string; after: string }[]; yaml_a: string; yaml_b: string }
export interface Tradeoff { k: { k: number; guess_chance: number; cells_kept: number; current: boolean }[]; epsilon: { epsilon: number; mean_error: number | null; current: boolean }[] }
export interface Example { tables: { table: string; renamed: Dict; rows: { raw: Dict; after: Dict }[] }[] }
export interface Compare { receivers: Receiver[]; rows: ({ table: string; column: string; role: string } & Dict)[]; left_out: { id: string; recipient: string; reason: string }[] }
export interface ColumnChange { column: string; released_as: string | null; technique: string; filled_before: number; filled_after: number; distinct_before: number; distinct_after: number; top_after: [string, number][] }
export interface Lookalikes { rows: number; unique_share: number; guess_chance: number; buckets: Record<string, number> }
export interface Results {
  release_id: string; files: { name: string }[];
  tables: { name: string; rows_in: number; rows_out: number; preview: Dict[]; raw_preview: Dict[]; pairs: { raw: Dict; released: Dict }[];
    changes: ColumnChange[]; suppression: { rows_removed: number; cells_blanked: Record<string, number> } | null }[];
  attacker: { table: string; known: string[]; before: Lookalikes; after: Lookalikes }[];
  attack: Attack | null; summary: ReleaseSummary; techniques: Dict;
  statistics: { name: string; preview: Dict[]; cells: number }[]; accuracy: { name: string; within_10pct: number | null }[];
  text: { column: string; samples: { t: string; label?: string }[][] }[];
  residual_risks: string[]; epsilon: number | null; published: boolean;
}

type Opts = { method?: string; body?: unknown };

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const init: RequestInit = { method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"), headers: {} };
  if (opts.body instanceof FormData) init.body = opts.body;
  else if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers = { "Content-Type": "application/json" }; }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || `request failed (${res.status})`);
  return data as T;
}

/** Upload with progress (fetch cannot report it; XMLHttpRequest can). */
export function upload<T>(url: string, form: FormData, onProgress: (sent: number, total: number) => void, onSent: () => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
    x.upload.onprogress = e => e.lengthComputable && onProgress(e.loaded, e.total);
    x.upload.onload = onSent;
    x.onload = () => {
      let d: { error?: string } = {};
      try { d = JSON.parse(x.responseText); } catch { /* not JSON */ }
      x.status < 300 ? resolve(d as T) : reject(new Error(d.error || `upload failed (${x.status})`));
    };
    x.onerror = () => reject(new Error("the upload was interrupted"));
    x.send(form);
  });
}

/** Download a file the API serves, keeping the name it suggests. */
export async function download(href: string) {
  const res = await fetch(href);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "download refused");
  const blob = await res.blob(), url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url;
  a.download = (res.headers.get("Content-Disposition") || "").split('filename="')[1]?.replace('"', "") || "release.zip";
  a.click();
  URL.revokeObjectURL(url);
}
