// Step 3: who gets the data, and what will they see. Pick a receiver; the tool decides how each column is shared
// and shows the result (lanes, an example record, the protection level) before anything leaves.
import { AlertTriangle, ArrowLeft, ArrowRight, FileCode2, LayoutGrid } from "lucide-react";
import { useState } from "react";
import { Guide, PageHead, Section, useRole } from "@/components/common";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/form";
import { Meter, Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Action, Column, Receiver } from "@/lib/api";
import { ROLE_LABEL, ROLE_TONE, clip, pct, plural, text, words } from "@/lib/format";
import { LANES, RECEIVER_ICON, TIME_UNITS, laneOf, planTables, techniqueTone } from "@/lib/lanes";
import { changeColumn, loadCompare, makePlan, setK, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";
import { CustomReceiver } from "@/steps/CustomReceiver";
import { PlanVersionsPanel, PlanYaml } from "@/steps/PlanVersions";

const LANE_SHOWN = 6;

export function PlanStep() {
  const cat = useApp(s => s.cat!), plan = useApp(s => s.plan), choice = useApp(s => s.receiverChoice), busy = useApp(s => s.busy === "plan");
  const session = useApp(s => s.session);
  const [custom, setCustom] = useState(false);
  // A receiver fits this data when every table it asks for is here (works for uploads too, not just by dataset name).
  const have = new Set(session?.tables.map(t => t.name) ?? []);
  const missing = (r: Receiver) => (r.tables ?? []).filter(t => !have.has(t));
  const fitting = cat.receivers.filter(r => missing(r).length === 0), other = cat.receivers.filter(r => missing(r).length > 0);
  const card = (r: Receiver, off = false) => (
    <ReceiverCard key={r.id} icon={RECEIVER_ICON[r.trust_level] ?? "📦"} title={r.recipient} text={r.purpose} selected={choice === r.id} disabled={off}
      note={off ? `Made for the ${words(r.dataset)} data · needs ${missing(r).join(", ")}` : `${r.id} · ${words(r.trust_level)}`}
      gets={r.kind === "statistics" ? "Gets only counts, with a little noise" : "Gets individual records, protected"} stats={r.kind === "statistics"}
      onClick={() => makePlan({ scenario_id: r.id }, r.id)} />
  );
  return (
    <>
      <PageHead title="Who gets the data, and what will they see?" lede="Pick the receiver. The tool decides how each column is shared and shows you the result before anything leaves." />
      <Guide steps={["Pick who gets the data", "Check what they will receive", "Change anything that looks wrong, then continue"]} done={[!!plan, !!plan, false]} />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,240px),1fr))] gap-3">
        {fitting.map(r => card(r))}
        <ReceiverCard icon="✏️" title="Someone else" text={fitting.length ? "Describe who they are and tick what they need." : "No ready-made receiver fits this data: describe who gets it and tick what they need."}
          gets="You choose the columns" selected={choice === "custom"} onClick={() => setCustom(true)} />
      </div>
      {other.length > 0 && (
        <details className="rounded-xl border bg-card p-3">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground">Receivers made for other data ({other.length}): they ask for tables this dataset does not have</summary>
          <div className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(min(100%,240px),1fr))] gap-3">{other.map(r => card(r, true))}</div>
        </details>
      )}
      {busy && !plan && <Spinner />}
      {plan && <PlanResult />}
      {custom && <CustomReceiver onClose={() => setCustom(false)} />}
    </>
  );
}

function ReceiverCard({ icon, title, text, gets, stats, selected, onClick, disabled = false, note }: { icon: string; title: string; text: string; gets: string; stats?: boolean; selected: boolean; onClick: () => void; disabled?: boolean; note?: string }) {
  return (
    <button onClick={onClick} aria-pressed={selected} disabled={disabled} title={disabled ? note : undefined}
      className={cn("flex flex-col gap-2 rounded-xl border bg-card p-4 text-left shadow-sm transition-colors hover:border-input disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border", selected && "border-safe ring-1 ring-safe")}>
      <span className="text-[26px] leading-none" aria-hidden>{icon}</span><b>{title}</b>
      <span className="text-sm text-muted-foreground">{text}</span>
      {note && <span className={cn("font-mono text-[11px]", disabled ? "text-warn" : "text-muted-foreground")}>{note}</span>}
      <span className={cn("mt-auto border-t border-dashed pt-2 text-[12.5px] font-semibold", stats ? "text-ok" : "text-safe")}>{gets}</span>
    </button>
  );
}

function PlanResult() {
  const view = useApp(s => s.plan!), P = view.plan, compare = useApp(s => s.compare), busy = useApp(s => s.busy === "compare");
  const reviews = view.reviews.length;
  return (
    <>
      {P.actions.length > 0 && <ExampleRecord />}
      <ProtectionLevel />
      {reviews > 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-warn/45 bg-warn-soft px-4 py-3 text-sm">
          <AlertTriangle className="size-4 text-warn" />
          <span><b>{plural(reviews, "column")} need{reviews === 1 ? "s" : ""} a decision</b> — open “Adjust columns” below.</span>
        </div>
      )}
      {P.aggregates.length > 0 && <CountsBoard />}
      {P.actions.length > 0 && (
        <details className="rounded-2xl border bg-card px-5 py-3" open={reviews > 0}>
          <summary className="cursor-pointer font-medium text-muted-foreground">Adjust columns{reviews > 0 ? ` (${reviews} need a decision)` : ""}</summary>
          <div className="mt-3"><Board /></div>
        </details>
      )}
      <details className="rounded-2xl border bg-card px-5 py-3">
        <summary className="cursor-pointer font-medium text-muted-foreground">Plan versions</summary>
        <div className="mt-3"><PlanVersionsPanel /></div>
      </details>
      <details className="rounded-2xl border bg-card px-5 py-3" onToggle={e => (e.target as HTMLDetailsElement).open && !compare && loadCompare()}>
        <summary className="cursor-pointer font-medium text-muted-foreground">Compare with other receivers</summary>
        <div className="mt-3 flex flex-col gap-3">
          {busy && <Spinner />}
          {compare && compare.left_out.length > 0 && (
            <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer">{plural(compare.left_out.length, "receiver")} left out: made for other data or asking for what this data does not have</summary>
              <ul className="mt-2 flex flex-col gap-1 pl-4">{compare.left_out.map(x => <li key={x.id} className="list-disc"><b className="font-medium text-foreground">{x.recipient}</b> ({x.id}): {x.reason}</li>)}</ul>
            </details>
          )}
          {compare && <TableWrap><table className="w-full border-collapse">
            <thead><tr><Th>Column</Th>{compare.receivers.map(r => <Th key={r.id}>{r.recipient}</Th>)}</tr></thead>
            <tbody>{compare.rows.filter(r => compare.receivers.some(x => r[x.id] !== "withheld")).map(r => (
              <tr key={`${r.table}.${r.column}`}><Td className="font-mono">{r.table}.{r.column}</Td>{compare.receivers.map(x => <Td key={x.id}><Badge variant={techniqueTone(r[x.id])}>{r[x.id]}</Badge></Td>)}</tr>
            ))}</tbody></table></TableWrap>}
        </div>
      </details>
    </>
  );
}

/** How each column is shared: one lane per protection, a chip per column; a click explains and offers the others. */
function Board() {
  const view = useApp(s => s.plan!), P = view.plan, reviews = new Set(view.reviews), tables = planTables(P);
  const [change, setChange] = useState<Action | null>(null), [openLanes, setOpenLanes] = useState<Record<string, boolean>>({});
  const flagged = (t: string) => P.actions.some(a => a.table === t && reviews.has(`${a.table}.${a.column}`));
  return (
    <Section eyebrow={`What ${view.scenario?.recipient ?? P.scenario_id} will receive`} title="How each column is shared"
      right={<div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">{LANES.map(l => <span key={l.technique}>{l.icon} {l.name}</span>)}</div>}>
      <Tabs defaultValue="board">
      <TabsList><TabsTrigger value="board"><LayoutGrid className="size-4" /> Board</TabsTrigger><TabsTrigger value="yaml"><FileCode2 className="size-4" /> YAML</TabsTrigger></TabsList>
      <TabsContent value="yaml"><PlanYaml /></TabsContent>
      <TabsContent value="board" className="flex flex-col gap-4">
      {view.reviews.length > 0 && <div className="flex items-center gap-2 rounded-xl border border-warn/45 bg-warn-soft px-4 py-3 text-sm"><AlertTriangle className="size-4 text-warn" />
        <span><b>{plural(view.reviews.length, "column")} need{view.reviews.length === 1 ? "s" : ""} a person's decision</b>: click {view.reviews.length === 1 ? "it" : "them"} below and choose.</span></div>}
      <Accordion type="multiple" defaultValue={tables.filter((t, i) => flagged(t) || i === 0)} className="flex flex-col gap-2">
        {tables.map(t => {
          const acts = P.actions.filter(a => a.table === t), shared = acts.filter(a => a.technique !== "drop").length;
          return (
            <AccordionItem key={t} value={t}>
              <AccordionTrigger right={`${shared} of ${acts.length} columns shared`}><b className="font-mono">{t}</b>{flagged(t) && <Badge variant="warn">⚠ needs a decision</Badge>}</AccordionTrigger>
              <AccordionContent>
                <div className="grid items-start gap-2.5 sm:grid-cols-2 xl:grid-cols-5">
                  {LANES.map(l => {
                    const inLane = acts.filter(a => a.technique === l.technique), key = t + l.technique, all = openLanes[key];
                    return (
                      <div key={l.technique} className={cn("flex min-h-[92px] flex-wrap content-start gap-1.5 rounded-xl border border-t-[3px] bg-muted p-2.5",
                        l.technique === "drop" ? "border-t-risk" : l.technique === "keep" ? "border-t-muted-foreground" : "border-t-safe")}>
                        <div className="mb-0.5 flex basis-full items-center gap-1.5 text-[13px] font-semibold"><span>{l.icon}</span>{l.name}<b className="ml-auto font-mono text-xs text-muted-foreground">{inLane.length}</b></div>
                        {(all ? inLane : inLane.slice(0, LANE_SHOWN)).map(a => {
                          const review = reviews.has(`${a.table}.${a.column}`);
                          return <button key={a.column} title={a.reason} onClick={() => setChange(a)}
                            className={cn("max-w-full truncate rounded-lg border bg-card px-2 py-1 font-mono text-[12.5px] hover:border-foreground",
                              l.technique === "drop" && "text-muted-foreground line-through decoration-risk/60", review && "border-warn bg-warn-soft font-semibold text-foreground no-underline")}>{review && "⚠ "}{a.column}</button>;
                        })}
                        {inLane.length > LANE_SHOWN && !all && <button onClick={() => setOpenLanes({ ...openLanes, [key]: true })} className="rounded-lg border border-dashed px-2 py-1 text-[12.5px] text-safe">+{inLane.length - LANE_SHOWN} more</button>}
                        {!inLane.length && <span className="text-sm text-muted-foreground">none</span>}
                      </div>
                    );
                  })}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
        <StaysHereTables tables={view.withheld_tables} reason="This receiver's request does not include this table, so all of it stays on this computer." />
      </Accordion>
      <p className="text-sm text-muted-foreground">Click any column to see why, and to change how it is shared. Tables marked "not shared" stay here entirely.</p>
      </TabsContent>
      </Tabs>
      {change && <ChangeDialog action={change} onClose={() => setChange(null)} />}
    </Section>
  );
}

/** Tables the plan does not share, listed with the shared ones so the plan always shows every table of the dataset. */
function StaysHereTables({ tables, reason }: { tables: string[]; reason: string }) {
  const columns = useApp(s => s.scan!.detections.columns);
  return <>{tables.map(t => {
    const cols = columns.filter(c => c.table === t);
    return (
      <AccordionItem key={t} value={`stays:${t}`} className="border-dashed bg-muted/40">
        <AccordionTrigger right={`0 of ${cols.length} columns shared`}><b className="font-mono">{t}</b><Badge>🏠 not shared</Badge></AccordionTrigger>
        <AccordionContent>
          <p className="text-sm text-muted-foreground">{reason}</p>
          {/* the same lane box as the shared tables, with every column in "Stays here" */}
          <div className="flex min-h-[92px] flex-wrap content-start gap-1.5 rounded-xl border border-t-[3px] border-t-input bg-muted p-2.5">
            <div className="mb-0.5 flex basis-full items-center gap-1.5 text-[13px] font-semibold"><span>🏠</span>Stays here<b className="ml-auto font-mono text-xs text-muted-foreground">{cols.length}</b></div>
            {cols.map(c => <span key={c.column} className="max-w-full truncate rounded-lg border bg-card px-2 py-1 font-mono text-[12.5px] text-muted-foreground">{c.column}</span>)}
          </div>
        </AccordionContent>
      </AccordionItem>
    );
  })}</>;
}

/** The ways a column can be shared, given what it holds. */
function optionsFor(a: Action, c?: Column): [string, Record<string, unknown>][] {
  const opts: [string, Record<string, unknown>][] = [["keep", {}], ["drop", {}], ["pseudonymise", { length: 16 }]];
  const sub = c?.subtype ?? "";
  if (["TIMESTAMP", "DATE"].includes(sub)) TIME_UNITS.forEach(u => opts.push([`generalise:${u}`, { to: "time", unit: u }]));
  if (sub === "BIRTH_DATE") opts.push(["generalise:age_band", { ...a.params, to: "age_band", width: 10, top: 80, rename_to: "age" }]);
  if (["DIAGNOSIS_CODE", "POSTCODE"].includes(sub)) opts.push(["generalise:truncate 3", { to: "truncate", length: 3 }]);
  if (c?.privacy_role === "free_text") opts.push(["redact_text", a.technique === "redact_text" ? a.params : {}]);
  const now = current(a);
  if (!opts.some(o => o[0] === now)) opts.push([now, a.params]);
  return opts;
}
const current = (a: Action) => a.technique === "generalise"
  ? `generalise:${a.params.to === "time" ? a.params.unit : a.params.to === "truncate" ? "truncate 3" : a.params.to}` : a.technique;

function ChangeDialog({ action, onClose }: { action: Action; onClose: () => void }) {
  const view = useApp(s => s.plan!), c = useApp(s => s.scan!.detections.columns.find(d => d.table === action.table && d.column === action.column));
  const ex = useApp(s => s.example?.tables.find(x => x.table === action.table)?.rows[0]), busy = useApp(s => s.busy === "plan");
  const a = view.plan.actions.find(x => x.table === action.table && x.column === action.column) ?? action, review = view.reviews.includes(`${a.table}.${a.column}`);
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle className="font-mono">{a.table}.{a.column}</DialogTitle></DialogHeader>
        <DialogBody>
          <p><b>What it is:</b> {ROLE_LABEL[c?.privacy_role ?? ""]}{ex && <> · for example <span className="font-mono">{clip(text(ex.raw[a.column]), 50)}</span></>}</p>
          {review ? <>
            <div className="flex items-start gap-2 rounded-xl border border-warn/45 bg-warn-soft px-4 py-3 text-sm"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" />The tool was not sure what this column holds, so a person should decide how it is shared.</div>
            <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Details</summary>{a.reason.replace(/^REVIEW:?\s*/, "")}</details>
          </> : <p className="text-sm text-muted-foreground"><b>Why:</b> {a.reason}</p>}
          <div className="flex flex-col gap-2">
            {optionsFor(a, c).map(([key, params]) => {
              const l = laneOf(key.split(":")[0]), detail = key.includes(":") ? words(key.split(":")[1]) : "", on = key === current(a);
              return (
                <button key={key} onClick={() => changeColumn(a.table, a.column, key.split(":")[0], params)}
                  className={cn("flex items-center gap-3 rounded-xl border bg-card px-3.5 py-3 text-left hover:border-foreground", on && "border-safe bg-safe-soft ring-1 ring-safe")}>
                  <span className="w-7 text-center text-xl">{l.icon}</span>
                  <span className="flex flex-1 flex-col"><b>{l.name}{detail && `: ${detail}`}</b><span className="text-sm text-muted-foreground">{l.help}</span></span>
                  {on && <Badge variant="ok">now</Badge>}
                </button>
              );
            })}
          </div>
        </DialogBody>
        <DialogFooter>{busy && <Spinner />}<Button onClick={onClose}>Done</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CountsBoard() {
  const view = useApp(s => s.plan!), P = view.plan;
  return (
    <Section eyebrow={`What ${view.scenario?.recipient ?? P.scenario_id} will receive`} title="Only counts, never individual records">
      <Tabs defaultValue="board">
      <TabsList><TabsTrigger value="board"><LayoutGrid className="size-4" /> Board</TabsTrigger><TabsTrigger value="yaml"><FileCode2 className="size-4" /> YAML</TabsTrigger></TabsList>
      <TabsContent value="yaml"><PlanYaml /></TabsContent>
      <TabsContent value="board" className="flex flex-col gap-4">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,220px),1fr))] gap-3">
        {P.aggregates.map(a => (
          <div key={a.name} className="flex flex-col gap-1.5 rounded-xl border bg-muted p-4"><span className="text-2xl" aria-hidden>📊</span><b>{words(a.name)}</b>
            <span className="text-sm text-muted-foreground">Counted by {a.dimensions.map(d => words(d.name ?? d.column)).join(" and ")}, from <span className="font-mono">{a.table}</span></span></div>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">A little random noise is added to every number, so nobody can tell whether one particular person is in the data.{P.differential_privacy && ` Each person is counted at most ${P.differential_privacy.max_rows_per_unit} times.`}</p>
      <Accordion type="multiple" className="flex flex-col gap-2">
        <StaysHereTables tables={view.withheld_tables} reason="Not used for any of the counts, so all of it stays on this computer." />
      </Accordion>
      </TabsContent>
      </Tabs>
    </Section>
  );
}

/** The attacked person's record (or the first rows), now and as the receiver will get it. */
function ExampleRecord() {
  const E = useApp(s => s.example), P = useApp(s => s.plan!.plan), attackTable = useApp(s => s.scan?.attack?.before.table);
  const [tableName, setTable] = useState<string>(), [row, setRow] = useState(0), role = useRole();
  if (!E) return <Section title="One record, now and as they will see it"><span className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner /> Preparing an example…</span></Section>;
  const T = E.tables.find(x => x.table === tableName) ?? E.tables[0];
  if (!T?.rows.length) return null;
  const i = Math.min(row, T.rows.length - 1), r = T.rows[i];
  const techOf = (c: string) => P.actions.find(x => x.table === T.table && x.column === c)?.technique ?? "drop";
  const order = (c: string) => LANES.findIndex(l => l.technique === techOf(c));
  return (
    <Section eyebrow="Example" title="One record, now and as they will see it" right={
      <div className="flex flex-wrap items-center gap-2">
        {E.tables.length > 1 && <div className="flex gap-1">{E.tables.map(x => <Button key={x.table} size="sm" variant={x.table === T.table ? "default" : "outline"} onClick={() => { setTable(x.table); setRow(0); }}>{x.table}</Button>)}</div>}
        <Button size="icon-sm" variant="outline" aria-label="Previous record" onClick={() => setRow((i + T.rows.length - 1) % T.rows.length)}><ArrowLeft /></Button>
        <span className="text-sm text-muted-foreground">{i + 1} of {T.rows.length}</span>
        <Button size="icon-sm" variant="outline" aria-label="Next record" onClick={() => setRow((i + 1) % T.rows.length)}><ArrowRight /></Button>
      </div>}>
      {i === 0 && attackTable === T.table && <p className="-mt-2 text-sm text-muted-foreground">This is the person from the attack on the risk scan.</p>}
      <TableWrap>
        <table className="w-full border-collapse max-sm:block">
          <thead className="max-sm:hidden"><tr><Th>Column</Th><Th>Now (stays here)</Th><Th /><Th>They will see</Th><Th>How</Th></tr></thead>
          <tbody className="max-sm:block">{Object.keys(r.raw).sort((x, y) => order(x) - order(y)).map(c => {
            const tech = techOf(c), l = laneOf(tech), after = r.after[T.renamed[c] ?? c];
            return (
              <tr key={c} className="max-sm:grid max-sm:grid-cols-[1fr_auto] max-sm:gap-x-3 max-sm:border-b max-sm:px-3 max-sm:py-2.5">
                <Td className="font-mono max-sm:border-0 max-sm:p-0 max-sm:font-semibold">{c}</Td>
                <Td className={cn(ROLE_TONE[role(T.table, c)], "max-sm:col-span-2 max-sm:row-start-2 max-sm:border-0 max-sm:p-0")}>{clip(text(r.raw[c]), 60)}</Td>
                <Td className="text-muted-foreground max-sm:hidden">→</Td>
                <Td className={cn("font-semibold max-sm:col-span-2 max-sm:row-start-3 max-sm:border-0 max-sm:p-0 max-sm:before:content-['→_']",
                  tech === "keep" && "font-medium text-muted-foreground", ["generalise", "pseudonymise", "redact_text"].includes(tech) && "text-safe", tech === "pseudonymise" && "font-mono text-xs")}>
                  {tech === "drop" ? <span className="font-mono text-xs text-risk">removed</span> : after}</Td>
                <Td className="text-sm text-muted-foreground max-sm:col-start-2 max-sm:row-start-1 max-sm:border-0 max-sm:p-0 max-sm:text-right">{l.icon} {l.name}</Td>
              </tr>
            );
          })}</tbody>
        </table>
      </TableWrap>
      <p className="text-sm text-muted-foreground">Some values may also be blanked in the release, so that every person has look-alikes.</p>
    </Section>
  );
}

/** k in plain words: how many people each person hides among, and what that costs in detail. */
function ProtectionLevel() {
  const T = useApp(s => s.tradeoff), P = useApp(s => s.plan!.plan), busy = useApp(s => s.busy === "tradeoff");
  const [pick, setPick] = useState<number | null>(null);
  if (!P.actions.length && !P.aggregates.length) return null;
  if (!T) return <Section title="How strong is the protection?"><span className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner /> Working it out on your data…</span></Section>;
  if (T.k.length) {
    const cur = Math.max(T.k.findIndex(p => p.current), 0), i = pick != null && pick < T.k.length ? pick : cur, p = T.k[i];
    return (
      <Section eyebrow="Protection level" title={<>Each person hides among at least <span className="text-safe">{p.k}</span> people</>}
        right={i !== cur ? <Button disabled={busy} onClick={async () => { await setK(p.k); setPick(null); }}>{busy && <Spinner className="text-current" />}Use this level</Button> : <Badge variant="ok">current plan</Badge>}>
        <div className="flex flex-col gap-1">
          <div className="flex justify-between gap-3 text-[12.5px] text-muted-foreground"><span>← Weaker: more details kept</span><span>Stronger: harder to find anyone →</span></div>
          <Slider min={0} max={T.k.length - 1} step={1} value={[i]} onValueChange={([v]) => setPick(v)} aria-label="Protection level" />
          <div className="flex justify-between px-0.5 font-mono text-xs text-muted-foreground">{T.k.map((x, j) => <span key={x.k} className={cn("w-4 text-center", j === cur && "font-bold text-safe")}>{x.k}</span>)}</div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Gauge tone="risk" label="Chance an outsider picks the right person" value={pct(p.guess_chance, 1)} meter={Math.max(0.01, p.guess_chance)} />
          <Gauge tone="safe" label="Details kept for the receiver" value={pct(p.cells_kept)} meter={p.cells_kept} />
        </div>
        <p className="text-sm text-muted-foreground">Stronger protection blanks more values. Computed on your data; nothing is released.</p>
      </Section>
    );
  }
  const cur = Math.max(T.epsilon.findIndex(x => x.current), 0), i = pick ?? cur, p = T.epsilon[i];
  if (!p) return null;
  return (
    <Section eyebrow="Noise level" title={<>Published numbers are off by about <span className="text-safe">{pct(p.mean_error)}</span> on average</>}>
      <div className="flex flex-col gap-1">
        <div className="flex justify-between gap-3 text-[12.5px] text-muted-foreground"><span>← More noise, more privacy</span><span>Less noise, more exact →</span></div>
        <Slider min={0} max={T.epsilon.length - 1} step={1} value={[i]} onValueChange={([v]) => setPick(v)} aria-label="Noise level" />
      </div>
      <p className="text-sm text-muted-foreground">Privacy budget ε {p.epsilon}{p.current ? " (the receiver's agreement)" : ""}. The budget is set by the agreement with the receiver; this shows what a different budget would mean.</p>
    </Section>
  );
}
const Gauge = ({ tone, label, value, meter }: { tone: "risk" | "safe"; label: string; value: string; meter: number }) => (
  <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 gap-y-2 rounded-xl border bg-muted p-3.5">
    <span className="text-[13.5px] text-muted-foreground">{label}</span><b className={cn("big-number text-[26px]", tone === "risk" ? "text-risk" : "text-safe")}>{value}</b>
    <Meter className="col-span-2 h-2.5" value={meter} tone={tone} />
  </div>
);

/** A receiver that is not a preset: who, why, how far trusted, and which columns (or, for the public, which counts). */
