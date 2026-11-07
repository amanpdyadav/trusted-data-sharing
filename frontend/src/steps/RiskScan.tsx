// Step 2: what could go wrong if the data were shared as it is. Headline numbers, the attack replay on one
// person and the trail through the tables, the connection map, then the detail per table and per column.
import { ArrowDown, ArrowRight, Dices, Download, Play } from "lucide-react";
import { useState } from "react";
import { Facts, Guide, Kpi, Kpis, PageHead, ProgressCard, Section, useRole, useShown } from "@/components/common";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/form";
import { Meter, Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Attack, Hop, Scan, TableExposure } from "@/lib/api";
import { ROLE_LABEL, ROLE_TONE, clip, fmt, pct, plural } from "@/lib/format";
import { anotherPerson, correctColumn, detectionHref, go, play, runScan, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";

export function RiskScan() {
  const scan = useApp(s => s.scan), progress = useApp(s => s.progress);
  const title = "What could go wrong if this data were shared as it is";
  if (!scan) return <><PageHead title={title} />{progress ? <ProgressCard /> : <div><Button size="lg" onClick={runScan}>Scan for risks</Button></div>}</>;
  const R = scan.risk, worst = [...R.tables].sort((a, b) => b.unique_share - a.unique_share)[0];
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

export const Legend = ({ items }: { items: [string, string][] }) => (
  <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-muted-foreground">
    {items.map(([cls, label]) => <span key={label} className="inline-flex items-center gap-1.5"><i className={cn("size-2.5 rounded-sm", cls)} />{label}</span>)}
  </div>
);

function Stage({ n, title, hit, children }: { n: number; title: string; hit?: boolean; children: React.ReactNode }) {
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

export const Verdict = ({ tone, badge, children }: { tone: "risk" | "safe"; badge: string; children: React.ReactNode }) => (
  <div className={cn("verdict flex flex-wrap items-center gap-3.5 rounded-xl px-4 py-3.5", tone === "risk" ? "bg-risk-soft" : "bg-safe-soft")}>
    <span className={cn("rounded-md px-3 py-2 font-display text-[13px] font-extrabold uppercase tracking-wider text-white", tone === "risk" ? "bg-risk" : "bg-safe")}>{badge}</span>
    <span className="flex-1">{children}</span>
  </div>
);

/** The mosaic effect step by step: from the outsider's facts through each table, and what each one gives away. */
function Trail({ attack }: { attack: Attack }) {
  const shown = useShown(), role = useRole(), trail = attack.trail!;
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
          <b className={cn("font-semibold [overflow-wrap:anywhere]", ROLE_TONE[role(h.table, k)] ?? "")}>{shown(h.table, k, vals)}{more}</b></div>;
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

function Details({ scan }: { scan: Scan }) {
  const R = scan.risk, det = scan.detections.columns, people = Object.values(R.person ?? {}).reduce((n, r) => n + r.length, 0);
  return (
    <Card className="p-5">
      <Tabs defaultValue="tables">
        <TabsList>
          <TabsTrigger value="tables">Exposure per table <Badge>{R.tables.length}</Badge></TabsTrigger>
          <TabsTrigger value="person">One person's file <Badge>{people}</Badge></TabsTrigger>
          <TabsTrigger value="columns">What each column is <Badge>{det.length}</Badge></TabsTrigger>
        </TabsList>
        <TabsContent value="tables"><div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,240px),1fr))] gap-3">{R.tables.map(t => <ExposureCard key={t.table} t={t} />)}</div></TabsContent>
        <TabsContent value="person"><PersonFile person={R.person} /></TabsContent>
        <TabsContent value="columns"><ColumnsByTable scan={scan} /></TabsContent>
      </Tabs>
    </Card>
  );
}

function ExposureCard({ t }: { t: TableExposure }) {
  const chips = (cols: string[], v: "risk" | "warn" | "safe") => cols.map(c => <Badge key={c} variant={v} className="font-mono">{c}</Badge>);
  const row = (label: string, cols: string[], v: "risk" | "warn" | "safe") => cols.length > 0 && <div className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">{label}: {chips(cols, v)}</div>;
  return (
    <div className={cn("flex flex-col gap-3 rounded-xl border bg-muted p-4", t.unique_share >= 0.5 && "border-risk/50")}>
      <div className="flex flex-wrap items-center justify-between gap-2"><b className="min-w-0 break-all font-mono">{t.table}</b>{t.special_category && <Badge variant="risk">GDPR Art. 9</Badge>}</div>
      <div><div className="flex justify-between text-[13px]"><span className="text-muted-foreground">singled out on quasi-identifiers</span><b className="tabular-nums">{pct(t.unique_share)}</b></div><Meter value={t.unique_share} /></div>
      {row("Identifies a person", t.direct_identifiers, "risk")}{row("An outsider may know", t.quasi_identifiers, "warn")}
      {row("Sensitive", t.sensitive, "safe")}{row("Free text", t.free_text, "risk")}
    </div>
  );
}

/** Groups for what one person's records give away, in the same colours as the rest of the scan. */
const PERSON_GROUPS: { title: string; roles: string[]; tone: "risk" | "warn" | "safe" | "outline" }[] = [
  { title: "Identifies the person", roles: ["direct_identifier"], tone: "risk" },
  { title: "An outsider may know", roles: ["quasi_identifier"], tone: "warn" },
  { title: "Sensitive", roles: ["sensitive_attribute"], tone: "safe" },
  { title: "Free text", roles: ["free_text"], tone: "risk" },
  { title: "Codes and other details", roles: [], tone: "outline" },
];

function PersonFile({ person }: { person: Record<string, Record<string, string>[]> }) {
  const tables = Object.keys(person ?? {});
  if (!tables.length) return <p className="text-sm text-muted-foreground">No person key found, so records cannot be gathered per person.</p>;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">One person picked the way an attacker would: someone with several records. Facts that are the same in every record are shown once, grouped by what they give away; below them, what changes from record to record.</p>
      <Accordion type="multiple" defaultValue={[tables[0]]} className="flex flex-col gap-2">
        {tables.map(t => <PersonTable key={t} table={t} records={person[t]} />)}
      </Accordion>
    </div>
  );
}

function PersonTable({ table, records }: { table: string; records: Record<string, string>[] }) {
  const shown = useShown(), role = useRole();
  const cols = [...new Set(records.flatMap(r => Object.keys(r)))];
  const same = records.length > 1 ? cols.filter(c => records.every(r => (r[c] ?? "") === (records[0][c] ?? ""))) : cols;
  const varies = cols.filter(c => !same.includes(c));
  const known = PERSON_GROUPS.flatMap(g => g.roles);
  const groups = PERSON_GROUPS.map(g => ({ ...g, cols: same.filter(c => (g.roles.length ? g.roles.includes(role(table, c)) : !known.includes(role(table, c)))) })).filter(g => g.cols.length);
  const exposing = same.filter(c => ["direct_identifier", "quasi_identifier"].includes(role(table, c))).length;
  return (
    <AccordionItem value={table}>
      <AccordionTrigger right={<>{plural(records.length, "record")}{exposing ? <span className="text-risk"> · {exposing} identifying facts in every one</span> : null}</>}><b className="font-mono">{table}</b></AccordionTrigger>
      <AccordionContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="eyebrow text-muted-foreground">{records.length > 1 ? `The same in all ${records.length} records` : "The record"}</span>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,280px),1fr))] gap-3">
            {groups.map(g => (
              <div key={g.title} className={cn("flex flex-col gap-2 rounded-xl border bg-muted p-4", g.tone === "risk" && "border-risk/40")}>
                <div className="flex items-center justify-between gap-2"><b className="text-sm">{g.title}</b><Badge variant={g.tone}>{g.cols.length}</Badge></div>
                <Facts table={table} facts={Object.fromEntries(g.cols.map(c => [c, clip(records[0][c] ?? "", 44)]))} />
              </div>
            ))}
          </div>
        </div>
        {varies.length > 0 && (
          <div className="flex flex-col gap-2">
            <span className="eyebrow text-muted-foreground">What changes from record to record</span>
            <TableWrap>
              <table className="w-full border-collapse">
                <thead><tr><Th>#</Th>{varies.map(c => <Th key={c} className={ROLE_TONE[role(table, c)]}>{c}</Th>)}</tr></thead>
                <tbody>{records.map((r, i) => (
                  <tr key={i}><Td className="tabular-nums text-muted-foreground">{i + 1}</Td>
                    {varies.map(c => { const v = shown(table, c, r[c] ?? ""); return <Td key={c} className={cn("whitespace-nowrap", ROLE_TONE[role(table, c)])} title={clip(v, 600)}>{clip(v, 40) || "–"}</Td>; })}</tr>
                ))}</tbody>
              </table>
            </TableWrap>
          </div>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}

function ColumnsByTable({ scan }: { scan: Scan }) {
  const det = scan.detections.columns, tables = [...new Set(det.map(c => c.table))];
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Found from column names and values (ID-code checksums, IBAN and card check digits, phone formats, name shapes, dates, code sets). Wrong? Open it and change it; the plan follows your correction.</p>
        <Button size="sm" variant="outline" asChild><a href={detectionHref()}><Download /> detection.json</a></Button>
      </div>
      <Accordion type="multiple" defaultValue={[tables[0]]} className="flex flex-col gap-2">
        {tables.map(t => {
          const cols = det.map((c, i) => [c, i] as const).filter(([c]) => c.table === t);
          const ident = cols.filter(([c]) => c.privacy_role === "direct_identifier").length, qi = cols.filter(([c]) => c.privacy_role === "quasi_identifier").length;
          return (
            <AccordionItem key={t} value={t}>
              <AccordionTrigger right={<>{plural(cols.length, "column")}{ident ? <span className="text-risk"> · {ident} identify a person</span> : null}{qi ? <span className="text-warn"> · {qi} outsider may know</span> : null}</>}><b className="font-mono">{t}</b></AccordionTrigger>
              <AccordionContent className="p-0">
                <TableWrap className="rounded-none border-0">
                  <table className="w-full border-collapse"><thead><tr><Th>Column</Th><Th>What it is</Th><Th>Type</Th><Th>How sure</Th><Th /></tr></thead>
                    <tbody>{cols.map(([c, i]) => (
                      <tr key={c.column} className="cursor-pointer hover:bg-muted" onClick={() => setOpen(i)}>
                        <Td className="font-mono">{c.column}</Td>
                        <Td className={ROLE_TONE[c.privacy_role]}>{ROLE_LABEL[c.privacy_role] ?? c.privacy_role}{c.evidence.some(e => e.kind === "manual") && <Badge variant="ok" className="ml-2">corrected</Badge>}</Td>
                        <Td className="font-mono text-xs text-muted-foreground">{c.subtype}</Td><Td><Meter value={c.confidence} tone="safe" className="w-20" /></Td>
                        <Td><Button size="sm" variant="outline">Details</Button></Td>
                      </tr>))}</tbody></table>
                </TableWrap>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
      {open != null && <ColumnDialog index={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

/** Why a column was classified as it was, a few values, and a correction form. */
function ColumnDialog({ index, onClose }: { index: number; onClose: () => void }) {
  const c = useApp(s => s.scan!.detections.columns[index]), cat = useApp(s => s.cat!), session = useApp(s => s.session!), busy = useApp(s => s.busy === "scan");
  const shown = useShown(), samples = (session.tables.find(t => t.name === c.table)?.preview ?? []).map(r => r[c.column]).filter(v => v).slice(0, 6);
  const select = "h-9 w-full rounded-lg border border-input bg-card px-2.5 text-sm";
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle className="font-mono">{c.table}.{c.column}</DialogTitle></DialogHeader>
        <DialogBody>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5"><Label>What it is</Label>
              <select className={select} value={c.privacy_role} onChange={e => correctColumn(index, "privacy_role", e.target.value)}>{cat.roles.map(r => <option key={r} value={r}>{ROLE_LABEL[r] ?? r}</option>)}</select></div>
            <div className="flex flex-col gap-1.5"><Label>Type</Label>
              <select className={select} value={c.subtype} onChange={e => correctColumn(index, "subtype", e.target.value)}>{cat.subtypes.map(r => <option key={r}>{r}</option>)}</select></div>
          </div>
          <div><span className="eyebrow">How sure</span><div className="flex items-center gap-3"><Meter value={c.confidence} tone="safe" className="flex-1" /><b className="tabular-nums">{c.confidence.toFixed(2)}</b></div></div>
          <div><span className="eyebrow">Why</span><ul className="mt-1 flex flex-col gap-1.5 text-sm">{c.evidence.map((e, i) => <li key={i} className="flex items-baseline gap-2"><Badge>{e.kind}</Badge>{e.detail}</li>)}</ul></div>
          {samples.length > 0 && <div><span className="eyebrow">Values from the first rows</span><div className="mt-1 flex flex-wrap gap-1.5">{samples.map((v, i) => <Badge key={i} className="font-mono">{clip(shown(c.table, c.column, v), 40)}</Badge>)}</div></div>}
          <p className="text-xs text-muted-foreground">A change is kept as a reviewer's correction (with your name in the evidence) and the plan follows it.</p>
        </DialogBody>
        <DialogFooter>{busy && <Spinner />}<Button onClick={onClose}>Done</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
