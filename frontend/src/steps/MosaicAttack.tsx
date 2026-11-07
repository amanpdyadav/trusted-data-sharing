// Mosaic attack: one public post or news clip followed across datasets, one clue at a time (ported from the main
// branch). Three modes: raw data shared, names removed everywhere, and our release (where the chain breaks).
import { Pause, Play, RotateCcw, StepBack, StepForward } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { PageHead } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Meter } from "@/components/ui/misc";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { clip, fmt, plural, when } from "@/lib/format";
import { useScreen, type ChainStep, type FunnelRow, type Mosaic, type MosaicCase } from "@/lib/screens";
import { cn } from "@/lib/utils";

type Mode = "raw" | "names" | "ours";
const MODES: [Mode, string][] = [["raw", "Raw data shared"], ["names", "Names removed"], ["ours", "Our release"]];
const KIND_LABEL = { public: "public", leaked: "if shared", release: "names removed" } as const;

/** One tick per clue on the hospital step, one per dataset after it. */
function ticksOf(chain: ChainStep[]): [step: number, rows: number][] {
  return chain.flatMap((st, i): [number, number][] => {
    const rows = st.funnel.length;
    return st.id === "ed" && rows > 1 ? Array.from({ length: rows - 1 }, (_, r) => [i, r + 2]) : [[i, rows]];
  });
}

export function MosaicAttack() {
  const { data, error } = useScreen<Mosaic>("mosaic");
  if (!data) return <><PageHead title="Mosaic attack" lede="From one public post or news clip to a full profile." /><NotBuilt error={error} what="mosaic data" /></>;
  return <MosaicBoard data={data} />;
}

function MosaicBoard({ data }: { data: Mosaic }) {
  const [kind, setKind] = useState<"post" | "news">("post");
  const [caseId, setCaseId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("names");
  const [tick, setTick] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const ofKind = useMemo(() => data.cases.filter(c => c.kind === kind), [data, kind]);
  const c: MosaicCase = ofKind.find(x => x.id === caseId) ?? ofKind[0] ?? data.cases[0];
  const counts = { post: data.cases.filter(x => x.kind === "post").length, news: data.cases.filter(x => x.kind === "news").length };
  const activeMode: Mode = mode === "raw" && !c.raw.length ? "names" : mode;
  const chain = activeMode === "ours" ? [] : c[activeMode];
  const ticks = useMemo(() => ticksOf(chain), [chain]);
  const t = tick == null || tick >= ticks.length ? ticks.length - 1 : tick;

  useEffect(() => {
    if (!playing) return;
    if (t >= ticks.length - 1) { setPlaying(false); return; }
    const id = setTimeout(() => setTick(t + 1), 1600);
    return () => clearTimeout(id);
  }, [playing, t, ticks.length]);
  const reset = () => { setPlaying(false); setTick(0); };

  return (
    <>
      <PageHead title="Mosaic attack" lede="Pick a public post or a news clip and follow it across datasets, one clue at a time. Switch the mode to see what removing names does, and what our release does." />
      <Card className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <ToggleGroup type="single" value={kind} onValueChange={v => { if (v) { setKind(v as "post" | "news"); setCaseId(null); reset(); } }}>
            <ToggleGroupItem value="post">Public posts <span className="ml-1 font-mono text-xs opacity-70">{counts.post}</span></ToggleGroupItem>
            <ToggleGroupItem value="news">News clips <span className="ml-1 font-mono text-xs opacity-70">{counts.news}</span></ToggleGroupItem>
          </ToggleGroup>
          <select aria-label="Pick a scrap" value={c.id} onChange={e => { setCaseId(e.target.value); reset(); }}
            className="min-w-0 flex-1 basis-64 rounded-lg border border-input bg-card px-3 py-2 text-sm">
            {ofKind.map(x => <option key={x.id} value={x.id}>{x.id} · {clip(x.label, 24)}: {clip(x.text, 60)}</option>)}
          </select>
          <ToggleGroup type="single" value={activeMode} onValueChange={v => { if (v) { setMode(v as Mode); reset(); } }}>
            {MODES.filter(([k]) => k !== "raw" || c.raw.length).map(([k, l]) => <ToggleGroupItem key={k} value={k}>{l}</ToggleGroupItem>)}
          </ToggleGroup>
        </div>
        <p className="text-xs text-muted-foreground">All people are synthetic and shown as they appear in the data, to show how re-identification happens. ID codes, phone numbers and IBANs are partly masked. Built {when(data.created_utc)}.</p>
      </Card>
      {activeMode === "ours" ? <OursView c={c} /> : (() => {
        const [si, rowsShown] = ticks[t], st = chain[si];
        const shown = st.funnel.slice(0, Math.max(rowsShown, 1));
        const left = shown.length ? shown[shown.length - 1][1] : null;
        const stepDone = rowsShown >= st.funnel.length;
        const reached = chain.slice(0, stepDone ? si + 1 : si);
        return (
          <>
            <LinkGraph chain={chain} upto={si} />
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" disabled={t === 0} onClick={() => { setPlaying(false); setTick(Math.max(0, t - 1)); }}><StepBack /> Back</Button>
              <Button disabled={t >= ticks.length - 1} onClick={() => { setPlaying(false); setTick(t + 1); }}><StepForward /> Next {si === 0 || st.id === "ed" ? "clue" : "link"}</Button>
              <Button variant="outline" onClick={() => { if (!playing && t >= ticks.length - 1) setTick(0); setPlaying(!playing); }}>{playing ? <><Pause /> Stop</> : <><Play /> Play</>}</Button>
              <Button variant="outline" onClick={reset}><RotateCcw /> Restart</Button>
              <span className="text-sm text-muted-foreground">step {t + 1} of {ticks.length}</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card className={cn("flex flex-col gap-3 p-5", st.kind !== "public" && "border-risk/50")}>
                <Badge variant={st.kind === "public" ? "safe" : "risk"} className="w-fit">{KIND_LABEL[st.kind]}</Badge>
                <h2 className="text-2xl">{st.title}</h2>
                <code className="text-xs text-muted-foreground">{st.file}</code>
                <p>{st.how}</p>
                {si === 0 && st.quote && <blockquote className="border-l-[3px] border-risk py-1 pl-3 text-[17px]"><b>{st.quote.who}</b> <span className="text-xs text-muted-foreground">{st.quote.when}</span><br />{st.quote.text}</blockquote>}
                {si === 0 && st.clues?.length ? <p className="text-xs text-muted-foreground">Clues read from it: {st.clues.join(" · ")}</p> : null}
                {shown.length > 0 && <Funnel rows={shown} />}
                {st.verified && <Badge variant="ok" className="w-fit">verified against ground truth</Badge>}
              </Card>
              <Dossier chain={chain} reached={reached} left={left} mode={activeMode} />
            </div>
          </>
        );
      })()}
    </>
  );
}

function Funnel({ rows, safe = false }: { rows: FunnelRow[]; safe?: boolean }) {
  const top = Math.log10((rows[0]?.[1] ?? 1) + 1);
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map(([label, n, applied], i) => (
        <div key={`${label}-${i}`} className={cn("flex flex-col gap-1", applied === false && "opacity-50")}>
          <div className="flex justify-between gap-3 text-sm"><span className="text-muted-foreground">{label}</span><b className="font-mono tabular-nums">{fmt(n)}</b></div>
          <Meter value={Math.max(0.015, Math.log10(n + 1) / top)} tone={safe && i === rows.length - 1 ? "safe" : "risk"} />
        </div>
      ))}
    </div>
  );
}

/** The attacker's dossier as a data mapping: one block per source reached, newest on top. */
function Dossier({ chain, reached, left, mode }: { chain: ChainStep[]; reached: ChainStep[]; left: number | null; mode: Mode }) {
  const facts = new Set(reached.flatMap(x => Object.keys(x.revealed))).size;
  const isNew = (k: string, i: number) => !chain.slice(0, i).some(x => k in x.revealed);
  return (
    <Card className="flex flex-col gap-3 p-5">
      <span className="eyebrow">What the attacker now knows</span>
      {left != null && <><div className="big-number text-[52px] leading-none text-risk">{fmt(left)}</div><p className="text-sm text-muted-foreground">{left === 1 ? "record left: one person" : "records still fit"}</p></>}
      <p className="text-sm text-muted-foreground">{plural(facts, "fact")} from {plural(reached.length, "source")}{mode === "names" ? ", with names removed everywhere" : ""}</p>
      <div className="flex flex-col gap-2.5">
        {reached.map((x, i) => ({ x, i })).reverse().map(({ x, i }) => {
          const latest = i === reached.length - 1, pub = x.kind === "public";
          return (
            <div key={x.id} className={cn("flex flex-col gap-1 rounded-xl border border-l-4 p-3", pub ? "border-l-safe" : "border-l-risk",
              latest && (pub ? "bg-safe-soft shadow-sm" : "bg-risk-soft shadow-sm"), latest && "animate-in fade-in slide-in-from-top-1")}>
              <div className="flex items-center justify-between gap-2"><b>{i + 1}. {x.dataset}</b><Badge variant={pub ? "safe" : "risk"}>{KIND_LABEL[x.kind]}</Badge></div>
              <span className="text-xs text-muted-foreground">{i > 0 && x.link ? <>joined on <b>{x.link}</b>{x.verified ? " · verified" : ""}</> : `read from the ${x.id === "news" ? "news clip" : "post"}`}</span>
              {Object.entries(x.revealed).map(([k, v]) => (
                <div key={k} className={cn("flex justify-between gap-3 border-t border-dashed py-0.5 text-sm", !isNew(k, i) && "opacity-55")}>
                  <span className="text-muted-foreground">{k}</span><b className="text-right [overflow-wrap:anywhere]">{v}</b>
                </div>
              ))}
            </div>
          );
        })}
        {!reached.length && <p className="text-sm text-muted-foreground">Nothing yet.</p>}
      </div>
    </Card>
  );
}

function OursView({ c }: { c: MosaicCase }) {
  const r = c.ours;
  const chain: ChainStep[] = [c.names[0], { ...c.names[0], id: "ours", dataset: "Our release", kind: "release", link: "" }, ...c.names.slice(2)];
  return (
    <>
      <LinkGraph chain={chain} upto={0} broken />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className={cn("flex flex-col gap-3 p-5", r.holds ? "border-safe/50" : "border-risk/50")}><h2 className="text-2xl">Same scrap, our release</h2><Funnel rows={r.funnel} safe={r.holds} /></Card>
        <Card className="flex flex-col gap-3 p-5">
          <span className="eyebrow">What the attacker now knows</span>
          <div className={cn("big-number text-[52px] leading-none", r.holds ? "text-safe" : "text-risk")}>{fmt(r.candidates)}</div>
          <p className="text-sm text-muted-foreground">visits still fit{r.target_in ? ", the real one among them" : ""}. {r.holds ? "No single visit, no birth date, postcode or name: nothing to join to other data." : "Below k = 5 for this attacker: a residual risk we report."}</p>
        </Card>
      </div>
    </>
  );
}

/** How the person is identified: datasets joined, on what, lit up as the chain advances. */
function LinkGraph({ chain, upto, broken = false }: { chain: ChainStep[]; upto: number; broken?: boolean }) {
  const w = 150, gap = 96, h = 104, width = chain.length * w + (chain.length - 1) * gap + 8;
  return (
    <Card className="overflow-x-auto px-3 py-2">
      <svg viewBox={`0 0 ${width} ${h}`} width={width} height={h} role="img" aria-label="How the datasets link up" className="block">
        {chain.map((st, i) => {
          if (i === 0) return null;
          const x1 = 4 + (i - 1) * (w + gap) + w, x2 = x1 + gap, on = !broken && i <= upto, brk = broken && i === 1;
          const stroke = brk ? "hsl(var(--safe))" : on ? "hsl(var(--risk))" : "hsl(var(--input))";
          return (
            <g key={`e${i}`}>
              <line x1={x1} y1={50} x2={x2 - 6} y2={50} stroke={stroke} strokeWidth={2} strokeDasharray={on ? undefined : "5 4"} />
              {on && <path d={`M${x2 - 8},45 L${x2},50 L${x2 - 8},55 Z`} fill="hsl(var(--risk))" />}
              <text x={(x1 + x2) / 2} y={brk ? 38 : i % 2 ? 98 : 14} textAnchor="middle" fontSize={10.5} fontFamily="var(--font-mono, monospace)"
                fill={brk ? "hsl(var(--safe))" : on ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))"}>{brk ? "chain breaks" : clip(st.link, 36)}</text>
            </g>
          );
        })}
        {chain.map((st, i) => {
          const x = 4 + i * (w + gap), lit = broken ? i <= 1 : i <= upto, cut = broken && i > 1;
          const pub = st.kind === "public" || st.id === "ours";  // blue: public sources and our release; orange: attacker joins
          return (
            <g key={`n${i}`} opacity={cut ? 0.5 : 1}>
              <rect x={x} y={22} width={w} height={56} rx={12} strokeWidth={lit ? 2 : 1.5} strokeDasharray={cut ? "5 4" : undefined}
                fill={lit ? (pub ? "hsl(var(--safe-soft))" : "hsl(var(--risk-soft))") : "hsl(var(--muted))"}
                stroke={lit ? (pub ? "hsl(var(--safe))" : "hsl(var(--risk))") : "hsl(var(--border))"} />
              <text x={x + 12} y={44} fontSize={10} fontWeight={600} letterSpacing=".08em" fill="hsl(var(--muted-foreground))">{(st.id === "ours" ? "our release" : KIND_LABEL[st.kind]).toUpperCase()}</text>
              <text x={x + 12} y={64} fontSize={13} fontWeight={600} fill="hsl(var(--foreground))">{clip(st.dataset, 18)}</text>
            </g>
          );
        })}
      </svg>
    </Card>
  );
}

export function NotBuilt({ error, what }: { error: string | null; what: string }) {
  return (
    <Card className={cn("flex flex-col gap-2 p-5", error && "border-risk/50")}>
      {error ? <><b>No {what} yet.</b><p className="text-sm text-muted-foreground">{error}</p>
        <p className="text-sm text-muted-foreground">Build it: <code>python -m evaluation screens --release out/health-s1/release --rowmaps out/health-s1/private --plan plans/health-s1.yaml</code></p></>
        : <p className="text-sm text-muted-foreground">Loading {what}…</p>}
    </Card>
  );
}
