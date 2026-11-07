// Columns that came without a real name: a note above the table, and a dialog to name them.
// Only unnamed columns appear here; columns with a name are never renamed. Nothing changes until "Use these names".
import { RefreshCw, Sparkles, Tags } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox, Input } from "@/components/ui/form";
import { Spinner, Tip } from "@/components/ui/misc";
import type { NameSource, NameSuggestion, TableOverview } from "@/lib/api";
import { clip, pct, plural } from "@/lib/format";
import { saveNames, setHeaderless, suggestNames, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";

const NAME = /^[a-z][a-z0-9_]{0,62}$/;
const UNNAMED = /^\s*$|^unnamed: ?\d+$|^(?:c|col|column|field|var|v|x|f)[ _-]?\d{1,4}$|^x$/i;  // same rule as columns.py
const SOURCE_LABEL: Record<NameSuggestion["source"], string> = { rules: "format check", ai: "local AI", person: "you", none: "no suggestion" };

/** The note above a table with unnamed columns (or a first row that looks like data). */
export function NamingNote({ table, frozen }: { table: TableOverview; frozen: boolean }) {
  const ai = useApp(s => s.session?.ai.on ?? false), busy = useApp(s => s.busy);
  const [open, setOpen] = useState(false);
  const { unnamed, headerless, headerless_guess } = table.naming;
  const left = unnamed.filter(u => !u.name).length;
  if (!unnamed.length && !headerless_guess) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-warn/40 bg-warn-soft px-4 py-3 text-sm">
      <Tags className="size-4 shrink-0 text-warn" />
      <span className="min-w-[220px] flex-1">
        {headerless_guess && !unnamed.length
          ? <>The first row of <b>{table.name}</b> looks like data, not column names.</>
          : left
            ? <><b>{left} of {table.columns.length}</b> columns in {table.name} have no real name{headerless ? " (the file has no header row)" : ""}. Names make the scan and the plan easier to check; columns that have a name are left as they are.</>
            : <>All {plural(unnamed.length, "unnamed column")} in {table.name} now have names. The release uses them; the manifest keeps the original headers.</>}
      </span>
      {!frozen && (headerless_guess || headerless) && (
        <Button size="sm" variant="outline" disabled={busy === "headerless"} onClick={() => setHeaderless(table.name, !headerless)}>
          {busy === "headerless" && <Spinner className="text-current" />}{headerless ? "The first row is column names" : "Read the first row as data"}
        </Button>
      )}
      {!frozen && unnamed.length > 0 && (ai
        ? <Button size="sm" onClick={() => setOpen(true)}><Sparkles /> Suggest names</Button>
        : <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Tags /> Name the columns</Button>)}
      {open && <NamesDialog table={table} ai={ai} open={open} onOpenChange={setOpen} />}
    </div>
  );
}

type Row = { original: string; value: string; keep: boolean; existing: { name: string; by: NameSource } | null; suggestion: NameSuggestion | null; avoid: string[] };

function NamesDialog({ table, ai, open, onOpenChange }: { table: TableOverview; ai: boolean; open: boolean; onOpenChange: (o: boolean) => void }) {
  const busy = useApp(s => s.busy);
  const [rows, setRows] = useState<Row[]>([]), [note, setNote] = useState<string | null>(null), [loading, setLoading] = useState(true);
  const unnamedNow = new Set(table.naming.unnamed.map(u => u.name ?? u.original));
  const named = table.columns.filter(c => !unnamedNow.has(c));  // columns with a real name: never renamed, never reused

  useEffect(() => {
    if (!open) return;
    const start: Row[] = table.naming.unnamed.map(u => ({
      original: u.original, value: u.name ?? "", keep: false, suggestion: null, avoid: [],
      existing: u.name && u.suggested_by ? { name: u.name, by: u.suggested_by } : null,
    }));
    setRows(start); setLoading(true);
    suggestNames(table.name).then(r => {
      setLoading(false);
      if (!r) return;
      setNote(ai ? r.ai_error : null);  // with the AI off, the rules' names are all there is: no error to show
      const by = new Map(r.suggestions.map(x => [x.column, x]));
      setRows(rs => rs.map(row => {
        const sg = by.get(row.original) ?? null;
        return { ...row, suggestion: sg, value: row.value || (sg?.source !== "none" ? sg?.name ?? "" : "") };
      }));
    });
  }, [open, table, ai]);

  const again = async (row: Row) => {
    const avoid = [...row.avoid, row.suggestion?.name, row.value].filter((x): x is string => !!x);
    const r = await suggestNames(table.name, [row.original], { [row.original]: avoid });
    const sg = r?.suggestions[0];
    if (r?.ai_error) setNote(r.ai_error);
    if (sg) setRows(rs => rs.map(x => (x.original === row.original ? { ...x, suggestion: sg, avoid, value: sg.source !== "none" ? sg.name : x.value } : x)));
  };
  const update = (original: string, p: Partial<Row>) => setRows(rs => rs.map(x => (x.original === original ? { ...x, ...p } : x)));

  const chosen = rows.filter(r => !r.keep && r.value.trim());
  const problem = (r: Row): string | null => {
    const v = r.value.trim();
    if (r.keep || !v) return null;
    if (!NAME.test(v)) return "lower-case letters, digits and _, starting with a letter";
    if (UNNAMED.test(v)) return "say what the column holds";
    if (named.includes(v)) return `${table.name} already has a column called ${v}`;
    if (chosen.filter(x => x.value.trim() === v).length > 1) return "two columns would have this name";
    return null;
  };
  const errors = rows.filter(r => problem(r)).length;
  const save = async () => {
    const names = chosen.map(r => {
      const v = r.value.trim(), sg = r.suggestion;
      const by: NameSource = r.existing?.name === v ? r.existing.by : sg && sg.source !== "none" && sg.name === v ? sg.source : "person";
      return { original: r.original, name: v, suggested_by: by, meaning: sg && sg.name === v ? sg.meaning : "" };
    });
    if (await saveNames(table.name, names)) onOpenChange(false);
  };
  const scanned = useApp(s => !!s.scan);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide>
        <DialogHeader><DialogTitle>Name the columns of {table.name}</DialogTitle></DialogHeader>
        <DialogBody>
          <p className="text-sm text-muted-foreground">
            Only the {plural(rows.length, "column")} without a real name are listed; the others keep their names.
            {ai ? " Format checks name what they are sure of; the local AI suggests the rest from a short summary of each column (a few sample values, never the whole table)." : " Format checks name what they are sure of; type a name for the rest."}
            {" "}Change any name you disagree with, or keep the original header.
          </p>
          {note && <p className="rounded-lg border border-warn/40 bg-warn-soft px-3 py-2 text-sm">{note}</p>}
          {loading && <p className="flex items-center gap-2 text-sm"><Spinner /> {ai ? "Asking the format checks, then the local AI…" : "Running the format checks…"}</p>}
          <div className="flex flex-col divide-y rounded-xl border">
            {rows.map(r => {
              const sg = r.suggestion, err = problem(r);
              return (
                <div key={r.original} className={cn("grid gap-3 px-3 py-2.5 md:grid-cols-[90px_minmax(0,1.1fr)_minmax(0,1.3fr)_minmax(180px,1fr)]", r.keep && "opacity-60")}>
                  <div className="font-mono text-sm font-semibold">{r.original}</div>
                  <div className="flex min-w-0 flex-wrap gap-1 text-xs text-muted-foreground">
                    {(sg?.samples ?? []).slice(0, 4).map((v, i) => <span key={i} className="max-w-full truncate rounded bg-muted px-1.5 py-0.5 font-mono">{clip(v, 28)}</span>)}
                    {sg && !sg.samples.length && <span>empty in every row</span>}
                  </div>
                  <div className="flex min-w-0 flex-col gap-1 text-sm">
                    {sg && sg.source !== "none"
                      ? <>
                          <span className="flex flex-wrap items-center gap-1.5">
                            <b className="font-mono">{sg.name}</b>
                            <Badge variant={sg.source === "rules" ? "ok" : "safe"}>{SOURCE_LABEL[sg.source]}{sg.source === "ai" ? ` · ${pct(sg.confidence)}` : ""}</Badge>
                          </span>
                          {sg.meaning && <span className="text-xs text-muted-foreground">{sg.meaning}</span>}
                        </>
                      : <span className="text-xs text-muted-foreground">{loading ? "…" : "No suggestion: type a name"}</span>}
                  </div>
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-1.5">
                      <Input aria-label={`New name for ${r.original}`} value={r.value} disabled={r.keep} placeholder="name"
                        className={cn("h-8 font-mono text-sm", err && "border-risk")} onChange={e => update(r.original, { value: e.target.value })} />
                      {ai && !r.keep && (
                        <Tip text="Suggest another name for this column only">
                          <Button size="icon-sm" variant="ghost" aria-label={`Suggest again for ${r.original}`} disabled={!!busy} onClick={() => again(r)}>
                            {busy === `suggest:${r.original}` ? <Spinner /> : <RefreshCw />}
                          </Button>
                        </Tip>
                      )}
                    </div>
                    {err && <span className="text-xs text-risk">{err}</span>}
                    <label className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Checkbox checked={r.keep} onCheckedChange={c => update(r.original, { keep: c === true })} /> Keep “{r.original}”
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        </DialogBody>
        <DialogFooter className="items-center">
          <span className="mr-auto text-xs text-muted-foreground">{scanned ? "The scan and the plan start over with the new names." : "The scan will use these names."}</span>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={loading || busy === "names" || errors > 0}>{busy === "names" && <Spinner className="text-current" />}Use these names</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
