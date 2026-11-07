import * as T from "@radix-ui/react-toggle-group";
import * as React from "react";
import { cn } from "@/lib/utils";

/** A row of mutually exclusive choices (segmented control). */
export const ToggleGroup = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.Root>) => (
  <T.Root className={cn("inline-flex rounded-lg border bg-muted p-0.5", className)} {...p} />
);
export const ToggleGroupItem = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.Item>) => (
  <T.Item className={cn("rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-sm", className)} {...p} />
);
