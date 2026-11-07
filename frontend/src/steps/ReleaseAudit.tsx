// Release audit: the record of every release made in this app (who it was for, who approved it, what was done to each
// column, the attack before and after, the risk left, the file fingerprints), and the automatic planner measured on
// every receiver (results/receivers.csv, `make receivers`). Works on company data: nothing here needs the answer files;
// a release scored with the organisers' toolkit (`make screens`) also shows its checks.
import { FileCheck2, Lock, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Kpi, Kpis, PageHead } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Meter, Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, type AuditDetail, type AuditItem, type Baselines, type ReceiverResult, type ReceiversBenchmark } from "@/lib/api";
import { clip, fmt, pct, plural, when } from "@/lib/format";
import { go, useApp } from "@/lib/store";
import { cn } from "@/lib/utils";

export function ReleaseAudit() {
  const [releases, setReleases] = useState<AuditItem[] | null>(null);
  const [bench, setBench] = useState<ReceiversBenchmark | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<AuditItem[]>("/api/audit/releases").then(setReleases).catch((e: Error) => setError(e.message));
    api<ReceiversBenchmark>("/api/audit/receivers").then(setBench).catch((e: Error) => setError(e.message));
  }, []);
  return (
    <>
      <PageHead title="Release audit" lede="Every release made here: who it was for, who approved it, what was done to each column, and what risk is left. And how the automatic planner does for each of the challenge's receivers." />
      {error && <Card className="border-risk/50 p-4 text-sm">{error}</Card>}
      <Tabs defaultValue="releases">
        <TabsList>
          <TabsTrigger value="releases">Your releases <Badge>{releases?.length ?? "…"}</Badge></TabsTrigger>
          <TabsTrigger value="receivers">Receivers benchmark <Badge>{bench?.rows.length ?? "…"}</Badge></TabsTrigger>
        </TabsList>
        <TabsContent value="releases">{releases ? <Releases items={releases} /> : <Spinner />}</TabsContent>
        <TabsContent value="receivers">{bench ? <Receivers bench={bench} /> : <Spinner />}</TabsContent>
      </Tabs>
    </>
  );
}

// ---------------------------------------------------------------- your releases
function Releases({ items }: { items: AuditItem[] }) {
  const [picked, setPicked] = useState<AuditItem | null>(items[0] ?? null);
  if (!items.length) return (
    <Card className="flex flex-col items-start gap-3 p-5">
      <b>No releases yet.</b>
      <p className="text-sm text-muted-foreground">Each release made in the five steps is recorded here with its approval, its column decisions, the attack replayed on it and the fingerprints of its files.</p>
      <Button onClick={() => go("data")}>Start with your data →</Button>
    </Card>
  );
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(240px,320px)_minmax(0,1fr)]">
      <div className="flex flex-col gap-2 lg:sticky lg:top-4">
        {items.map(r => {
          const on = picked?.release_id === r.release_id && picked.session_id === r.session_id;
          return (
            <button key={`${r.session_id}/${r.release_id}`} onClick={() => setPicked(r)} aria-pressed={on}
              className={cn("flex flex-col gap-1 rounded-xl border bg-card p-3.5 text-left shadow-sm transition-colors hover:bg-muted", on && "border-primary ring-1 ring-primary")}>
              <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">{r.dataset} · {when(r.created_at)}</span>
              <b className="leading-snug">{r.recipient}</b>
              <span className="flex flex-wrap gap-1.5">
                {r.k != null && <Badge variant="safe">k = {r.k}</Badge>}
                {r.epsilon != null && <Badge variant="safe">ε = {r.epsilon}</Badge>}
                <Badge variant={r.published ? "ok" : "outline"}>{r.published ? "shared" : "not downloaded yet"}</Badge>
              </span>
            </button>
          );
        })}
      </div>
      {picked && <ReleaseRecord key={`${picked.session_id}/${picked.release_id}`} item={picked} />}
    </div>
  );
}

function ReleaseRecord({ item }: { item: AuditItem }) {
  const [d, setD] = useState<AuditDetail | null>(null), [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<AuditDetail>(`/api/audit/releases/${item.session_id}/${encodeURIComponent(item.release_id)}`).then(setD).catch((e: Error) => setError(e.message));
  }, [item]);
  if (error) return <Card className="border-risk/50 p-4 text-sm">{error}</Card>;
  if (!d) return <Card className="p-5"><Spinner /></Card>;
  const m = d.manifest, plan = m.plan, s = d.summary;
  const tables = [...new Set(plan.actions.map(a => a.table))];
  const after = d.attack?.after;
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-2 p-5">
        <span className="eyebrow flex items-center gap-1.5 text-safe"><Lock className="size-3.5" /> Release {m.release_id}</span>
        <h2 className="text-2xl">{s.recipient}</h2>
        <p className="text-sm text-muted-foreground">
          {d.dataset} · receiver {plan.scenario_id} · made {when(m.created_at)} · plan version {s.plan_version ?? "–"} · approved by <b className="text-foreground">{plan.approved_by ?? "nobody"}</b>
        </p>
        <p className="text-xs text-muted-foreground">Key domain <code>{m.key_domain}</code> · input fingerprint <code title={m.input_fingerprint}>{m.input_fingerprint.slice(0, 16)}…</code> · tool {m.tool_version}</p>
      </Card>
      <Kpis>
        {s.singled_out_before != null && <Kpi tone="risk" value={pct(s.singled_out_before)} label="singled out in the raw data" />}
        {s.singled_out_after != null && <Kpi tone={s.singled_out_after ? "warn" : "safe"} value={pct(s.singled_out_after)} label="singled out in the release" />}
        {after && <Kpi tone={after.matches === 1 ? "risk" : "safe"} value={after.matches === 1 ? "found" : fmt(after.matches)} label={after.matches === 1 ? "the attacked person is found in the release" : "people fit the attacker's facts in the release"} />}
        <Kpi tone="none" value={fmt(m.files.length)} label={plural(m.files.length, "file") + " shared, fingerprinted"} />
      </Kpis>
      {d.scorecard && (
        <Card className="flex flex-col gap-3 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xl">Scored with the organisers' toolkit</h3>
            <span className="text-sm text-muted-foreground">combined {d.scorecard.scores.composite?.toFixed(3) ?? "–"} · run {d.scorecard.run_id}</span></div>
          <TableWrap><table className="w-full"><thead><tr><Th /><Th>Check</Th><Th>Measured</Th><Th>Target</Th></tr></thead>
            <tbody>{[...d.scorecard.gates].sort((a, b) => Number(b.status === "FAIL") - Number(a.status === "FAIL")).map(g => <tr key={g.name}><Td><Badge variant={g.status === "PASS" ? "ok" : g.status === "FAIL" ? "risk" : "outline"}>{g.status}</Badge></Td><Td>{g.name}</Td><Td className="text-sm text-muted-foreground">{g.value}</Td><Td className="text-sm text-muted-foreground">{g.target}</Td></tr>)}</tbody>
          </table></TableWrap>
        </Card>
      )}
      <Card className="flex flex-col gap-3 p-5">
        <h3 className="text-xl">What was done to each column</h3>
        {tables.map(t => (
          <TableWrap key={t} className="max-h-none"><table className="w-full">
            <thead><tr><Th className="w-[28%]">{t}</Th><Th className="w-[22%]">Protection</Th><Th>Why</Th></tr></thead>
            <tbody>{plan.actions.filter(a => a.table === t).map(a => (
              <tr key={a.column}><Td className="font-mono text-xs">{a.column}</Td>
                <Td><Badge variant={a.technique === "drop" ? "risk" : a.technique === "keep" ? "outline" : "safe"}>{a.technique}</Badge>
                  {a.params && Object.keys(a.params).length > 0 && <span className="mt-1 block font-mono text-[11px] text-muted-foreground">{params(a.params)}</span>}</Td>
                <Td className="text-sm text-muted-foreground">{a.reason}</Td></tr>))}</tbody>
          </table></TableWrap>
        ))}
        {plan.aggregates.length > 0 && <p className="text-sm text-muted-foreground">Published statistics: {plan.aggregates.map(a => `${a.name} (ε ${a.epsilon})`).join(", ")}.</p>}
      </Card>
      {!!plan.column_names?.length && (
        <Card className="flex flex-col gap-3 p-5">
          <h3 className="text-xl">Columns that came without a name</h3>
          <TableWrap><table className="w-full"><thead><tr><Th>Input header</Th><Th>Name in the release</Th><Th>Suggested by</Th></tr></thead>
            <tbody>{plan.column_names.map(c => <tr key={`${c.table}.${c.original}`}><Td className="font-mono text-xs">{c.table}.{c.original}</Td><Td className="font-mono text-xs">{c.name}</Td>
              <Td className="text-sm">{c.suggested_by === "ai" ? <span className="inline-flex items-center gap-1"><Sparkles className="size-3.5" /> local AI ({c.model}), confirmed by a person</span> : c.suggested_by === "rules" ? "format check, confirmed by a person" : "a person"}</Td></tr>)}</tbody>
          </table></TableWrap>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-2 p-5">
          <h3 className="text-xl">Risk left</h3>
          <ul className="flex flex-col gap-1.5 pl-4 text-sm">{d.residual_risks.map((r, i) => <li key={i} className="list-disc">{r}</li>)}</ul>
          {m.llm && <p className="text-sm text-muted-foreground">Local AI: {m.llm.model}, {m.llm.used_for.join("; ")}.</p>}
        </Card>
        <Card className="flex flex-col gap-2 p-5">
          <h3 className="flex items-center gap-2 text-xl"><FileCheck2 className="size-5 text-safe" /> Files shared</h3>
          <TableWrap><table className="w-full"><thead><tr><Th>File</Th><Th>Rows</Th><Th>SHA-256</Th></tr></thead>
            <tbody>{m.files.map(f => <tr key={f.name}><Td className="font-mono text-xs">{f.name}</Td><Td className="tabular-nums">{fmt(f.rows)}</Td><Td><code className="text-xs" title={f.sha256}>{f.sha256.slice(0, 16)}…</code></Td></tr>)}</tbody>
          </table></TableWrap>
          <p className="text-xs text-muted-foreground">Row maps (which released row came from which record) stay on this computer and are never in a release.</p>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- receivers benchmark
type Filter = "all" | "fits" | "ready" | "needs tuning" | "unscored";
const STATUS: Record<ReceiverResult["status"], { label: string; tone: "ok" | "warn" | "outline" | "risk" }> = {
  ready: { label: "ready", tone: "ok" }, "needs tuning": { label: "needs tuning", tone: "warn" },
  unscored: { label: "statistics, not scored", tone: "outline" }, failed: { label: "failed", tone: "risk" },
};

function Receivers({ bench }: { bench: ReceiversBenchmark }) {
  const cat = useApp(s => s.cat), session = useApp(s => s.session);
  const [filter, setFilter] = useState<Filter>("all");
  const have = new Set(session?.tables.map(t => t.name) ?? []);
  const fits = (id: string) => {
    const tables = cat?.receivers.find(r => r.id === id)?.tables ?? [];
    return !!session && tables.length > 0 && tables.every(t => have.has(t));
  };
  const rows = useMemo(() => bench.rows.filter(r => filter === "all" || (filter === "fits" ? fits(r.id) : r.status === filter)), [bench, filter, session]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (!bench.rows.length) return (
    <Card className="flex flex-col gap-2 p-5"><b>Not measured yet.</b>
      <p className="text-sm text-muted-foreground">Run <code>make receivers</code> (needs the challenge pack): it plans, releases and scores every receiver and writes <code>results/receivers.csv</code>.</p></Card>
  );
  const count = (st: ReceiverResult["status"]) => bench.rows.filter(r => r.status === st).length;
  const verdicts = bench.rows.map(versusB2k).filter((v): v is Verdict => v !== null);
  const beats = verdicts.filter(v => v.key === "beats").length, lessUseful = verdicts.filter(v => v.key === "less-useful").length;
  return (
    <div className="flex flex-col gap-4">
      <Kpis>
        <Kpi tone="ok" value={count("ready")} label="ready: combined score ≥ 0.70 with the automatic plan" />
        <Kpi tone="none" value={count("unscored")} label="public statistics: released, no organisers' scorer outside health" />
        <Kpi tone="warn" value={count("needs tuning")} label="need a person to tune the plan" />
        {count("failed") > 0 && <Kpi tone="risk" value={count("failed")} label="did not release" />}
      </Kpis>
      {verdicts.length > 0 && (
        <Kpis>
          <Kpi tone="ok" value={<>{beats}<span className="text-lg text-muted-foreground">/ {verdicts.length}</span></>} label="beat the organisers' B2-k baseline on both privacy and usefulness" />
          <Kpi tone="warn" value={<>{lessUseful}<span className="text-lg text-muted-foreground">/ {verdicts.length}</span></>} label="more private than B2-k but less useful: the plans to tune first" />
        </Kpis>
      )}
      <Card className="flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex max-w-3xl flex-col gap-1.5 text-sm text-muted-foreground">
            <p>Each receiver planned by the automatic planner (approved for this benchmark only), released, and scored with the organisers' <code>pets-eval</code>. Measured {when(bench.measured_at)}; <code>make receivers</code> measures again.</p>
            {bench.baselines_generated && <p>Under each score, the organisers' baselines from the challenge pack ({bench.baselines_generated}): <b>B0</b> drops names and ID codes, <b>B2</b> adds classic protection, <b>B2-k</b> also suppresses rows until k ≥ 5. Their privacy is measured once per dataset, ours per receiver; they release rows even to public receivers, which only get statistics from us.</p>}
          </div>
          <ToggleGroup type="single" value={filter} onValueChange={v => v && setFilter(v as Filter)}>
            <ToggleGroupItem value="all">All</ToggleGroupItem>
            {session && <ToggleGroupItem value="fits">Fit {session.name}</ToggleGroupItem>}
            <ToggleGroupItem value="ready">Ready</ToggleGroupItem>
            <ToggleGroupItem value="needs tuning">Needs tuning</ToggleGroupItem>
            <ToggleGroupItem value="unscored">Statistics</ToggleGroupItem>
          </ToggleGroup>
        </div>
        <TableWrap className="max-h-none"><table className="w-full">
          <thead><tr><Th>Receiver</Th><Th>Data · gets</Th><Th>Privacy</Th><Th>Usefulness</Th><Th>Combined</Th><Th>vs B2-k</Th><Th>Status</Th></tr></thead>
          <tbody>{rows.map(r => (
            <tr key={r.id} className="align-top">
              <Td className="min-w-[240px]"><b className="block leading-snug">{r.recipient}</b><span className="font-mono text-[11px] text-muted-foreground">{r.id} · {r.trust_level.replace(/_/g, " ")}{r.source === "hand-written" ? " · hand-written" : ""}</span>
                {r.why && <span className="mt-1 block text-xs text-muted-foreground">{r.why}</span>}</Td>
              <Td className="whitespace-nowrap text-sm">{r.dataset.replace(/_/g, " ")}<span className="block text-xs text-muted-foreground">{r.gets === "statistics" ? `statistics${r.epsilon != null ? ` · ε ${r.epsilon.toFixed(2)}` : ""}` : "rows"}</span></Td>
              <Td><Score v={r.privacy} /><Base b={r.baselines} of="privacy" /></Td><Td><Score v={r.utility} /><Base b={r.baselines} of="utility" /></Td>
              <Td className="font-mono tabular-nums">{r.composite?.toFixed(2) ?? "–"}</Td>
              <Td><VsB2k r={r} /></Td>
              <Td><Badge variant={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge></Td>
            </tr>))}</tbody>
        </table></TableWrap>
        {!rows.length && <p className="text-sm text-muted-foreground">No receiver matches this filter{filter === "fits" ? ": none of them is made for this data. Use “Someone else” on the Receiver & plan step." : "."}</p>}
      </Card>
    </div>
  );
}

type Verdict = { key: "beats" | "less-useful" | "less-private"; label: string; tone: "ok" | "warn" | "risk" };
/** Ours against the strongest baseline, B2-k (k >= 5 like our plans). Unscored receivers have no verdict. */
function versusB2k(r: ReceiverResult): Verdict | null {
  const b = r.baselines?.b2k;
  if (!b || r.privacy == null || r.utility == null) return null;
  if (r.privacy + 0.005 < b.privacy) return { key: "less-private", label: "less private", tone: "risk" };
  if (r.utility + 0.005 < b.utility) return { key: "less-useful", label: `−${Math.round((b.utility - r.utility) * 100)} pts useful`, tone: "warn" };
  return { key: "beats", label: "beats B2-k", tone: "ok" };
}
const VsB2k = ({ r }: { r: ReceiverResult }) => {
  const v = versusB2k(r);
  if (v) return <Badge variant={v.tone} title={v.key === "less-useful" ? "More private than B2-k, but its usefulness is higher" : undefined}>{v.label}</Badge>;
  return <span className="text-xs text-muted-foreground" title="B2-k releases rows to this receiver; we publish statistics only">–</span>;
};
const short = (x: number) => x.toFixed(2).replace(/^0\./, ".");
const Base = ({ b, of }: { b: Baselines | null; of: "privacy" | "utility" }) => !b ? null : (
  <span className="mt-1 block whitespace-nowrap font-mono text-[11px] text-muted-foreground" title="The organisers' baselines: B0, B2, B2-k">
    B0 {short(b.b0[of])} · B2 {short(b.b2[of])} · B2-k {short(b.b2k[of])}
  </span>
);

/** Plan parameters in a line: "to age_band · width 10 · rename_to age" (lists clipped). */
const params = (p: Record<string, unknown>) =>
  Object.entries(p).map(([k, v]) => `${k} ${clip(Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v), 32)}`).join(" · ");

const Score = ({ v }: { v: number | null }) => v == null ? <span className="text-muted-foreground">–</span> : (
  <div className="flex min-w-[88px] flex-col gap-1"><span className="font-mono text-sm tabular-nums">{v.toFixed(2)}</span><Meter value={v} tone={v >= 0.7 ? "ok" : v >= 0.4 ? "safe" : "risk"} /></div>
);
