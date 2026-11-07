// The risk scan's tabs: exposure per table, one person's file, and what each column is (with corrections).
import { Download } from "lucide-react";
import { useState } from "react";
import { Facts, useRole } from "@/components/common";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label, Select } from "@/components/ui/form";
import { Meter, Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Scan, TableExposure } from "@/lib/api";
import { ROLE_LABEL, ROLE_TONE, clip, pct, plural, text } from "@/lib/format";
import { correctColumn, detectionHref, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";

export function Details({ scan }: { scan: Scan }) {
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
  const role = useRole();
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
                    {varies.map(c => { const v = text(r[c] ?? ""); return <Td key={c} className={cn("whitespace-nowrap", ROLE_TONE[role(table, c)])} title={clip(v, 600)}>{clip(v, 40) || "–"}</Td>; })}</tr>
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
  const samples = (session.tables.find(t => t.name === c.table)?.preview ?? []).map(r => r[c.column]).filter(v => v).slice(0, 6);
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle className="font-mono">{c.table}.{c.column}</DialogTitle></DialogHeader>
        <DialogBody>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5"><Label>What it is</Label>
              <Select className="w-full" value={c.privacy_role} onChange={e => correctColumn(index, "privacy_role", e.target.value)}>{cat.roles.map(r => <option key={r} value={r}>{ROLE_LABEL[r] ?? r}</option>)}</Select></div>
            <div className="flex flex-col gap-1.5"><Label>Type</Label>
              <Select className="w-full" value={c.subtype} onChange={e => correctColumn(index, "subtype", e.target.value)}>{cat.subtypes.map(r => <option key={r}>{r}</option>)}</Select></div>
          </div>
          <div><span className="eyebrow">How sure</span><div className="flex items-center gap-3"><Meter value={c.confidence} tone="safe" className="flex-1" /><b className="tabular-nums">{c.confidence.toFixed(2)}</b></div></div>
          <div><span className="eyebrow">Why</span><ul className="mt-1 flex flex-col gap-1.5 text-sm">{c.evidence.map((e, i) => <li key={i} className="flex items-baseline gap-2"><Badge>{e.kind}</Badge>{e.detail}</li>)}</ul></div>
          {samples.length > 0 && <div><span className="eyebrow">Values from the first rows</span><div className="mt-1 flex flex-wrap gap-1.5">{samples.map((v, i) => <Badge key={i} className="font-mono">{clip(text(v), 40)}</Badge>)}</div></div>}
          <p className="text-xs text-muted-foreground">A change is kept as a reviewer's correction (with your name in the evidence) and the plan follows it.</p>
        </DialogBody>
        <DialogFooter>{busy && <Spinner />}<Button onClick={onClose}>Done</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
