// Every release made from this dataset, kept for download, and two releases compared side by side.
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/form";
import { Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { valuesKept, type Results } from "@/lib/api";
import { fmt, pct, plural, when } from "@/lib/format";
import { fetchRelease, useApp, viewRelease } from "@/lib/store";
import { cn } from "@/lib/utils";

export function History() {
  const history = useApp(s => s.history), current = useApp(s => s.results?.release_id);
  const [picked, setPicked] = useState<string[]>([]), [pair, setPair] = useState<[Results, Results] | null>(null), [loading, setLoading] = useState(false);
  if (!history.length) return <p className="text-sm text-muted-foreground">No releases yet.</p>;
  const pick = async (id: string, on: boolean) => {
    const next = on ? [...picked.filter(x => x !== id), id].slice(-2) : picked.filter(x => x !== id);
    setPicked(next);
    if (next.length === 2) {
      setLoading(true);
      const ordered = history.filter(h => next.includes(h.release_id)).reverse();  // older first
      try { setPair(await Promise.all(ordered.map(h => fetchRelease(h.release_id))) as [Results, Results]); }
      catch (e) { toast.error((e as Error).message); }
      finally { setLoading(false); }
    }
  };
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm text-muted-foreground">Every release made from this dataset is kept here. Tick two to compare them.</p>{loading && <Spinner />}</div>
      <div className="overflow-hidden rounded-xl border">{history.map(h => (
        <div key={h.release_id} className={cn("grid items-center gap-x-4 gap-y-1 border-b px-4 py-3 last:border-b-0 md:grid-cols-[minmax(0,1.5fr)_auto_minmax(0,1.2fr)_auto]", h.release_id === current && "bg-safe-soft")}>
          <div className="min-w-0"><b className="block truncate font-mono text-sm">{h.release_id}</b><span className="text-sm text-muted-foreground">{when(h.created_at)} · for {h.recipient} · approved by {h.approved_by ?? "–"}</span></div>
          <span className="text-sm text-muted-foreground">{h.plan_version ? `plan v${h.plan_version} · ` : ""}{h.k != null && `k ${h.k}`}{h.epsilon != null && ` ε ${h.epsilon}`} · {plural(h.files.length, "file")}</span>
          <span className="text-sm text-muted-foreground">{h.singled_out_after != null ? <>singled out {pct(h.singled_out_before)} → <b className="text-safe">{pct(h.singled_out_after)}</b>, guess {pct(h.guess_chance_after, 1)}</> : "statistics only"}</span>
          <div className="flex items-center justify-end gap-2">
            <label className="flex cursor-pointer items-center gap-1.5 text-[13px]"><Checkbox aria-label={`Compare ${h.release_id}`} checked={picked.includes(h.release_id)} onCheckedChange={v => pick(h.release_id, !!v)} /> compare</label>
            {h.release_id === current ? <Badge variant="ok">open</Badge> : <Button size="sm" variant="outline" onClick={() => viewRelease(h.release_id)}>Open</Button>}
          </div>
        </div>))}</div>
      {picked.length === 1 && <p className="text-sm text-muted-foreground">Tick one more release to compare.</p>}
      {pair && <CompareDialog pair={pair} onClose={() => { setPair(null); setPicked([]); }} />}
    </>
  );
}

function CompareDialog({ pair: [a, b], onClose }: { pair: [Results, Results]; onClose: () => void }) {
  const A = a.summary, B = b.summary;
  const metric = (label: string, va: number | null, vb: number | null, show: (v: number) => string, lowerIsBetter: boolean) => {
    const d = va != null && vb != null && va !== vb ? vb - va : null;
    return <tr key={label}><Td className="whitespace-nowrap text-muted-foreground">{label}</Td><Td className="tabular-nums">{va == null ? "–" : show(va)}</Td><Td className="tabular-nums">{vb == null ? "–" : show(vb)}</Td>
      <Td>{d != null && <span className={cn("font-mono text-xs font-semibold", (d < 0) === lowerIsBetter ? "text-ok" : "text-risk")}>{d > 0 ? "+" : ""}{show(d)}</span>}</Td></tr>;
  };
  const cols = [...new Set([...Object.keys(a.techniques), ...Object.keys(b.techniques)])], changed = cols.filter(c => a.techniques[c] !== b.techniques[c]);
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent wide>
        <DialogHeader><DialogTitle>Two releases side by side</DialogTitle></DialogHeader>
        <DialogBody>
          <div className="grid gap-5 md:grid-cols-2">
            <div className="flex flex-col gap-2"><h3 className="font-semibold">Headline numbers</h3><p className="text-xs text-muted-foreground">A = {A.release_id} · B = {B.release_id}</p>
              <TableWrap className="max-h-none"><table className="w-full border-collapse"><thead><tr><Th /><Th>A</Th><Th>B</Th><Th>B − A</Th></tr></thead><tbody>
                <tr><Td className="text-muted-foreground">Receiver</Td>{A.recipient === B.recipient ? <Td colSpan={3}>{A.recipient} <span className="text-muted-foreground">(both)</span></Td> : <><Td>{A.recipient}</Td><Td>{B.recipient}</Td><Td /></>}</tr>
                {metric("k", A.k, B.k, fmt, false)}{metric("ε", A.epsilon, B.epsilon, v => v.toFixed(2), true)}
                {metric("Singled out", A.singled_out_after, B.singled_out_after, v => pct(v, 1), true)}{metric("Guess chance", A.guess_chance_after, B.guess_chance_after, v => pct(v, 1), true)}
                {metric("Values kept", valuesKept(a), valuesKept(b), v => pct(v, 1), false)}{metric("Attack: people to choose from", A.attack_matches, B.attack_matches, fmt, false)}
              </tbody></table></TableWrap></div>
            <div className="flex flex-col gap-2"><h3 className="font-semibold">Columns treated differently <span className="text-sm font-normal text-muted-foreground">({changed.length} of {cols.length})</span></h3>
              {changed.length ? <TableWrap className="max-h-none"><table className="w-full border-collapse"><thead><tr><Th>Column</Th><Th>A</Th><Th>B</Th></tr></thead>
                <tbody>{changed.map(c => <tr key={c} className="bg-warn-soft/60"><Td className="font-mono">{c}</Td><Td><Badge>{a.techniques[c] ?? "withheld"}</Badge></Td><Td><Badge>{b.techniques[c] ?? "withheld"}</Badge></Td></tr>)}</tbody></table></TableWrap>
                : <p className="text-sm text-muted-foreground">Every column is treated the same way; only the protection level or budget differs.</p>}</div>
          </div>
        </DialogBody>
        <DialogFooter><Button onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
