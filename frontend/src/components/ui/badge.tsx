import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      default: "border-transparent bg-primary text-primary-foreground",
      outline: "text-muted-foreground",
      risk: "border-risk/40 bg-risk-soft text-risk",
      safe: "border-safe/40 bg-safe-soft text-safe",
      warn: "border-warn/40 bg-warn-soft text-warn",
      ok: "border-ok/40 bg-ok-soft text-ok",
    },
  },
  defaultVariants: { variant: "outline" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}
export const Badge = ({ className, variant, ...props }: BadgeProps) => <span className={cn(badgeVariants({ variant }), className)} {...props} />;
