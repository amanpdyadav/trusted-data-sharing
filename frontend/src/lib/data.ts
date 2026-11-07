// Page data loaded straight from the local API (Release audit, Mosaic attack), and the Mosaic attack data types.
// The Mosaic data is written by `make screens` (outside the tool: it uses the challenge's answer files).
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
export interface MosaicTotals { scraps: number; one_person_names_removed: number; exposed_on_release: number }
export interface Mosaic { created_utc: string; release: string; cases: MosaicCase[]; summary?: { post: MosaicTotals; news: MosaicTotals } }

/** Load data from the local API when `path` changes; a stale answer for an earlier path is ignored. */
export function useApi<T>(path: string) {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    let live = true;
    setState({ data: null, error: null });
    api<T>(path).then(data => live && setState({ data, error: null }))
      .catch((e: Error) => live && setState({ data: null, error: e.message }));
    return () => { live = false; };
  }, [path]);
  return state;
}
