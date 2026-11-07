// Building blocks shared by the steps: page head, the "what to do here" strip, headline tiles, facts, progress.
import { Check } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/misc";
import { ROLE_TONE, clip } from "@/lib/format";
import { useApp } from "@/lib/store";
import { cn } from "@/lib/utils";

export function PageHead({ title, lede }: { title: ReactNode; lede?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <h1 className="text-[clamp(26px,3.4vw,40px)] leading-[1.06]">{title}</h1>
      {lede && <p className="max-w-[70ch] text-base text-muted-foreground">{lede}</p>}
    </div>
  );
}

/** The few things to do on this step, with the current one highlighted. */
export function Guide({ steps, done }: { steps: string[]; done: boolean[] }) {
  const current = steps.findIndex((_, i) => !done[i]);
  return (
    <ol className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-2">
      {steps.map((text, i) => (
        <li key={text} className={cn("flex items-center gap-2.5 rounded-xl border bg-card px-3 py-2.5 text-sm text-muted-foreground",
          i === current && "border-safe font-semibold text-foreground ring-1 ring-safe")}>
          <span className={cn("grid size-6 shrink-0 place-items-center rounded-full border-[1.5px] font-mono text-xs",
            done[i] && "border-ok bg-ok text-white", i === current && "border-safe bg-safe text-white")}>
            {done[i] ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
          </span>
          {text}
        </li>
      ))}
    </ol>
  );
}

const TONE = { risk: "before:bg-risk text-risk", safe: "before:bg-safe text-safe", ok: "before:bg-ok text-ok", warn: "before:bg-warn text-warn", none: "before:bg-input" };
export function Kpi({ tone = "none", value, label }: { tone?: keyof typeof TONE; value: ReactNode; label: ReactNode }) {
  return (
    <Card className={cn("relative flex flex-col gap-1.5 overflow-hidden p-4 pl-5 before:absolute before:inset-y-0 before:left-0 before:w-1", TONE[tone])}>
      <div className="big-number flex flex-wrap items-baseline gap-2 text-[34px] leading-none">{value}</div>
      <div className="text-[13px] text-muted-foreground">{label}</div>
    </Card>
  );
}
export const Kpis = ({ children }: { children: ReactNode }) => <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-3">{children}</div>;

/** What a column holds, from the scan (empty before the scan). */
export function useRole() {
  const columns = useApp(s => s.scan?.detections.columns);
  return (table: string, column: string) => columns?.find(c => c.table === table && c.column === column)?.privacy_role ?? "";
}
/** A value as shown on screen: always as it is in the data (the app runs on this computer only). */
export function useShown() {
  return (_table: string, _column: string, v: unknown) => String(v ?? "");
}

/** column → value rows, used by the attack replay and its trail. */
export function Facts({ facts, table, tone }: { facts: Record<string, string>; table: string; tone?: "risk" | "safe" }) {
  const shown = useShown(), role = useRole();
  return (
    <div className="flex flex-col">
      {Object.entries(facts).map(([k, v]) => (
        <div key={k} className="flex min-w-0 justify-between gap-3 border-b border-dashed py-1 text-[13px]">
          <span className="truncate font-mono text-xs text-muted-foreground">{k}</span>
          <b className={cn("text-right font-semibold [overflow-wrap:anywhere]", tone === "risk" && "text-risk", tone === "safe" && "text-safe", !tone && ROLE_TONE[role(table, k)])}>
            {clip(shown(table, k, v), 80) || "–"}
          </b>
        </div>
      ))}
    </div>
  );
}

/** One card for every long wait: real percentages for uploads, elapsed time for work on the computer. */
export function ProgressCard() {
  const p = useApp(s => s.progress);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t); }, []);
  if (!p) return null;
  return (
    <Card className="flex flex-col gap-3 border-safe/40 p-5">
      <div className="flex items-center justify-between gap-3"><h2 className="text-xl">{p.title}</h2><span className="font-mono text-sm text-muted-foreground">{Math.round((Date.now() - p.started) / 1000)} s</span></div>
      <Progress value={p.pct} />
      <p className="text-sm text-muted-foreground">{p.detail}</p>
      {p.checks && <ul className="flex flex-col gap-1.5 text-[13.5px] text-muted-foreground">{p.checks.map(c => <li key={c} className="flex items-baseline gap-2.5"><span className="size-1.5 shrink-0 rounded-full bg-safe" />{c}</li>)}</ul>}
    </Card>
  );
}

export const Section = ({ eyebrow, title, right, children, className }: { eyebrow?: ReactNode; title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) => (
  <Card className={cn("flex flex-col gap-4 p-5", className)}>
    {(eyebrow || title || right) && (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h2 className="text-xl leading-tight">{title}</h2>}</div>
        {right}
      </div>
    )}
    {children}
  </Card>
);
