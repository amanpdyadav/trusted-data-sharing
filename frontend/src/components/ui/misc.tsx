// Small display pieces shared by every step: meters, progress bars, tables, tooltips, a spinner.
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Spinner = ({ className }: { className?: string }) => <Loader2 className={cn("size-4 animate-spin text-safe", className)} aria-label="working" />;

/** A thin bar: value 0..1. */
export const Meter = ({ value, tone = "risk", className }: { value: number; tone?: "risk" | "safe" | "ok"; className?: string }) => (
  <div className={cn("h-2 overflow-hidden rounded-full bg-muted ring-1 ring-border", className)}>
    <div className={cn("h-full rounded-full", { risk: "bg-risk", safe: "bg-safe", ok: "bg-ok" }[tone])} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
  </div>
);

export const Progress = ({ value }: { value: number | null }) => (
  <div className="relative h-2.5 overflow-hidden rounded-full bg-muted ring-1 ring-border">
    {value == null
      ? <div className="absolute h-full w-1/3 animate-[slide_1.3s_ease-in-out_infinite] rounded-full bg-safe" style={{ animationName: "slide" }} />
      : <div className="h-full rounded-full bg-safe transition-[width]" style={{ width: `${value * 100}%` }} />}
    <style>{"@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(300%)}}"}</style>
  </div>
);

export const TableWrap = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("max-h-[480px] max-w-full overflow-auto rounded-xl border bg-card", className)} {...p} />
);
export const Th = ({ className, ...p }: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th className={cn("sticky top-0 z-[1] whitespace-nowrap border-b bg-muted px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.05em] text-muted-foreground", className)} {...p} />
);
export const Td = ({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) => (
  <td className={cn("border-b px-3 py-2 align-top text-[13px] [overflow-wrap:anywhere]", className)} {...p} />
);

export const TooltipProvider = TooltipPrimitive.Provider;
export function Tip({ text, children }: { text: React.ReactNode; children: React.ReactNode }) {
  return (
    <TooltipPrimitive.Root delayDuration={200}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content sideOffset={6} className="z-50 max-w-xs rounded-lg bg-primary px-3 py-1.5 text-xs text-primary-foreground shadow-md">{text}</TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
