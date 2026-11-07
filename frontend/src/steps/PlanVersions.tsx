// The plan as YAML, every version of it, and what changed between any two versions.
import { Check, Copy, Download, GitCompare, History, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/form";
import { Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { PlanCompare } from "@/lib/api";
import { plural, when } from "@/lib/format";
import { foldUnchanged, lineDiff } from "@/lib/linediff";
import { comparePlans, go, planHref, planYaml, useApp, useVersion } from "@/lib/store";
import { cn } from "@/lib/utils";

/** The exact plan.yaml that is approved and written into every release, with line numbers. */
export function PlanYaml({ version }: { version?: number }) {
  const plan = useApp(s => s.plan), [text, setText] = useState<string | null>(null), [copied, setCopied] = useState(false);
  useEffect(() => { setText(null); planYaml(version).then(setText).catch(() => setText("")); }, [plan, version]);
  if (text == null) return <span className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner /> Loading the plan file…</span>;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">The plan file exactly as it will be approved and written into the release manifest.</p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={async () => { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}</Button>
          <Button size="sm" variant="outline" asChild><a href={planHref()}><Download /> plan.yaml</a></Button>
        </div>
      </div>
      <pre className="max-h-[520px] overflow-auto rounded-xl border bg-muted py-3 font-mono text-[12.5px] leading-6">
        {text.trimEnd().split("\n").map((line, i) => (
          <div key={i} className="flex px-3 hover:bg-accent"><span className="w-10 shrink-0 select-none pr-3 text-right text-muted-foreground/70">{i + 1}</span><span className="whitespace-pre">{line}</span></div>
        ))}
      </pre>
    </div>
  );
}

/** Every version of the plan: what changed, who approved it, which one a release was made with. */
export function PlanVersionsPanel() {
  const data = useApp(s => s.versions), busy = useApp(s => s.busy === "plan");
  const [picked, setPicked] = useState<number[]>([]), [compare, setCompare] = useState<[number, number] | null>(null);
  if (!data || !data.versions.length) return null;
  const versions = [...data.versions].reverse();  // newest first
  const pick = (v: number, on: boolean) => setPicked(on ? [...picked.filter(x => x !== v), v].slice(-2) : picked.filter(x => x !== v));
  return (
    <Section eyebrow={<span className="inline-flex items-center gap-1.5"><History className="size-3.5" /> Plan versions</span>} title="Every change to the plan is kept"
      right={<Button variant="outline" disabled={picked.length !== 2} onClick={() => setCompare([Math.min(...picked), Math.max(...picked)] as [number, number])}>
        <GitCompare /> {picked.length === 2 ? `Compare v${Math.min(...picked)} and v${Math.max(...picked)}` : "Tick two to compare"}</Button>}>
      <ol className="relative flex flex-col">
        {versions.map((v, i) => {
          const current = v.version === data.current;
          return (
            <li key={v.version} className="relative grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-3 pb-3 last:pb-0">
              {i < versions.length - 1 && <span aria-hidden className="absolute left-[15px] top-8 h-[calc(100%-24px)] w-px bg-border" />}
              <span className={cn("z-[1] grid size-8 place-items-center rounded-full border-2 bg-card font-mono text-xs font-semibold", current ? "border-safe text-safe" : v.approved ? "border-ok text-ok" : "border-input text-muted-foreground")}>v{v.version}</span>
              <div className={cn("min-w-0 rounded-xl border px-3.5 py-2.5", current && "border-safe/50 bg-safe-soft")}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <b className="text-sm">{v.note}</b>
                  {current && <Badge variant="safe">current</Badge>}
                  {v.approved && <Badge variant="ok">approved by {v.approved_by}</Badge>}
                  {v.released_as && <Badge variant="outline" className="font-mono">released · {v.released_as}</Badge>}
                </div>
                <span className="text-xs text-muted-foreground">{when(v.created_at)} · for {v.recipient}</span>
              </div>
              <div className="flex items-center gap-2 pt-1.5">
                <label className="flex cursor-pointer items-center gap-1.5 text-[13px]"><Checkbox checked={picked.includes(v.version)} onCheckedChange={on => pick(v.version, !!on)} aria-label={`Compare version ${v.version}`} /> compare</label>
                {!current && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setCompare([v.version, data.current])}><GitCompare /> vs current</Button>}
                {!current && <Button size="sm" variant="outline" disabled={busy} onClick={() => useVersion(v.version)}><RotateCcw /> Use this version</Button>}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="text-sm text-muted-foreground">Using an earlier version makes it the plan again. If it was approved, it stays approved (it is exactly what was signed), so you can create a release from it straight away.</p>
      {compare && <CompareVersions a={compare[0]} b={compare[1]} onClose={() => setCompare(null)} />}
    </Section>
  );
}

function CompareVersions({ a, b, onClose }: { a: number; b: number; onClose: () => void }) {
  const [data, setData] = useState<PlanCompare | null>(null), current = useApp(s => s.versions?.current), busy = useApp(s => s.busy === "plan");
  useEffect(() => { comparePlans(a, b).then(setData).catch(() => onClose()); }, [a, b, onClose]);
  const older = a === current ? b : a;
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent wide>
        <DialogHeader><DialogTitle>Version {a} → version {b}</DialogTitle></DialogHeader>
        <DialogBody>
          {!data ? <Spinner /> : (
            <Tabs defaultValue="changes">
              <TabsList><TabsTrigger value="changes">What changed <Badge>{data.changes.length}</Badge></TabsTrigger><TabsTrigger value="yaml">YAML diff</TabsTrigger></TabsList>
              <TabsContent value="changes">
                {data.changes.length ? (
                  <TableWrap className="max-h-none"><table className="w-full border-collapse"><thead><tr><Th>What</Th><Th>Version {a}</Th><Th /><Th>Version {b}</Th></tr></thead>
                    <tbody>{data.changes.map(c => (
                      <tr key={c.what}><Td className="font-mono">{c.what}</Td><Td className="text-risk line-through decoration-risk/40">{c.before}</Td><Td className="text-muted-foreground">→</Td><Td className="font-semibold text-ok">{c.after}</Td></tr>
                    ))}</tbody></table></TableWrap>
                ) : <p className="text-sm text-muted-foreground">The two versions are the same.</p>}
              </TabsContent>
              <TabsContent value="yaml"><YamlDiff before={data.yaml_a} after={data.yaml_b} a={a} b={b} /></TabsContent>
            </Tabs>
          )}
        </DialogBody>
        <DialogFooter>
          {older !== current && <Button variant="outline" disabled={busy} onClick={async () => { if (await useVersion(older)) { onClose(); go("plan"); } }}><RotateCcw /> Use version {older}</Button>}
          <Button onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** A unified diff of two YAML texts: removed lines red, added lines green, unchanged runs folded. */
function YamlDiff({ before, after, a, b }: { before: string; after: string; a: number; b: number }) {
  const lines = lineDiff(before.trimEnd(), after.trimEnd()), shown = foldUnchanged(lines);
  const added = lines.filter(l => l.kind === "added").length, removed = lines.filter(l => l.kind === "removed").length;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted-foreground"><span className="font-mono text-risk">− {plural(removed, "line")}</span> only in version {a} · <span className="font-mono text-ok">+ {plural(added, "line")}</span> only in version {b}</p>
      <pre className="max-h-[520px] overflow-auto rounded-xl border bg-muted py-2 font-mono text-[12.5px] leading-6">
        {shown.map((l, i) => l.kind === "fold"
          ? <div key={i} className="select-none border-y border-dashed px-3 text-center text-xs text-muted-foreground">… {plural(l.count, "unchanged line")} …</div>
          : (
            <div key={i} className={cn("flex px-2", l.kind === "added" && "bg-ok-soft", l.kind === "removed" && "bg-risk-soft")}>
              <span className="w-9 shrink-0 select-none text-right text-muted-foreground/70">{l.a ?? ""}</span>
              <span className="w-9 shrink-0 select-none pr-2 text-right text-muted-foreground/70">{l.b ?? ""}</span>
              <span className={cn("w-4 shrink-0 select-none font-bold", l.kind === "added" ? "text-ok" : l.kind === "removed" ? "text-risk" : "text-transparent")}>{l.kind === "added" ? "+" : l.kind === "removed" ? "−" : " "}</span>
              <span className="whitespace-pre">{l.text}</span>
            </div>
          ))}
      </pre>
    </div>
  );
}
