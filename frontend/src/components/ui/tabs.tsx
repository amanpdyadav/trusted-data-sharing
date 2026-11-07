import * as T from "@radix-ui/react-tabs";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export const TabsList = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.List>) => (
  <T.List className={cn("flex gap-1 overflow-x-auto border-b", className)} {...p} />
);
export const TabsTrigger = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.Trigger>) => (
  <T.Trigger
    className={cn("-mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 border-transparent px-3.5 py-2.5 text-sm font-medium text-muted-foreground hover:text-foreground data-[state=active]:border-foreground data-[state=active]:text-foreground", className)}
    {...p} />
);
export const TabsContent = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.Content>) => (
  <T.Content className={cn("pt-4 focus-visible:outline-none", className)} {...p} />
);
