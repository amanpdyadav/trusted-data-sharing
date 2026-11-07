// Step 1: bring the data. Upload or pick an example, see what is inside, manage earlier datasets.
import { Copy, Lock, MoreHorizontal, Pencil, Plus, Search, Trash2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { NamingNote } from "@/components/ColumnNames";
import { Guide, PageHead, ProgressCard, Section, useRole, useShown } from "@/components/common";
import { ConfirmDialog, NameDialog } from "@/components/dialogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input, Label } from "@/components/ui/form";
import { TableWrap, Td, Th, Tip } from "@/components/ui/misc";
import type { SessionListItem } from "@/lib/api";
import { ROLE_TONE, clip, fmt, mb, pct, plural, when } from "@/lib/format";
import {
  addTables, deleteDataset, duplicateDataset, go, openSample, removeTable, renameDataset, reopen, runScan, uploadFiles, useApp,
} from "@/lib/store";
import { cn } from "@/lib/utils";

/** The top bar's "Choose files…" opens the same file picker as the drop zone. */
export const openPicker = () => document.getElementById("files")?.click();
const WORKSPACE_SHOWN = 6;  // newest first; the rest behind "Show all" or a search

export function DataStep() {
  const session = useApp(s => s.session), scan = useApp(s => s.scan), progress = useApp(s => s.progress);
  if (progress) return <><PageHead title="Bring the data you want to share" /><ProgressCard /></>;
  const guide = <Guide steps={["Upload your files or pick an example", "Look at what is inside", "Scan for risks"]} done={[!!session, !!session, !!scan]} />;
  if (session) return (
    <>
      {guide}
      <Ready />
      <Inside />
      <details className="group rounded-2xl border bg-card">
        <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 px-5 py-4 font-semibold">
          <span className="flex items-center gap-2"><Plus className="size-4 text-safe transition-transform group-open:rotate-45" /> Load different data or reopen earlier work</span>
          <span className="text-sm font-normal text-muted-foreground">{plural(useApp.getState().sessions.length, "dataset")} in your workspace</span>
        </summary>
        <div className="flex flex-col gap-5 px-5 pb-5"><Loaders /><Workspace /></div>
      </details>
    </>
  );
  return (
    <>
      <PageHead title="Bring the data you want to share" lede="Drop the tables as CSV files (or one ZIP), pick an example, or reopen earlier work. Files are copied into a local folder on this computer; nothing is uploaded anywhere." />
      {guide}
      <Loaders />
      <Workspace />
    </>
  );
}

function Loaders() {
  const cat = useApp(s => s.cat), samples = cat?.samples ?? [];  // select stable values; build arrays outside the selector
  const [name, setName] = useState("my-data"), [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Section title="Your files">
        <div className="flex flex-col gap-1.5"><Label htmlFor="dsname">Dataset name</Label><Input id="dsname" value={name} onChange={e => setName(e.target.value)} /></div>
        <button type="button" onClick={() => input.current?.click()}
          onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); uploadFiles(e.dataTransfer.files, name); }}
          className={cn("flex flex-col items-center gap-2.5 rounded-2xl border-2 border-dashed border-input bg-muted px-5 py-8 text-center transition-colors hover:border-safe hover:bg-safe-soft", over && "border-safe bg-safe-soft")}>
          <span className="grid size-11 place-items-center rounded-xl border bg-card text-safe"><Upload className="size-5" /></span>
          <b>Drop CSV or ZIP files here</b>
          <span className="text-sm text-muted-foreground">or click to choose. One file per table; the file name becomes the table name.</span>
        </button>
        <input ref={input} id="files" type="file" accept=".csv,.zip" multiple hidden onChange={e => e.target.files?.length && uploadFiles(e.target.files, name)} />
      </Section>
      <Section title="Or try an example" right={<span className="text-sm text-muted-foreground">synthetic TrustED data</span>}>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,210px),1fr))] gap-2.5">
          {samples.map(s => (
            <button key={s.name} onClick={() => openSample(s.name)} className="flex flex-col gap-1 rounded-xl border bg-card p-3.5 text-left shadow-sm transition-colors hover:border-input hover:bg-muted">
              <span className="text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">{s.tables.length} tables</span>
              <b>{s.name.replace(/_/g, " ")}</b>
              <span className="line-clamp-2 text-sm text-muted-foreground">{s.tables.join(", ")}</span>
            </button>
          ))}
          {!samples.length && <p className="text-sm text-muted-foreground">No sample folder found (set PETS_PACKAGE_ROOT).</p>}
        </div>
      </Section>
    </div>
  );
}

function Ready() {
  const session = useApp(s => s.session)!, scan = useApp(s => s.scan);
  const bytes = useApp(s => s.sessions.find(x => x.id === session.id)?.bytes);
  const [dialog, setDialog] = useState<"" | "rename" | "duplicate">("");
  const rows = session.tables.reduce((n, t) => n + t.rows, 0), cols = session.tables.reduce((n, t) => n + t.columns.length, 0);
  return (
    <Card className="flex flex-col gap-4 border-safe/40 bg-[radial-gradient(120%_160%_at_100%_0%,hsl(var(--safe)/0.08),transparent_55%)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow flex items-center gap-1.5 text-safe">{session.released ? <><Lock className="size-3.5" /> Released · data frozen</> : "Dataset ready"}</span>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[clamp(26px,3.4vw,40px)] leading-none">{session.name}</h1>
            <DatasetMenu item={{ id: session.id, name: session.name, released: session.released }} onRename={() => setDialog("rename")} onDuplicate={() => setDialog("duplicate")} hideDelete />
          </div>
        </div>
        <Button size="lg" onClick={() => (scan ? go("scan") : runScan())}>{scan ? "See the risk scan →" : "Scan for risks →"}</Button>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,140px),1fr))] gap-2.5">
        {[[fmt(session.tables.length), "tables"], [fmt(rows), "rows"], [fmt(cols), "columns"], ...(bytes ? [[`${mb(bytes)} MB`, "on this computer"]] : [])].map(([v, l]) => (
          <div key={l} className="flex flex-col gap-0.5 rounded-xl border bg-muted px-3.5 py-3"><b className="big-number text-[26px] leading-tight">{v}</b><span className="text-[12.5px] text-muted-foreground">{l}</span></div>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">Next, the scan reads every column, finds what identifies people and how the tables connect, and replays an attack on one person.</p>
      <NameDialog open={dialog === "rename"} onOpenChange={o => !o && setDialog("")} title="Rename the dataset" label="Name" initial={session.name}
        hint="Letters, digits, '-' and '_'; other characters become '_'." busyKey="rename" action="Save" onSubmit={n => renameDataset(session.id, n)} />
      <DuplicateDialog item={{ id: session.id, name: session.name, released: session.released, tables: session.tables.length }} open={dialog === "duplicate"} onOpenChange={o => !o && setDialog("")} />
    </Card>
  );
}

function Inside() {
  const session = useApp(s => s.session)!, scan = useApp(s => s.scan);
  const [current, setCurrent] = useState(session.tables[0]?.name), [removing, setRemoving] = useState(""), [dup, setDup] = useState(false);
  const shown = useShown(), role = useRole(), add = useRef<HTMLInputElement>(null);
  const t = session.tables.find(x => x.name === current) ?? session.tables[0];
  const frozen = session.released, removable = !frozen && session.tables.length > 1;
  return (
    <Section title="What is inside" right={!frozen && <><Button variant="outline" onClick={() => add.current?.click()}><Plus /> Add tables</Button>
      <input ref={add} type="file" accept=".csv,.zip" multiple hidden onChange={e => e.target.files?.length && addTables(e.target.files)} /></>}>
      <p className="-mt-2 text-sm text-muted-foreground">{plural(session.tables.length, "table")} · first rows of each</p>
      {frozen && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-safe/40 bg-safe-soft px-4 py-3 text-sm">
          <Lock className="size-4 text-safe" /><span className="flex-1">This dataset has releases, so its tables are frozen: each release must stay traceable to exactly this data.</span>
          <Button size="sm" variant="outline" onClick={() => setDup(true)}><Copy /> Duplicate to change the data</Button>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {session.tables.map(x => (
          <span key={x.name} className={cn("inline-flex overflow-hidden rounded-full border bg-card text-[13px]", x.name === t.name && "border-primary bg-primary text-primary-foreground")}>
            <button className="px-3 py-1.5" onClick={() => setCurrent(x.name)} aria-pressed={x.name === t.name}>{x.name} · {fmt(x.rows)}</button>
            {removable && <Tip text="Remove this table"><button className="py-1.5 pl-1 pr-2.5 opacity-60 hover:text-risk hover:opacity-100" onClick={() => setRemoving(x.name)} aria-label={`Remove ${x.name}`}><X className="size-3.5" /></button></Tip>}
          </span>
        ))}
      </div>
      <NamingNote table={t} frozen={frozen} />
      <TableWrap>
        <table className="w-full border-collapse"><thead><tr>{t.columns.map(c => { const was = t.naming.unnamed.find(u => u.name === c)?.original;
          return <Th key={c} title={was ? `was ${was}` : undefined}>{c}{was && <span className="block font-normal normal-case text-muted-foreground">was {was}</span>}</Th>; })}</tr></thead>
          <tbody>{t.preview.map((r, i) => <tr key={i}>{t.columns.map(c => { const v = shown(t.name, c, r[c]); return <Td key={c} className={ROLE_TONE[role(t.name, c)]} title={clip(v, 600)}>{clip(v)}</Td>; })}</tr>)}</tbody></table>
      </TableWrap>
      <ConfirmDialog open={!!removing} onOpenChange={o => !o && setRemoving("")} title={`Remove ${removing}?`} action="Remove the table" danger
        onConfirm={() => removeTable(removing)}>
        <b>{removing}</b> leaves this dataset (your original file is not touched).{scan ? " The scan and plan start over, because the data changed." : ""}
      </ConfirmDialog>
      <DuplicateDialog item={{ id: session.id, name: session.name, released: true, tables: session.tables.length }} open={dup} onOpenChange={setDup} />
    </Section>
  );
}

/** One "⋯" menu per dataset instead of a row of buttons. */
function DatasetMenu({ item, onRename, onDuplicate, onDelete, hideDelete }: { item: { id: string; name: string; released: boolean }; onRename: () => void; onDuplicate: () => void; onDelete?: () => void; hideDelete?: boolean }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={`More for ${item.name}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onSelect={onDuplicate}><Copy /> Duplicate</DropdownMenuItem>
        <DropdownMenuItem onSelect={onRename}><Pencil /> Rename</DropdownMenuItem>
        {!hideDelete && <><DropdownMenuSeparator />
          <DropdownMenuItem danger disabled={item.released} onSelect={onDelete}><Trash2 /> {item.released ? "Released: kept as the record" : "Delete"}</DropdownMenuItem></>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DuplicateDialog({ item, open, onOpenChange }: { item: { id: string; name: string; released: boolean; tables: number }; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <NameDialog open={open} onOpenChange={onOpenChange} title="Duplicate the dataset" label="Name of the copy" initial={`${item.name}-copy`} busyKey="duplicate"
      action="Create the copy and open it" onSubmit={n => duplicateDataset(item.id, n)}
      intro={<>A new dataset with the same {plural(item.tables, "table")} and your column corrections. You can add or remove tables, then scan, plan and release again. The original{item.released ? " and its releases stay" : " stays"} exactly as {item.released ? "they are" : "it is"}.</>} />
  );
}

function Workspace() {
  const sessions = useApp(s => s.sessions), current = useApp(s => s.session?.id);
  const [dialog, setDialog] = useState<{ kind: "" | "rename" | "duplicate" | "delete"; item?: SessionListItem }>({ kind: "" });
  const [query, setQuery] = useState(""), [all, setAll] = useState(false);
  if (!sessions.length) return null;
  const matching = sessions.filter(x => x.name.toLowerCase().includes(query.toLowerCase()) || x.id === current);
  const listed = all || query ? matching : matching.slice(0, WORKSPACE_SHOWN);
  const close = (o: boolean) => !o && setDialog({ kind: "" });
  const item = dialog.item;
  return (
    <Section title="Your workspace" right={<div className="flex items-center gap-3"><span className="text-sm text-muted-foreground">{plural(sessions.length, "dataset")} · kept in the local output folder</span>
      {sessions.length > WORKSPACE_SHOWN && <div className="relative"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input className="w-56 pl-8" placeholder="Find a dataset…" value={query} onChange={e => setQuery(e.target.value)} /></div>}</div>}>
      <div className="overflow-hidden rounded-xl border">
        {listed.map(x => {
          const r = x.last_release, st = x.steps, isCurrent = x.id === current;
          const stage = x.releases ? plural(x.releases, "release") : st.approved ? "approved" : st.planned ? "planned" : st.scanned ? "scanned" : "new";
          return (
            <div key={x.id} className={cn("grid items-center gap-x-4 gap-y-2 border-b px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,1.4fr)_auto_minmax(0,1.2fr)_auto]", isCurrent && "bg-safe-soft")}>
              <div className="min-w-0"><b className="block truncate">{x.name}</b><span className="text-sm text-muted-foreground">{plural(x.tables.length, "table")} · {mb(x.bytes)} MB · {when(x.created_at)}</span></div>
              <div className="flex items-center gap-1.5">
                {[st.scanned, st.planned, st.approved, x.releases > 0].map((on, i) => <span key={i} className={cn("size-2 rounded-full bg-input", on && "bg-ok")} />)}
                <Badge variant={x.released ? "ok" : "outline"} className="ml-1">{x.released && <Lock className="size-3" />}{stage}</Badge>
              </div>
              <div className="truncate text-sm text-muted-foreground">
                {r ? <>Last for <b className="text-foreground">{r.recipient}</b>{r.singled_out_after != null ? <> · singled out {pct(r.singled_out_before)} → <b className="text-safe">{pct(r.singled_out_after)}</b></> : r.epsilon != null ? <> · statistics, ε {r.epsilon}</> : null}</> : x.receiver}
              </div>
              <div className="flex items-center justify-end gap-1">
                <Button size="sm" variant={isCurrent ? "outline" : "default"} onClick={() => reopen(x.id)}>{isCurrent ? "Open ✓" : "Open"}</Button>
                <DatasetMenu item={x} onRename={() => setDialog({ kind: "rename", item: x })} onDuplicate={() => setDialog({ kind: "duplicate", item: x })} onDelete={() => setDialog({ kind: "delete", item: x })} />
              </div>
            </div>
          );
        })}
        {!listed.length && <p className="px-4 py-3 text-sm text-muted-foreground">No dataset matches.</p>}
      </div>
      {!query && matching.length > WORKSPACE_SHOWN && <Button variant="outline" className="self-center" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${matching.length}`}</Button>}
      {item && <>
        <NameDialog open={dialog.kind === "rename"} onOpenChange={close} title="Rename the dataset" label="Name" initial={item.name} busyKey="rename" action="Save"
          hint="Letters, digits, '-' and '_'; other characters become '_'." onSubmit={n => renameDataset(item.id, n)} />
        <DuplicateDialog item={{ id: item.id, name: item.name, released: item.released, tables: item.tables.length }} open={dialog.kind === "duplicate"} onOpenChange={close} />
        <ConfirmDialog open={dialog.kind === "delete"} onOpenChange={close} title={`Delete ${item.name}?`} action="Delete it" danger onConfirm={() => deleteDataset(item.id)}>
          The dataset's local copy, scan and plan are deleted from this computer. It was never released. This cannot be undone.
        </ConfirmDialog>
      </>}
    </Section>
  );
}
