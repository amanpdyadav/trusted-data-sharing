// Step 2: what could go wrong if the data were shared as it is. Headline numbers, the connection map, the attack
// replay on one person and the trail through the tables, then the tabs in ScanDetails.
import { ArrowDown, ArrowRight, Dices, Play } from "lucide-react";
import type { ReactNode } from "react";
import { Facts, Guide, Kpi, Kpis, PageHead, ProgressCard, Section, useRole, Verdict } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/misc";
import { worstTable, type Attack, type Hop, type Scan } from "@/lib/api";
import { ROLE_TONE, fmt, pct, plural, text } from "@/lib/format";
import { anotherPerson, go, play, runScan, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Details } from "@/steps/ScanDetails";

export function RiskScan() {
  const scan = useApp(s => s.scan), progress = useApp(s => s.progress);
  const title = "What could go wrong if this data were shared as it is";
  if (!scan) return <><PageHead title={title} />{progress ? <ProgressCard /> : <div><Button size="lg" onClick={runScan}>Scan for risks</Button></div>}</>;
  const R = scan.risk, worst = worstTable(R);
  const outside = R.tables.flatMap(t => t.outside_links), joined = new Set(R.links.flatMap(l => [l.from_table, l.to_table])).size;
  const special = R.tables.filter(t => t.special_category).map(t => t.table);
  return (
    <>
      <PageHead title={title} lede="Found from the data itself: which columns identify people, what outsiders could match, and how the tables connect." />
      <Guide steps={["See how one person is found", "Follow the trail to see what leaks", "Fix any column labelled wrong, then choose a receiver"]} done={[true, true, false]} />
      <Kpis>
        <Kpi tone={worst.unique_share >= 0.5 ? "risk" : "warn"} value={pct(worst.unique_share)} label={<>of rows in <b>{worst.table}</b> can be singled out on facts an outsider may know</>} />
        <Kpi tone={outside.length ? "risk" : "ok"} value={fmt(outside.length)} label="columns match public registers, social media or leaked lists" />
        <Kpi tone={joined ? "warn" : "ok"} value={fmt(joined)} label={joined ? "tables joined by shared keys: one match unlocks the rest" : "tables joined: each table stands alone"} />
        <Kpi tone={special.length ? "warn" : "ok"} value={special.length ? "Art. 9" : "none"} label={special.length ? `special category data (GDPR) in ${special.join(", ")}` : "special category data (GDPR)"} />
      </Kpis>
      <Section title="How your data connects" right={<Legend items={[["bg-input", "joined by a shared key"], ["bg-risk", "matchable from outside sources"]]} />}>
        <div className="-mx-1 overflow-x-auto px-1"><ConnectionMap risk={R} /></div>
      </Section>
      {scan.attack && <AttackReplay attack={scan.attack} />}
      <Details scan={scan} />
    </>
  );
}

const Legend = ({ items }: { items: [string, string][] }) => (
  <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-muted-foreground">
    {items.map(([cls, label]) => <span key={label} className="inline-flex items-center gap-1.5"><i className={cn("size-2.5 rounded-sm", cls)} />{label}</span>)}
  </div>
);

function Stage({ n, title, hit, children }: { n: number; title: string; hit?: boolean; children: ReactNode }) {
  return (
    <div className={cn("stage flex min-w-0 flex-col gap-2 border bg-card p-4 md:border-l-0 md:first:rounded-l-xl md:first:border-l md:last:rounded-r-xl max-md:border-t-0 max-md:first:rounded-t-xl max-md:first:border-t max-md:last:rounded-b-xl",
      hit && "border-risk/45 bg-risk-soft")}>
      <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">
        <span className={cn("grid size-5 place-items-center rounded-full border bg-muted text-foreground", hit && "border-risk bg-risk text-white")}>{n}</span>{title}
      </span>
      {children}
    </div>
  );
}

function AttackReplay({ attack }: { attack: Attack }) {
  const A = attack.before, hit = A.outcome === "identified", playing = useApp(s => s.play === "scan"), busy = useApp(s => s.busy === "another");
  const linked = Object.entries(A.linked ?? {}), total = linked.reduce((n, [, r]) => n + r, 0), facts = Object.keys(A.known).length;
  return (
    <Card className={cn("flex flex-col gap-4 bg-[radial-gradient(120%_140%_at_0%_0%,hsl(var(--risk)/0.08),transparent_60%)] p-5", playing && "play")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><span className="eyebrow">Attack replay on your data</span><h2 className="text-xl">How an outsider re-identifies one person</h2></div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={anotherPerson} disabled={busy}>{busy ? <Spinner /> : <Dices />} Another person</Button>
          <Button variant="risk" onClick={() => play("scan")}><Play /> Play the attack</Button>
        </div>
      </div>
      <div className="grid md:grid-cols-4">
        <Stage n={1} title="The outsider knows"><Facts facts={A.known} table={A.table} /><span className="text-sm text-muted-foreground">from a public register, social media or a leaked list</span></Stage>
        <Stage n={2} title={`Searches ${A.table}`} hit={hit}>
          <span className={cn("big-number text-3xl", hit && "text-risk")}>{hit ? "1 person" : `${fmt(A.matches)} people`}</span>
          <span className="text-sm text-muted-foreground">of {fmt(A.rows)} records fit all {facts} facts</span>
        </Stage>
        <Stage n={3} title="Learns who it is" hit={hit}>
          {Object.keys(A.revealed).length ? <Facts facts={A.revealed} table={A.table} tone="risk" /> : <span className="text-sm text-muted-foreground">No single person: the facts fit {fmt(A.matches)} people.</span>}
        </Stage>
        <Stage n={4} title="Unlocks through keys" hit={hit && total > 0}>
          {hit ? <><span className="big-number text-3xl text-risk">{fmt(total)}</span><span className="text-sm text-muted-foreground">records about this person</span>
            <Facts facts={Object.fromEntries(linked.map(([t, r]) => [t, fmt(r)]))} table="" /></> : <span className="text-sm text-muted-foreground">Nothing certain to unlock.</span>}
        </Stage>
      </div>
      <Verdict tone={hit ? "risk" : "safe"} badge={hit ? "Re-identified" : "Not singled out"}>
        {hit ? `${facts} everyday facts are enough to name this person and open ${plural(total, "record")} across ${plural(linked.length, "table")}. This is the mosaic effect, and it is why the data cannot be shared as it is.`
          : `On these facts the person hides among ${fmt(A.matches)} people. Other columns may still expose them; see the tables below.`}
      </Verdict>
      {hit && attack.trail && attack.trail.length > 0 && <Trail attack={attack} />}
      <AcrossOrganisations />
    </Card>
  );
}

/** The mosaic effect step by step: from the outsider's facts through each table, and what each one gives away. */
function Trail({ attack }: { attack: Attack }) {
  const role = useRole(), trail = attack.trail!;
  const arrow = (label: string, sub: string) => (
    <div className="flex shrink-0 items-center gap-2.5 px-1.5 max-md:pl-6 md:w-[118px] md:flex-col md:justify-center md:text-center">
      <span className="font-mono text-xs font-semibold text-risk">{label}</span>
      <span aria-hidden className="flex items-center text-risk max-md:order-first max-md:flex-col md:w-full">
        <i className="block bg-risk max-md:h-6 max-md:w-0.5 md:h-0.5 md:flex-1" /><ArrowRight className="-ml-1.5 size-4 max-md:hidden" /><ArrowDown className="-mt-1.5 size-4 md:hidden" />
      </span>
      <span className="text-xs text-muted-foreground">{sub}</span>
    </div>
  );
  const node = (h: Hop) => (
    <div className="flex shrink-0 flex-col gap-1.5 rounded-xl border border-risk/45 bg-risk-soft p-3.5 md:w-[260px]">
      <div className="flex items-center justify-between gap-2"><b className="font-mono">{h.table}</b><Badge variant="risk">{plural(h.rows, "record")}</Badge></div>
      {Object.entries(h.learnt).map(([k, v]) => {
        const [, vals, more = ""] = v.match(/^(.*?)( \+\d+ more)?$/s) ?? [];
        return <div key={k} className="flex flex-col border-b border-dashed border-risk/25 py-1 text-[12.5px]"><span className="font-mono text-[11px] text-muted-foreground">{k}</span>
          <b className={cn("font-semibold [overflow-wrap:anywhere]", ROLE_TONE[role(h.table, k)] ?? "")}>{text(vals)}{more}</b></div>;
      })}
      {!Object.keys(h.learnt).length && <span className="text-sm text-muted-foreground">nothing telling beyond the link</span>}
    </div>
  );
  return (
    <div className="flex flex-col gap-3 border-t border-dashed pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Follow the trail: what each table gives away</h3>
        <span className="text-sm text-muted-foreground">{plural(trail.length, "table")} · {fmt(trail.reduce((n, h) => n + h.rows, 0))} records about one person</span></div>
      <div className="trail flex flex-col overflow-x-auto pb-1.5 md:flex-row md:items-stretch">
        <div className="flex shrink-0 flex-col gap-1.5 rounded-xl border bg-muted p-3.5 md:w-[220px]"><b>The outsider</b><Facts facts={attack.before.known} table={attack.before.table} /></div>
        {trail.flatMap((h, i) => [<div key={`a${i}`}>{i === 0 ? arrow("search", "1 person fits") : arrow(`via ${h.via}`, `from ${h.from_table}`)}</div>, <div key={`n${i}`}>{node(h)}</div>])}
      </div>
      <p className="text-sm text-muted-foreground">Red identifies the person, blue is sensitive. Each arrow is a key shared by two tables: knowing one row opens the next table.</p>
    </div>
  );
}

/** On the hospital example, the same attack followed into other organisations' data (the Mosaic attack demo). */
function AcrossOrganisations() {
  const built = useApp(s => !!s.cat?.screens?.includes("mosaic")), health = useApp(s => !!s.session?.tables.some(t => t.name === "ed_visits"));
  if (!built || !health) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed px-4 py-3 text-sm">
      <span>This attack stays inside your dataset. See it continue from a public post into the bank, energy, transport and school data of the same person.</span>
      <Button size="sm" variant="outline" onClick={() => go("mosaic")}>Mosaic attack across organisations <ArrowRight /></Button>
    </div>
  );
}

/** Tables, the keys that join them, and the columns an outsider could match (drawn as an SVG). */
function ConnectionMap({ risk }: { risk: Scan["risk"] }) {
  const tables = risk.tables.map(t => t.table), n = tables.length, cols = Math.min(n, 4);
  const W = 960, nodeW = 200, nodeH = 74, top = 120, gapY = 70, rows = Math.ceil(n / cols), H = top + rows * (nodeH + gapY) + 24;
  const pos: Record<string, { x: number; y: number }> = {};
  tables.forEach((t, i) => {
    const r = Math.floor(i / cols), c = i % cols, inRow = Math.min(cols, n - r * cols), span = W / inRow;
    pos[t] = { x: span * c + span / 2, y: top + 40 + r * (nodeH + gapY) };
  });
  const out = { x: W / 2, y: 34 }, exp = Object.fromEntries(risk.tables.map(t => [t.table, t]));
  return (
    <svg className="map block h-auto w-full max-md:min-w-[680px]" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Tables, the keys that join them, and the columns that link to outside sources">
      {risk.tables.filter(t => t.outside_links.length).map(t => {
        const p = pos[t.table];
        return <g key={`o${t.table}`}><path className="edge out" d={`M${out.x},${out.y + 22} C${out.x},${(out.y + p.y) / 2} ${p.x},${(out.y + p.y) / 2} ${p.x},${p.y - nodeH / 2}`} />
          <text x={p.x} y={p.y - nodeH / 2 - 8} textAnchor="middle" fontSize="11" className="muted">{t.outside_links.slice(0, 3).join(", ")}{t.outside_links.length > 3 ? "…" : ""}</text></g>;
      })}
      {risk.links.map((l, i) => {
        const a = pos[l.from_table], b = pos[l.to_table], mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 + (a.y === b.y ? 46 + 14 * i : 0);
        return <g key={`e${i}`}><path className="edge" d={`M${a.x},${a.y + nodeH / 2} Q${mx},${my + nodeH} ${b.x},${b.y + nodeH / 2}`} />
          <rect className="lab" x={mx - 58} y={my + nodeH / 2 - 11} width="116" height="22" rx="11" />
          <text x={mx} y={my + nodeH / 2 + 4} textAnchor="middle" fontSize="11">{l.from_column}</text></g>;
      })}
      <rect className="outside" x={out.x - 230} y={out.y - 22} width="460" height="44" rx="22" />
      <text x={out.x} y={out.y + 5} textAnchor="middle" fontSize="13" fontWeight="600">Outside world: public registers, social media, leaked lists</text>
      {tables.map(t => {
        const p = pos[t], e = exp[t], hot = e.unique_share >= 0.5 || e.direct_identifiers.length > 0;
        return <g key={`n${t}`}><rect className={cn("node", hot && "hot")} x={p.x - nodeW / 2} y={p.y - nodeH / 2} width={nodeW} height={nodeH} rx="12" />
          <text x={p.x} y={p.y - 12} textAnchor="middle" fontSize="14" fontWeight="600">{t}</text>
          <text x={p.x} y={p.y + 6} textAnchor="middle" fontSize="12" className="muted">{fmt(e.rows)} rows</text>
          <text x={p.x} y={p.y + 24} textAnchor="middle" fontSize="12" style={{ fill: e.unique_share >= 0.5 ? "hsl(var(--risk))" : "hsl(var(--muted-foreground))" }}>
            {e.quasi_identifiers.length ? `${pct(e.unique_share)} singled out` : "no quasi-identifiers"}</text></g>;
      })}
    </svg>
  );
}
