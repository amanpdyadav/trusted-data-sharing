// Step 5: release and proof. Create the release, replay the same attack on it, show what changed record by
// record and column by column, keep every release for download and comparison.
import { ArrowLeft, ArrowRight, Download, Play, Plus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Facts, Kpi, Kpis, PageHead, useRole, Verdict } from "@/components/common";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/form";
import { Meter, Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { valuesKept, type AttackResult, type Lookalikes, type Results } from "@/lib/api";
import { ROLE_TONE, fmt, pct, plural, text, when } from "@/lib/format";
import { laneOf, planTables, techniqueTone } from "@/lib/lanes";
import { askDownload, createRelease, downloadRelease, planHref, play, useApp, viewRelease } from "@/lib/store";
import { cn } from "@/lib/utils";
import { History } from "@/steps/ReleaseHistory";

export function Release() {
  const R = useApp(s => s.results), plan = useApp(s => s.plan), viewing = useApp(s => s.viewing), history = useApp(s => s.history);
  const [create, setCreate] = useState(false);
  const dialogs = <><CreateDialog open={create} onOpenChange={setCreate} /><PublishDialog /></>;
  if (!R) return (
    <>
      <PageHead title="Release and proof" />
      <Card className="flex flex-wrap items-center justify-between gap-4 border-safe/40 p-5">
        <div><span className="eyebrow text-safe">Approved by {plan?.plan.approved_by}</span><h2 className="text-xl">Create the release for {plan?.scenario?.recipient ?? plan?.plan.scenario_id}</h2>
          <p className="text-sm text-muted-foreground">The protected files are written, checked against the plan, and replayed against the same attacker.</p></div>
        <Button size="lg" onClick={() => setCreate(true)}>Create the release…</Button>
      </Card>
      {dialogs}
    </>
  );
  const m = R.summary, kept = valuesKept(R), A = R.attack;
  return (
    <>
      <PageHead title="Release and proof" lede={<><b className="text-foreground">{m.release_id}</b> for {m.recipient} · approved by {m.approved_by ?? "–"} · {when(m.created_at)}</>} />
      {viewing && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/40 bg-warn-soft px-4 py-2.5 text-sm">
        <span>Viewing an earlier release: <b>{m.release_id}</b>, made {when(m.created_at)}.</span>
        {history[0] && history[0].release_id !== m.release_id && <Button size="sm" variant="outline" onClick={() => viewRelease(history[0].release_id)}>Open the latest</Button>}</div>}
      {A?.after && <Duel before={A.before} after={A.after} />}
      <Card className="flex flex-col gap-3 border-safe/45 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><span className="eyebrow">Download</span><h2 className="text-xl">{R.files.map(f => f.name).join(", ")} + manifest</h2></div>
          <div className="flex gap-2">
            <Button variant="safe" onClick={askDownload}><Download /> Download release (.zip)</Button>
            <Button variant="outline" asChild><a href={planHref()}>Approved plan</a></Button>
            {plan?.plan.approved && !viewing && <Button variant="outline" onClick={() => setCreate(true)}><Plus /> New release…</Button>}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">The zip holds only what may be shared. Row maps stay on this computer.{m.epsilon != null && ` Publishing spends ε ${m.epsilon}${R.published ? " (already recorded)" : ""}.`}</p>
      </Card>
      <Kpis>
        {m.singled_out_after != null && <Kpi tone="safe" value={<>{pct(m.singled_out_after)} <s className="text-xl text-muted-foreground">{pct(m.singled_out_before)}</s></>} label="singled out (raw struck through)" />}
        {kept != null && <Kpi tone={kept >= 0.8 ? "ok" : "warn"} value={pct(kept, 1)} label="values kept in released columns" />}
        {m.epsilon != null && <Kpi tone="safe" value={`ε ${m.epsilon}`} label="privacy budget for these statistics" />}
      </Kpis>
      <details className="rounded-2xl border bg-card px-5 py-3">
        <summary className="cursor-pointer font-medium text-muted-foreground">Evidence: records, columns, risks, history</summary>
        <div className="mt-3"><Proof R={R} /></div>
      </details>
      {dialogs}
    </>
  );
}

function CreateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const plan = useApp(s => s.plan), busy = useApp(s => s.busy === "run"), [name, setName] = useState("receiver");
  if (!plan) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Create the release</DialogTitle></DialogHeader>
        <DialogBody>
          <div className="flex flex-col gap-1.5"><Label htmlFor="receiver">Receiver name</Label><Input id="receiver" autoFocus value={name} onChange={e => setName(e.target.value)} /></div>
          <p className="text-sm text-muted-foreground">The name selects the receiver's own key: each receiver gets different codes, so two receivers cannot join their copies.</p>
          <div><span className="eyebrow">Files</span><div className="mt-1 flex flex-wrap gap-1.5">
            {planTables(plan.plan).map(t => <Badge key={t} variant="safe" className="font-mono">{t}.csv</Badge>)}
            {plan.plan.aggregates.map(a => <Badge key={a.name} variant="safe" className="font-mono">{a.name}.csv</Badge>)}<Badge className="font-mono">manifest.json</Badge></div></div>
          <p className="text-sm text-muted-foreground">Row maps (which released row came from which record) stay in the private folder on this computer.</p>
        </DialogBody>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={busy || !name.trim()} onClick={async () => { if (await createRelease(name.trim())) onOpenChange(false); }}>{busy && <Spinner className="text-current" />}Create the release</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Statistics spend privacy budget when they are published, so the first download asks first. */
function PublishDialog() {
  const ask = useApp(s => s.publishAsk), R = useApp(s => s.results), busy = useApp(s => s.busy === "download");
  if (!R) return null;
  const close = () => useApp.setState({ publishAsk: false });
  return (
    <Dialog open={ask} onOpenChange={o => !o && close()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Publish these statistics?</DialogTitle></DialogHeader>
        <DialogBody>
          <p>Downloading publishes <b>{plural(R.statistics.length, "statistics table")}</b> and spends <b>ε {R.summary.epsilon}</b> of the privacy budget for this receiver{R.summary.budget_cap ? ` (cap ε ${R.summary.budget_cap})` : ""}.</p>
          <p className="text-sm text-muted-foreground">The spending is written to the privacy budget ledger once; downloading again later does not spend more.</p>
        </DialogBody>
        <DialogFooter><Button variant="outline" onClick={close}>Cancel</Button>
          <Button variant="safe" disabled={busy} onClick={async () => { await downloadRelease(R.release_id); close(); }}>{busy && <Spinner className="text-current" />}Publish and download</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function StageV({ label, tone, children }: { label: string; tone?: "hit" | "miss"; children: ReactNode }) {
  return (
    <div className={cn("stage grid items-start gap-3 rounded-xl border bg-card px-3.5 py-3 sm:grid-cols-[104px_minmax(0,1fr)]", tone === "hit" && "border-risk/45 bg-risk-soft", tone === "miss" && "border-safe/45 bg-safe-soft")}>
      <span className="eyebrow pt-1">{label}</span><div className="flex min-w-0 flex-col gap-1">{children}</div>
    </div>
  );
}

function Duel({ before: b, after: a }: { before: AttackResult; after: AttackResult }) {
  const playing = useApp(s => s.play === "release"), failed = a.outcome !== "identified";
  const total = Object.values(b.linked ?? {}).reduce((n, r) => n + r, 0);
  const fits = a.outcome === "withheld" ? "no rows" : a.outcome === "removed" ? "not there" : a.matches === 1 ? "1 person" : `${fmt(a.matches)} people`;
  const fitsNote = a.outcome === "withheld" ? `${a.table} is not released at all` : a.outcome === "removed" ? "the row was removed to reach k" : `fit what is left of the facts: ${a.usable.length ? a.usable.join(", ") : "nothing to match on"}`;
  return (
    <Card className={cn("flex flex-col gap-4 bg-[radial-gradient(120%_140%_at_100%_0%,hsl(var(--safe)/0.08),transparent_60%)] p-5", playing && "play")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><span className="eyebrow">The same attack, replayed on the release</span><h2 className="text-xl">Same outsider, same facts, same person</h2></div>
        <Button variant="safe" onClick={() => play("release")}><Play /> Replay</Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-2.5"><span className="eyebrow">Raw data</span>
          <StageV label="Knows"><Facts facts={b.known} table={b.table} /></StageV>
          <StageV label="Fits" tone={b.outcome === "identified" ? "hit" : undefined}><span className="big-number text-[26px] text-risk">{b.matches === 1 ? "1 person" : `${fmt(b.matches)} people`}</span><span className="text-sm text-muted-foreground">of {fmt(b.rows)} records</span></StageV>
          <StageV label="Learns" tone={b.outcome === "identified" ? "hit" : undefined}>{Object.keys(b.revealed).length ? <Facts facts={b.revealed} table={b.table} tone="risk" /> : <span className="text-sm text-muted-foreground">nothing certain</span>}</StageV>
          <StageV label="Unlocks" tone={total ? "hit" : undefined}><span className="big-number text-[26px] text-risk">{fmt(total)}</span><span className="text-sm text-muted-foreground">linked records</span></StageV>
        </div>
        <div className="flex min-w-0 flex-col gap-2.5"><span className="eyebrow">Release</span>
          <StageV label="Knows"><Facts facts={a.known} table={a.table} /></StageV>
          <StageV label="Fits" tone={failed ? "miss" : undefined}><span className="big-number text-[26px] text-safe">{fits}</span><span className="text-sm text-muted-foreground">{fitsNote}</span></StageV>
          <StageV label="Learns" tone={failed ? "miss" : undefined}>{Object.keys(a.revealed).length ? <Facts facts={a.revealed} table={a.table} tone="risk" />
            : Object.keys(a.hidden).length ? <Facts facts={Object.fromEntries(Object.entries(a.hidden).map(([c, t]) => [c, t === "pseudonymise" ? "keyed code" : t === "drop" ? "dropped" : t]))} table="" tone="safe" />
            : <span className="text-sm text-muted-foreground">no identifiers in the release</span>}</StageV>
          <StageV label="Unlocks" tone={failed ? "miss" : undefined}><span className="big-number text-[26px] text-safe">{failed ? "0" : fmt(Object.values(a.linked).reduce((n, r) => n + r, 0))}</span>
            <span className="text-sm text-muted-foreground">{failed ? (a.outcome === "one_in_n" ? `certain records; only a guess with a 1 in ${fmt(a.matches)} chance` : "records") : "records reachable"}</span></StageV>
        </div>
      </div>
      <Verdict tone={failed ? "safe" : "risk"} badge={failed ? "Attack fails" : "Still found"}>
        {failed ? `The outsider who named this person in the raw data ${a.outcome === "one_in_n" ? `now faces ${fmt(a.matches)} equally likely people and no name, ID code or contact detail` : a.outcome === "withheld" ? "finds no rows to search: only statistics leave" : "cannot find their row: it was removed to protect them"}.`
          : "The release still singles this person out. Raise the protection level, drop or coarsen a fact an outsider may know, and release again."}
      </Verdict>
    </Card>
  );
}

function Proof({ R }: { R: Results }) {
  const history = useApp(s => s.history);
  const tabs: [string, string, number | null, ReactNode][] = [
    ["records", "Records before → after", null, <Records R={R} />], ["columns", "Column changes", R.tables.length, <ColumnChanges R={R} />],
    ["attacker", "Attacker's view", R.attacker.length, <AttackerView R={R} />],
    ...(R.text.length ? [["text", "Free text", R.text.length, <FreeText R={R} />] as [string, string, number, ReactNode]] : []),
    ...(R.statistics.length ? [["stats", "Statistics", R.statistics.length, <Statistics R={R} />] as [string, string, number, ReactNode]] : []),
    ["risks", "Remaining risks", R.residual_risks.length, <><p className="text-sm text-muted-foreground">As written in the manifest that travels with the data.</p><ul className="ml-5 list-disc space-y-1.5 text-[13.5px]">{R.residual_risks.map(r => <li key={r}>{r}</li>)}</ul></>],
    ["history", "History & compare", history.length, <History />],
  ];
  return (
    <Card className="p-5">
      <Tabs defaultValue="records">
        <TabsList>{tabs.map(([k, l, n]) => <TabsTrigger key={k} value={k}>{l}{n != null && <Badge>{n}</Badge>}</TabsTrigger>)}</TabsList>
        {tabs.map(([k, , , body]) => <TabsContent key={k} value={k} className="flex flex-col gap-3">{body}</TabsContent>)}
      </Tabs>
    </Card>
  );
}

function Records({ R }: { R: Results }) {
  const role = useRole(), withPairs = R.tables.filter(t => t.pairs?.length);
  const [tableName, setTable] = useState<string>(), [open, setOpen] = useState<number | null>(null);
  if (!R.tables.length) return <p className="text-sm text-muted-foreground">No rows are released: only statistics.</p>;
  if (!withPairs.length) return <p className="text-sm text-muted-foreground">These tables have no record key, so released rows cannot be matched to their records.</p>;
  const t = withPairs.find(x => x.name === tableName) ?? withPairs[0];
  const renamed = Object.fromEntries(t.changes.map(c => [c.column, c.released_as || c.column])), cols = Object.keys(t.pairs[0].raw);
  const tech = (c: string) => R.techniques[`${t.name}.${c}`] ?? "keep";
  const cell = (pair: (typeof t.pairs)[number], c: string) => {
    const k = tech(c).split(":")[0], v = pair.released[renamed[c]];
    if (k === "drop" || k === "withheld") return <Td key={c} className="font-mono text-[11px] text-risk">dropped</Td>;
    if (v === "" || v == null) return <Td key={c} className="font-mono text-[11px] text-warn">blanked for k</Td>;
    return <Td key={c} className={cn("whitespace-nowrap", k === "keep" ? "text-muted-foreground" : "font-semibold text-safe", k === "pseudonymise" && "font-mono text-xs font-normal")}>{v}</Td>;
  };
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">The same records, raw and released, matched on this computer through the private row map (which never leaves). Click a pair to see it in full.</p>
        {withPairs.length > 1 && <div className="flex gap-1">{withPairs.map(x => <Button key={x.name} size="sm" variant={x.name === t.name ? "default" : "outline"} onClick={() => setTable(x.name)}>{x.name}</Button>)}</div>}
      </div>
      <TableWrap>
        <table className="w-full border-collapse">
          <thead><tr><Th />{cols.map(c => <Th key={c}>{c}<br /><Badge variant={techniqueTone(tech(c))} className="mt-1 normal-case tracking-normal">{tech(c)}</Badge></Th>)}</tr></thead>
          <tbody>{t.pairs.map((p, i) => [
            <tr key={`r${i}`} className="cursor-pointer bg-risk-soft/40 hover:bg-risk-soft" onClick={() => setOpen(i)}>
              <Td className="sticky left-0 whitespace-nowrap bg-risk-soft text-[11px] font-semibold uppercase tracking-[0.06em] text-risk">raw ↗</Td>
              {cols.map(c => <Td key={c} className={cn("max-w-[220px] truncate whitespace-nowrap", ROLE_TONE[role(t.name, c)])}>{text(p.raw[c])}</Td>)}</tr>,
            <tr key={`p${i}`} className="border-b-2"><Td className="sticky left-0 whitespace-nowrap bg-card text-[11px] font-semibold uppercase tracking-[0.06em] text-safe">released</Td>{cols.map(c => cell(p, c))}</tr>,
          ])}</tbody>
        </table>
      </TableWrap>
      {open != null && (
        <Dialog open onOpenChange={o => !o && setOpen(null)}>
          <DialogContent wide>
            <DialogHeader><DialogTitle>One record of <span className="font-mono">{t.name}</span>, before and after</DialogTitle></DialogHeader>
            <DialogBody><TableWrap className="max-h-none"><table className="w-full border-collapse"><thead><tr><Th>Column</Th><Th>Raw (stays here)</Th><Th>Released</Th><Th>How</Th></tr></thead>
              <tbody>{cols.map(c => { const l = laneOf(tech(c).split(":")[0]); return <tr key={c}><Td className="font-mono">{c}</Td><Td className={ROLE_TONE[role(t.name, c)]}>{text(t.pairs[open].raw[c])}</Td>{cell(t.pairs[open], c)}<Td className="text-sm text-muted-foreground">{l.icon} {l.name}</Td></tr>; })}</tbody></table></TableWrap></DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen((open + t.pairs.length - 1) % t.pairs.length)}><ArrowLeft /> Previous</Button>
              <Button variant="outline" onClick={() => setOpen((open + 1) % t.pairs.length)}>Next <ArrowRight /></Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

function ColumnChanges({ R }: { R: Results }) {
  if (!R.tables.length) return <p className="text-sm text-muted-foreground">No rows are released.</p>;
  return (
    <Accordion type="multiple" defaultValue={[R.tables[0].name]} className="flex flex-col gap-2">
      {R.tables.map(t => {
        const blanked = t.suppression ? Object.values(t.suppression.cells_blanked).reduce((n, x) => n + x, 0) : 0;
        return (
          <AccordionItem key={t.name} value={t.name}>
            <AccordionTrigger right={t.suppression ? `${fmt(t.suppression.rows_removed)} rows removed, ${fmt(blanked)} values blanked for k` : undefined}>
              <b className="font-mono">{t.name}</b><span className="text-sm text-muted-foreground">{fmt(t.rows_in)} rows in, {fmt(t.rows_out)} out</span></AccordionTrigger>
            <AccordionContent className="p-0"><TableWrap className="rounded-none border-0"><table className="w-full border-collapse">
              <thead><tr><Th>Column</Th><Th>Protection</Th><Th>Values</Th><Th>Distinct</Th><Th>Released values</Th></tr></thead>
              <tbody>{t.changes.map(c => (
                <tr key={c.column}><Td className="font-mono">{c.column}{c.released_as && c.released_as !== c.column && ` → ${c.released_as}`}</Td>
                  <Td><Badge variant={techniqueTone(c.technique)}>{c.technique}</Badge></Td>
                  <Td className="tabular-nums">{fmt(c.filled_before)} → {fmt(c.filled_after)}</Td><Td className="tabular-nums">{fmt(c.distinct_before)} → {fmt(c.distinct_after)}</Td>
                  <Td className="min-w-[220px]">{c.top_after.slice(0, 5).map(([v, s]) => <div key={v} className="grid grid-cols-[minmax(0,9em)_1fr_40px] items-center gap-2 text-xs"><span className="truncate font-mono">{v}</span><Meter value={s} tone="safe" /><span className="text-right font-mono">{pct(s)}</span></div>)}</Td></tr>
              ))}</tbody></table></TableWrap></AccordionContent>
          </AccordionItem>
        );
      })}
    </Accordion>
  );
}

const BUCKET_TONE: Record<string, string> = { alone: "bg-risk", "2-4": "bg-warn", "5-9": "bg-safe", "10-49": "bg-safe", "50+": "bg-muted-foreground" };
const Buckets = ({ b }: { b: Lookalikes["buckets"] }) => (
  <div className="flex h-7 gap-0.5 overflow-hidden rounded-md">{Object.entries(b).filter(([, v]) => v > 0).map(([k, v]) =>
    <div key={k} title={`${k}: ${pct(v, 1)}`} className={cn("min-w-0 overflow-hidden whitespace-nowrap px-1.5 font-mono text-[11px] font-semibold leading-7 text-white", BUCKET_TONE[k])} style={{ flex: v }}>{v > 0.08 ? `${k} ${pct(v)}` : ""}</div>)}</div>
);
function AttackerView({ R }: { R: Results }) {
  if (!R.attacker.length) return <p className="text-sm text-muted-foreground">No table was checked for look-alikes (statistics only, or no facts an outsider may know).</p>;
  return <>{R.attacker.map(v => (
    <div key={v.table} className="flex flex-col gap-2"><h3 className="font-semibold">{v.table}: someone who knows {v.known.join(", ")}</h3>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-xl border border-risk/40 bg-muted p-4"><span className="eyebrow">Before</span><span className="big-number text-3xl text-risk">{pct(v.before.unique_share)}</span><span className="text-sm text-muted-foreground">of {fmt(v.before.rows)} rows have no look-alike: found with certainty</span><Buckets b={v.before.buckets} /></div>
        <div className="flex flex-col gap-2 rounded-xl border border-safe/40 bg-muted p-4"><span className="eyebrow">After</span><span className="big-number text-3xl text-safe">{pct(v.after.unique_share)}</span><span className="text-sm text-muted-foreground">have no look-alike; an attacker's chance to pick the right person is {pct(v.after.guess_chance, 1)}</span><Buckets b={v.after.buckets} /></div>
      </div></div>))}
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">{[["bg-risk", "alone"], ["bg-warn", "2–4 look-alikes"], ["bg-safe", "5–49"], ["bg-muted-foreground", "50 or more"]].map(([c, l]) => <span key={l} className="inline-flex items-center gap-1.5"><i className={cn("size-2.5 rounded-sm", c)} />{l}</span>)}</div></>;
}

function FreeText({ R }: { R: Results }) {
  const [after, setAfter] = useState(true);
  return <>{R.text.map(t => (
    <div key={t.column} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-mono font-semibold">{t.column}</h3>
        <div className="flex gap-1"><Button size="sm" variant={after ? "outline" : "default"} onClick={() => setAfter(false)}>Found</Button><Button size="sm" variant={after ? "default" : "outline"} onClick={() => setAfter(true)}>Released</Button></div></div>
      <div className="grid gap-3 md:grid-cols-2">{t.samples.map((parts, i) => (
        <div key={i} className="whitespace-pre-wrap rounded-xl border bg-muted px-3.5 py-3 text-sm leading-7 [overflow-wrap:anywhere]">
          {parts.map((p, j) => !p.label ? <span key={j}>{p.t}</span> : after
            ? <span key={j} className="rounded bg-safe-soft px-1 font-mono text-xs text-safe">[{p.label}]</span>
            : <mark key={j} title={p.label} className="rounded bg-risk-soft px-0.5 text-risk">{p.t}</mark>)}
        </div>))}</div>
    </div>))}</>;
}

function Statistics({ R }: { R: Results }) {
  const acc = Object.fromEntries(R.accuracy.map(a => [a.name, a]));
  return <>
    <p className="text-sm text-muted-foreground">Noisy published numbers against the exact numbers (cells with at least 10 records). The exact numbers never leave.</p>
    {R.statistics.map(s => <div key={s.name} className="grid grid-cols-[minmax(0,14em)_1fr_48px] items-center gap-2 text-[13px]"><span className="truncate font-mono">{s.name}</span><Meter value={acc[s.name]?.within_10pct ?? 0} tone="safe" /><span className="text-right font-mono">{pct(acc[s.name]?.within_10pct)}</span></div>)}
    <p className="text-sm text-muted-foreground">Bar: share of cells within 10% of the true value. ε {R.epsilon} spent in this release.</p>
    <div className="grid gap-3 md:grid-cols-2">{R.statistics.slice(0, 2).map(s => {
      const cols = Object.keys(s.preview[0] ?? {});
      return <div key={s.name}><span className="eyebrow">{s.name} · {fmt(s.cells)} cells</span><TableWrap><table className="w-full border-collapse"><thead><tr>{cols.map(c => <Th key={c}>{c}</Th>)}</tr></thead><tbody>{s.preview.map((r, i) => <tr key={i}>{cols.map(c => <Td key={c}>{r[c]}</Td>)}</tr>)}</tbody></table></TableWrap></div>;
    })}</div>
  </>;
}
