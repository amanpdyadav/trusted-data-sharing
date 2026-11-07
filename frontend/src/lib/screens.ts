// Data for the two presentation screens (Mosaic attack, Release audit). Written by `python -m evaluation screens`
// and served at /api/screens/{mosaic,audit}; built outside the tool because it uses the challenge's answer files.
import { useEffect, useState } from "react";
import { api } from "./api";

export type FunnelRow = [label: string, candidates: number, applied?: boolean];

export interface ChainStep {
  id: string; dataset: string; file: string; kind: "public" | "leaked" | "release"; title: string; rows_total: number;
  funnel: FunnelRow[]; revealed: Record<string, string>; how: string; link: string; verified: boolean | null;
  quote?: { who: string; when: string; text: string }; clues?: string[];
}
export interface Replay { funnel: FunnelRow[]; candidates: number; target_in: boolean | null; holds: boolean }
export interface MosaicCase { id: string; kind: "post" | "news"; label: string; text: string; raw: ChainStep[]; names: ChainStep[]; ours: Replay }
export interface Mosaic { created_utc: string; release: string; cases: MosaicCase[] }

export interface Gate { name: string; value: string; target: string; status: "PASS" | "FAIL" | "N/A" }
export interface Audit {
  created_utc: string; run_id: string; dataset: string; scenario: string;
  scores: { privacy: number | null; utility: number | null; composite: number | null; share_below_k: number | null; k_min: number | null };
  gates: Gate[];
  sweep: { scraps: number; single: number; single_target: number; exposed: number; median_candidates: number; worst: (Replay & { id: string })[] } | null;
  decisions: { table: string; column: string; technique: string; params: Record<string, unknown> | null; reason: string }[];
  approved_by: string | null;
  manifest: { release_id?: string; files?: { name?: string; path?: string; sha256?: string }[]; residual_risks?: unknown[] } | null;
}

/** Load one screen's data once; `error` explains how to build it when it is missing. */
export function useScreen<T>(name: "mosaic" | "audit") {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    let live = true;
    api<T>(`/api/screens/${name}`).then(data => live && setState({ data, error: null }))
      .catch((e: Error) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [name]);
  return state;
}
