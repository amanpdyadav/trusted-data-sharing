// Release audit: who the release is for, what was done and why, every check and the risk left (ported from the main
// branch). Data from `python -m evaluation screens`.
import { useState } from "react";
import { Kpi, Kpis, PageHead } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Meter, TableWrap, Td, Th } from "@/components/ui/misc";
import { fmt, pct, plural, when } from "@/lib/format";
import { useScreen, type Audit, type FunnelRow } from "@/lib/screens";
import { cn } from "@/lib/utils";
import { NotBuilt } from "@/steps/MosaicAttack";

const STATUS_TONE = { PASS: "ok", FAIL: "risk", "N/A": "outline" } as const;

export function ReleaseAudit() {
  const { data, error } = useScreen<Audit>("audit");
  if (!data) return <><PageHead title="Release audit" lede="Who the release is for, what was done, what was measured, what risk is left." /><NotBuilt error={error} what="audit data" /></>;
  const d = data, sc = d.scores, sw = d.sweep;
  const failed = d.gates.filter(g => g.status === "FAIL");
  const gates = [...d.gates].sort((a, b) => Number(b.status === "FAIL") - Number(a.status === "FAIL"));
  return (
    <>
      <PageHead title={<>Release audit · {d.scenario}</>}
        lede={<>Run <code>{d.run_id}</code>, built {when(d.created_utc)} · {d.approved_by ? <>plan approved by <b>{d.approved_by}</b></> : <b>plan not yet approved</b>}</>} />
      <Card className={cn("p-4", failed.length ? "border-risk/50 bg-risk-soft" : "border-ok/50 bg-ok-soft")}>
        {failed.length ? <><b>{plural(failed.length, "check")} failing:</b> {failed.map(g => g.name).join(", ")}</> : <b>All {d.gates.length} checks pass.</b>}
      </Card>
      <Kpis>
        <Kpi tone="safe" value={sc.composite?.toFixed(3) ?? "–"} label="combined score (pets-eval)" />
        <Kpi tone="none" value={sc.utility?.toFixed(3) ?? "–"} label="usefulness kept" />
        <Kpi tone={sc.share_below_k ? "risk" : "safe"} value={pct(sc.share_below_k, 1)} label="rows in groups under k" />
        {sw && <Kpi tone={sw.exposed ? "risk" : "safe"} value={fmt(sw.exposed)} label={`of ${fmt(sw.scraps)} public posts and news clips expose someone`} />}
      </Kpis>
      <Card className="flex flex-col gap-3 p-5">
        <h2 className="text-2xl">Checks</h2>
        <TableWrap><table className="w-full"><thead><tr><Th /><Th>Check</Th><Th>Measured</Th><Th>Target</Th></tr></thead>
          <tbody>{gates.map(g => <tr key={g.name}><Td><Badge variant={STATUS_TONE[g.status]}>{g.status}</Badge></Td><Td>{g.name}</Td><Td className="text-sm text-muted-foreground">{g.value}</Td><Td className="text-sm text-muted-foreground">{g.target}</Td></tr>)}</tbody>
        </table></TableWrap>
      </Card>
      {sw && (
        <Card className="flex flex-col gap-3 p-5">
          <h2 className="text-2xl">Every public post and news clip, replayed</h2>
          <p className="text-sm text-muted-foreground">{fmt(sw.scraps)} scraps · one visit left {sw.single} (real person {sw.single_target}) · median group {fmt(Math.round(sw.median_candidates))}.</p>
          {sw.worst.length ? sw.worst.map(w => <Closest key={w.id} id={w.id} left={w.candidates} funnel={w.funnel} />) : <p className="text-sm">No scrap leaves the real person in a group smaller than 5.</p>}
        </Card>
      )}
      <Card className="flex flex-col gap-3 p-5">
        <h2 className="text-2xl">Decisions per column</h2>
        <TableWrap><table className="w-full"><thead><tr><Th>Column</Th><Th>Protection</Th><Th>Why</Th></tr></thead>
          <tbody>{d.decisions.map(a => (
            <tr key={`${a.table}.${a.column}`}><Td className="whitespace-nowrap font-mono text-xs">{a.table}.{a.column}</Td>
              <Td>{a.technique}{a.params && <span className="block font-mono text-[11px] text-muted-foreground">{JSON.stringify(a.params)}</span>}</Td>
              <Td className="text-sm text-muted-foreground">{a.reason}</Td></tr>))}</tbody>
        </table></TableWrap>
      </Card>
      {d.manifest?.files && (
        <Card className="flex flex-col gap-3 p-5">
          <h2 className="text-2xl">Released files</h2>
          <TableWrap><table className="w-full"><thead><tr><Th>File</Th><Th>SHA-256</Th></tr></thead>
            <tbody>{d.manifest.files.map(f => <tr key={f.name ?? f.path}><Td>{f.name ?? f.path}</Td><Td><code className="text-xs" title={f.sha256}>{(f.sha256 ?? "").slice(0, 16)}…</code></Td></tr>)}</tbody>
          </table></TableWrap>
        </Card>
      )}
    </>
  );
}

function Closest({ id, left, funnel }: { id: string; left: number; funnel: FunnelRow[] }) {
  const [open, setOpen] = useState(false);
  const top = Math.log10((funnel[0]?.[1] ?? 1) + 1);
  return (
    <div className="rounded-xl border p-3">
      <button className="flex w-full justify-between text-left" onClick={() => setOpen(!open)}><b>{id}</b><span className="text-sm text-muted-foreground">{fmt(left)} left</span></button>
      {open && <div className="mt-2 flex flex-col gap-2">{funnel.map(([label, n], i) => (
        <div key={`${label}-${i}`} className="flex flex-col gap-1"><div className="flex justify-between text-sm"><span className="text-muted-foreground">{label}</span><b>{fmt(n)}</b></div>
          <Meter value={Math.max(0.015, Math.log10(n + 1) / top)} /></div>))}</div>}
    </div>
  );
}
