// The frame around every step: the rail on the left (new dataset, steps, exposure, settings) and the top bar with
// the step's main action. The step itself is rendered in the middle.
import { Check, Download, Loader2, Plus } from "lucide-react";
import { useEffect } from "react";
import { Toaster } from "sonner";
import { Button } from "@/components/ui/button";
import { Meter, TooltipProvider } from "@/components/ui/misc";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { pct, plural } from "@/lib/format";
import { SCREENS, STEPS, applyTheme, askDownload, can, go, init, isScreen, newDataset, runScan, useApp, type Theme } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Approve } from "@/steps/Approve";
import { DataStep, openPicker } from "@/steps/DataStep";
import { MosaicAttack } from "@/steps/MosaicAttack";
import { PlanStep } from "@/steps/PlanStep";
import { Release } from "@/steps/Release";
import { ReleaseAudit } from "@/steps/ReleaseAudit";
import { RiskScan } from "@/steps/RiskScan";

const VIEWS = { data: DataStep, scan: RiskScan, plan: PlanStep, approve: Approve, release: Release, mosaic: MosaicAttack, audit: ReleaseAudit };

export default function App() {
  useEffect(() => { init(); }, []);
  const step = useApp(s => s.step), View = VIEWS[step];
  return (
    <TooltipProvider>
      {/* the rail's background and edge run the full height, also below a sticky rail */}
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[264px_minmax(0,1fr)] lg:bg-[linear-gradient(to_right,hsl(var(--card))_263px,hsl(var(--border))_263px,hsl(var(--border))_264px,transparent_264px)]">
        <Rail />
        <main className="min-w-0 px-4 pb-24 lg:px-8">
          <TopBar />
          <div className="mx-auto flex max-w-[1160px] flex-col gap-5"><View /></div>
        </main>
      </div>
      <Toaster position="bottom-right" richColors closeButton />
    </TooltipProvider>
  );
}

function Rail() {
  const step = useApp(s => s.step), session = useApp(s => s.session), scan = useApp(s => s.scan), plan = useApp(s => s.plan), results = useApp(s => s.results), cat = useApp(s => s.cat);
  const done: Record<string, boolean> = { data: !!session, scan: !!scan, plan: !!plan, approve: !!plan?.plan.approved, release: !!results };
  return (
    <aside className="flex min-w-0 flex-col gap-5 border-b bg-card p-4 lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:bg-transparent lg:p-5">
      <button onClick={newDataset} aria-label="Home: your data and workspace" title="Home: your data and workspace"
        className="-m-1.5 flex items-center gap-2.5 rounded-xl p-1.5 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-[linear-gradient(135deg,hsl(var(--risk))_50%,hsl(var(--safe))_50%)] font-display text-sm font-extrabold text-white">PT</span>
        <div><b className="block font-display text-[19px] font-extrabold leading-tight" style={{ fontStretch: "118%" }}>PETs Transformer</b><span className="text-xs text-muted-foreground">Beyond Syntax · safe data sharing</span></div>
      </button>
      <Button variant="outline" className="border-dashed font-semibold" onClick={newDataset}><Plus /> New dataset</Button>
      <nav aria-label="Steps" className="flex gap-1 overflow-x-auto lg:flex-col">
        {STEPS.map(([key, label], i) => {
          const current = key === step, isDone = done[key] && !current;
          return (
            <button key={key} disabled={!can(key)} onClick={() => go(key)} aria-current={current ? "step" : undefined}
              className={cn("flex items-center gap-3 whitespace-nowrap rounded-lg px-2.5 py-2 text-left font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
                current && "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground")}>
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full border-[1.5px] font-mono text-xs", current && "border-primary-foreground", isDone && "border-ok bg-ok text-white")}>
                {isDone ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
              </span>
              {label}
            </button>
          );
        })}
      </nav>
      <nav aria-label="Show the risk" className="flex flex-col gap-1">
        <span className="eyebrow px-2.5 text-[10.5px]">Show the risk</span>
        {SCREENS.filter(([key]) => key !== "mosaic" || cat?.screens?.includes("mosaic")).map(([key, label]) => (
          <button key={key} onClick={() => go(key)} aria-current={key === step ? "page" : undefined}
            className={cn("flex items-center gap-3 whitespace-nowrap rounded-lg px-2.5 py-2 text-left font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              key === step && "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground")}>
            <span className="grid size-6 shrink-0 place-items-center rounded-full border-[1.5px] font-mono text-xs">{key === "mosaic" ? "◎" : "✓"}</span>{label}
          </button>
        ))}
      </nav>
      <Ticker />
      <RailFooter />
    </aside>
  );
}

/** People singled out: the raw data, then the release. */
function Ticker() {
  const scan = useApp(s => s.scan), after = useApp(s => s.results?.summary.singled_out_after);
  if (!scan) return null;
  const worst = [...scan.risk.tables].sort((a, b) => b.unique_share - a.unique_share)[0];
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border bg-muted p-3">
      <span className="eyebrow text-[10.5px]">People singled out</span>
      <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-2 gap-y-1 text-xs text-muted-foreground"><span>Raw data</span><b className="big-number text-[22px] text-risk">{pct(worst.unique_share)}</b><Meter className="col-span-2" value={worst.unique_share} /></div>
      {after != null && <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-2 gap-y-1 text-xs text-muted-foreground"><span>Release</span><b className="big-number text-[22px] text-safe">{pct(after)}</b><Meter className="col-span-2" value={Math.max(0.01, after)} tone="safe" /></div>}
    </div>
  );
}

function RailFooter() {
  const theme = useApp(s => s.theme);
  return (
    <div className="mt-auto flex flex-wrap items-start justify-between gap-3 text-xs text-muted-foreground lg:flex-col">
      <ToggleGroup type="single" value={theme} onValueChange={v => v && applyTheme(v as Theme)} aria-label="Colour theme">
        <ToggleGroupItem value="light">☀ Light</ToggleGroupItem><ToggleGroupItem value="dark">☾ Dark</ToggleGroupItem><ToggleGroupItem value="system">Auto</ToggleGroupItem>
      </ToggleGroup>
      <span><b className="font-semibold text-ok">● Runs on this computer only.</b> Files stay in a local folder; nothing is sent anywhere.</span>
    </div>
  );
}

/** Where you are and the one thing to do next, pinned to the top. */
function TopBar() {
  const s = useApp();
  if (isScreen(s.step)) {
    const label = SCREENS.find(([k]) => k === s.step)?.[1];
    return (
      <header className="sticky top-0 z-30 -mx-4 mb-6 border-b bg-background/85 px-4 py-3 backdrop-blur-md lg:-mx-8 lg:px-8">
        <div className="mx-auto flex min-h-[46px] max-w-[1160px] flex-col justify-center gap-0.5">
          <span className="eyebrow text-safe">Show the risk · {label}</span>
          <span className="text-[13px]">{s.step === "audit"
            ? "Every release made here, and the receivers benchmark (make receivers)"
            : "The challenge's hospital data and its public posts and news clips, replayed on your HEALTH-S1 release (make screens)"}</span>
        </div>
      </header>
    );
  }
  const n = STEPS.findIndex(([k]) => k === s.step);
  const recipient = s.plan?.scenario?.recipient ?? s.plan?.plan.scenario_id ?? "";
  let info: React.ReactNode = "", action: React.ReactNode = null;
  if (s.progress) info = <span className="inline-flex items-center gap-2">{s.progress.title}… <Loader2 className="size-4 animate-spin text-safe" /></span>;
  else if (s.step === "data") {
    info = s.session ? <><b>{s.session.name}</b> · {plural(s.session.tables.length, "table")} loaded</> : "Drop your tables, pick an example, or reopen earlier work.";
    action = s.session ? <Button onClick={() => (s.scan ? go("scan") : runScan())}>{s.scan ? "See the risk scan →" : "Scan for risks →"}</Button> : <Button onClick={openPicker}>Choose files…</Button>;
  } else if (s.step === "scan") {
    if (!s.scan) { info = "Not scanned yet."; action = <Button onClick={runScan}>Scan for risks</Button>; }
    else { const w = [...s.scan.risk.tables].sort((a, b) => b.unique_share - a.unique_share)[0]; info = <>{pct(w.unique_share)} of <b>{w.table}</b> can be singled out today</>; action = <Button onClick={() => go("plan")}>Choose a receiver →</Button>; }
  } else if (s.step === "plan") {
    info = s.plan ? <>Plan for <b>{recipient}</b>{s.plan.reviews.length ? ` · ${plural(s.plan.reviews.length, "item")} to check` : ""}</> : "Pick who receives the data.";
    action = s.plan && <Button onClick={() => go("approve")}>Review & approve →</Button>;
  } else if (s.step === "approve") {
    info = s.plan?.plan.approved ? <>Approved by <b>{s.plan.plan.approved_by}</b></> : <>Plan for <b>{recipient}</b> waits for a named approval</>;
    action = s.plan?.plan.approved ? <Button onClick={() => go("release")}>Create the release →</Button>
      : <Button onClick={() => document.getElementById("signoff")?.scrollIntoView({ behavior: "smooth", block: "center" })}>Sign off ↓</Button>;
  } else if (s.step === "release") {
    info = s.results ? <><b>{s.results.release_id}</b> · {plural(s.results.files.length, "file")} + manifest</> : <>Approved by <b>{s.plan?.plan.approved_by}</b> · nothing released yet</>;
    action = s.results && <Button variant="safe" onClick={askDownload}><Download /> Download<span className="hidden sm:inline"> release</span></Button>;
  }
  return (
    <header className="sticky top-0 z-30 -mx-4 mb-6 border-b bg-background/85 px-4 py-3 backdrop-blur-md lg:-mx-8 lg:px-8">
      <div className="mx-auto flex min-h-[46px] max-w-[1160px] items-center justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="eyebrow text-safe">Step {n + 1} of 5 · {STEPS[n][1]}</span>
          <span className="line-clamp-2 text-[13px] sm:truncate">{info}</span>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </header>
  );
}

