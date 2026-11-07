import * as A from "@radix-ui/react-accordion";
import { ChevronRight } from "lucide-react";
import * as React from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const Accordion = A.Root;
export const AccordionItem = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof A.Item>) => (
  <A.Item className={cn("overflow-hidden rounded-xl border bg-card", className)} {...p} />
);
export const AccordionTrigger = ({ className, children, right, ...p }: React.ComponentPropsWithoutRef<typeof A.Trigger> & { right?: ReactNode }) => (
  <A.Header className="flex">
    <A.Trigger
      className={cn("group flex flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-muted data-[state=open]:border-b", className)}
      {...p}
    >
      <span className="flex min-w-0 items-center gap-2.5">
        <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        {children}
      </span>
      {right && <span className="text-sm text-muted-foreground">{right}</span>}
    </A.Trigger>
  </A.Header>
);
export const AccordionContent = ({ className, children, ...p }: React.ComponentPropsWithoutRef<typeof A.Content>) => (
  <A.Content className="overflow-hidden" {...p}>
    <div className={cn("flex flex-col gap-3 p-4", className)}>{children}</div>
  </A.Content>
);
