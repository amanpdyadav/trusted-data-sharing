// Step 4: check what leaves, then sign it off. Tables on the left, their fields and what happens to each on the
// right; then plain checks and a name. Nothing is shared until a named person approves.
import { CheckCircle2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Guide, PageHead, Section } from "@/components/common";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Input, Label } from "@/components/ui/form";
import { Spinner } from "@/components/ui/misc";
import type { Plan } from "@/lib/api";
import { plural } from "@/lib/format";
import { laneOf } from "@/lib/lanes";
import { approve, go, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";
import { planTables } from "@/steps/PlanStep";

type Kind = "shared" | "counts" | "stays";
type Field = { column: string; cls: string; icon: string; fate: string; why: string };
type TableFate = { table: string; kind: Kind; fields: Field[]; out: number };
const ORDER = ["keep", "generalise", "pseudonymise", "redact_text", "statistics", "drop", "stays"];

/** Every table and field, and what the plan does with it. */
function tableFates(P: Plan, columns: { table: string; column: string }[]): TableFate[] {
  const shared = new Set(planTables(P));
  const counted = new Map(P.aggregates.flatMap(g => g.dimensions.map(d => [`${g.table}.${d.column}`, g.name] as const)));
  const names = [...new Set(columns.map(c => c.table))];
  return names.map(table => {
    const cols = columns.filter(c => c.table === table).map(c => c.column);
    let kind: Kind, fields: Field[];
    if (shared.has(table)) {
      kind = "shared";
      fields = cols.map(column => {
        const a = P.actions.find(x => x.table === table && x.column === column), tech = a?.technique ?? "drop", l = laneOf(tech), as = a?.params?.rename_to;
        return { column, cls: tech, icon: l.icon, fate: l.name + (as && tech !== "drop" ? ` → ${as}` : ""), why: a?.reason ?? "" };
      });
    } else if (P.aggregates.some(g => g.table === table)) {
      kind = "counts";
      fields = cols.map(column => counted.has(`${table}.${column}`)
        ? { column, cls: "statistics", icon: "📊", fate: "Counted only", why: `used to count ${counted.get(`${table}.${column}`)}` }
        : { column, cls: "stays", icon: "🏠", fate: "Stays here", why: "" });
    } else {
      kind = "stays";
      fields = cols.map(column => ({ column, cls: "stays", icon: "🏠", fate: "Stays here", why: "the table is not shared" }));
    }
    fields.sort((x, y) => ORDER.indexOf(x.cls) - ORDER.indexOf(y.cls));  // what leaves first
    return { table, kind, fields, out: fields.filter(f => f.cls !== "drop" && f.cls !== "stays").length };
  }).sort((x, y) => ["shared", "counts", "stays"].indexOf(x.kind) - ["shared", "counts", "stays"].indexOf(y.kind) || x.table.localeCompare(y.table));
}

const FATE_TONE: Record<string, string> = {
  keep: "text-muted-foreground", generalise: "text-safe", pseudonymise: "text-safe", redact_text: "text-safe", statistics: "text-ok", drop: "text-risk", stays: "text-muted-foreground font-medium",
};

export function Approve() {
  const view = useApp(s => s.plan!), P = view.plan, recipient = view.scenario?.recipient ?? P.scenario_id;
  const [again, setAgain] = useState(false), signed = P.approved && !again;
  return (
    <>
      <PageHead title="Check what leaves, then sign it off" lede="Nothing is shared until a named person approves. Your name is written into the plan and into the release." />
      <Guide steps={["Check what leaves and what stays", "Tick the checks", "Type your name and approve"]} done={[signed, signed, signed]} />
      <LeavesStays recipient={recipient} />
      {signed ? (
        <Card className="flex flex-wrap items-center justify-between gap-4 border-ok/40 bg-ok-soft/40 p-5">
          <div className="flex items-center gap-3"><CheckCircle2 className="size-8 text-ok" />
            <div><span className="eyebrow text-ok">Approved</span><h2 className="text-xl">Signed off by {P.approved_by}</h2><p className="text-sm text-muted-foreground">Recorded in the plan and in every release.</p></div></div>
          <div className="flex gap-2"><Button variant="outline" onClick={() => setAgain(true)}>Change approval</Button><Button size="lg" onClick={() => go("release")}>Create the release →</Button></div>
        </Card>
      ) : <SignOff recipient={recipient} onDone={() => setAgain(false)} />}
    </>
  );
}

function LeavesStays({ recipient }: { recipient: string }) {
  const view = useApp(s => s.plan!), columns = useApp(s => s.scan!.detections.columns);
  const all = useMemo(() => tableFates(view.plan, columns), [view, columns]);
  const [selected, setSelected] = useState<Set<string> | null>(null), [query, setQuery] = useState(""), [kind, setKind] = useState<"all" | "shared" | "stays">("all");
  const sel = selected ?? new Set(all.map(x => x.table));
  const visible = all.filter(x => (kind === "all" || (kind === "shared" ? x.kind !== "stays" : x.kind === "stays")) && x.table.toLowerCase().includes(query.toLowerCase()));
  const leaving = all.filter(x => x.kind !== "stays"), staying = all.filter(x => x.kind === "stays");
  const fieldsOut = leaving.reduce((n, x) => n + x.out, 0), removed = leaving.reduce((n, x) => n + x.fields.length - x.out, 0);
  const shown = all.filter(x => sel.has(x.table));
  const badge = (x: TableFate) => x.kind === "shared" ? <Badge variant="safe">{x.out} of {x.fields.length} shared</Badge> : x.kind === "counts" ? <Badge variant="ok">counts only</Badge> : <Badge>🏠 0 of {x.fields.length} shared</Badge>;
  const toggle = (t: string, on: boolean) => { const s = new Set(sel); on ? s.add(t) : s.delete(t); setSelected(s); };
  const [openTables, setOpenTables] = useState<string[] | null>(null);
  const open = openTables ?? shown.filter(x => x.kind !== "stays").map(x => x.table);
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="flex flex-col gap-1 border-l-[5px] border-l-safe p-4"><span className="eyebrow text-safe">↗ Leaves your organisation</span>
          <b className="font-display text-[22px] font-extrabold">{plural(leaving.length, "table")}{view.plan.aggregates.length && !planTables(view.plan).length ? " as counts" : ""}, {plural(fieldsOut, "field")}</b>
          <span className="text-sm text-muted-foreground">to {recipient}{view.scenario?.purpose ? ` · ${view.scenario.purpose}` : ""}</span></Card>
        <Card className="flex flex-col gap-1 border-l-[5px] border-l-ok p-4"><span className="eyebrow text-ok">🏠 Stays on this computer</span>
          <b className="font-display text-[22px] font-extrabold">{plural(staying.length, "table")} not shared{removed ? `, ${plural(removed, "field")} removed` : ""}</b>
          <span className="text-sm text-muted-foreground">plus the original data, the row maps and the secret key</span></Card>
      </div>
      <div className="grid items-start gap-4 md:grid-cols-[minmax(240px,320px)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-2.5 p-4 md:sticky md:top-24 md:max-h-[calc(100vh-120px)]">
          <div className="flex items-center justify-between"><h3 className="font-semibold">Tables</h3><span className="text-sm text-muted-foreground">{sel.size} of {all.length} selected</span></div>
          {all.length > 8 && <div className="relative"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input className="pl-8" placeholder="Search tables…" value={query} onChange={e => setQuery(e.target.value)} /></div>}
          <div className="flex gap-1">{([["all", "All"], ["shared", "Shared"], ["stays", "Not shared"]] as const).map(([k, l]) =>
            <Button key={k} size="sm" variant={kind === k ? "default" : "outline"} className="rounded-full" onClick={() => setKind(k)}>{l}</Button>)}</div>
          <div className="flex gap-2 text-sm"><Button variant="link" onClick={() => setSelected(null)}>Select all</Button>·<Button variant="link" onClick={() => setSelected(new Set())}>None</Button></div>
          <div className="-mx-1.5 flex min-h-0 flex-col gap-1 overflow-auto px-1.5 max-md:max-h-64">
            {visible.map(x => (
              <label key={x.table} className={cn("grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-0.5 rounded-lg border border-transparent px-2.5 py-2 text-[13px] hover:bg-muted", sel.has(x.table) && "border-safe/35 bg-safe-soft")}>
                <Checkbox className="row-span-2" checked={sel.has(x.table)} onCheckedChange={v => toggle(x.table, !!v)} />
                <span className="truncate font-mono">{x.table}</span><span>{badge(x)}</span>
              </label>
            ))}
            {!visible.length && <p className="text-sm text-muted-foreground">No table matches.</p>}
          </div>
        </Card>
        <div className="flex min-w-0 flex-col gap-3">
          {shown.length ? <>
            <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{plural(shown.length, "table")} shown</span>
              <span><Button variant="link" onClick={() => setOpenTables(shown.map(x => x.table))}>Expand all</Button> · <Button variant="link" onClick={() => setOpenTables([])}>Collapse all</Button></span></div>
            <Accordion type="multiple" value={open} onValueChange={setOpenTables} className="flex flex-col gap-2.5">
              {shown.map(x => (
                <AccordionItem key={x.table} value={x.table} className={cn("border-t-4 shadow-sm", x.kind === "shared" ? "border-t-safe" : x.kind === "counts" ? "border-t-ok" : "border-t-input")}>
                  <AccordionTrigger right={badge(x)}><b className="font-mono">{x.table}</b></AccordionTrigger>
                  <AccordionContent>
                    {x.kind === "stays" && <p className="text-sm text-muted-foreground">This table is not part of the request, so all {plural(x.fields.length, "field")} stay here.</p>}
                    {(
                      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,280px),1fr))] gap-1.5">
                        {x.fields.map(f => (
                          <div key={f.column} title={f.why} className={cn("flex min-w-0 items-center justify-between gap-2.5 rounded-lg border bg-muted px-2.5 py-2 text-[13px]", f.cls === "drop" && "opacity-75")}>
                            <span className={cn("truncate font-mono", f.cls === "drop" && "line-through decoration-risk/55")}>{f.column}</span>
                            <span className={cn("whitespace-nowrap text-[12.5px] font-semibold", FATE_TONE[f.cls])}>{f.icon} {f.fate}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </> : <Card className="p-5 text-sm text-muted-foreground">Select one or more tables on the left to see their fields.</Card>}
        </div>
      </div>
    </>
  );
}

function SignOff({ recipient, onDone }: { recipient: string; onDone: () => void }) {
  const view = useApp(s => s.plan!), busy = useApp(s => s.busy === "approve"), reviews = view.reviews;
  const [checks, setChecks] = useState({ need: false, review: reviews.length === 0, allowed: false }), [name, setName] = useState("");
  const ready = checks.need && checks.review && checks.allowed && name.trim().length > 1;
  const purpose = view.scenario?.purpose ? view.scenario.purpose.toLowerCase() : "the agreed purpose";
  const check = (key: keyof typeof checks, body: React.ReactNode) => (
    <label className={cn("flex cursor-pointer items-start gap-3 rounded-xl border bg-muted px-4 py-3 text-[14.5px]", checks[key] && "border-ok bg-ok-soft")}>
      <Checkbox className="mt-0.5" checked={checks[key]} onCheckedChange={v => setChecks({ ...checks, [key]: !!v })} /><span>{body}</span>
    </label>
  );
  return (
    <Section eyebrow="Sign off" title="Before you approve" className="border-safe/45">
      <div id="signoff" className="flex flex-col gap-2.5">
        {check("need", <><b>The receiver needs this data</b> for {purpose}.</>)}
        {reviews.length > 0 && check("review", <><b>I checked the {plural(reviews.length, "column")} the tool could not decide:</b> <span className="font-mono">{reviews.join(", ")}</span>{" "}
          <Button size="sm" variant="outline" onClick={e => { e.preventDefault(); go("plan"); }}>Look again</Button></>)}
        {check("allowed", <><b>I am allowed to approve</b> sharing this data with {recipient}.</>)}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-[260px] flex-1 flex-col gap-1.5"><Label htmlFor="approver">Your full name</Label><Input id="approver" value={name} placeholder="e.g. Maria Virtanen" onChange={e => setName(e.target.value)} /></div>
        <Button size="lg" disabled={!ready || busy} onClick={async () => { if (await approve(name.trim(), reviews.length > 0)) onDone(); }}>{busy && <Spinner className="text-current" />}Approve and continue</Button>
      </div>
    </Section>
  );
}
