// Small form controls: Input, Select, Label, Checkbox, Slider (Radix underneath).
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as LabelPrimitive from "@radix-ui/react-label";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { Check } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("flex h-9 w-full rounded-lg border border-input bg-card px-3 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...p} />
));
Input.displayName = "Input";

/** A native drop-down styled like Input. */
export const Select = ({ className, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn("h-9 rounded-lg border border-input bg-card px-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...p} />
);

export const Label = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>) => (
  <LabelPrimitive.Root className={cn("text-sm font-medium", className)} {...p} />
);

export const Checkbox = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>) => (
  <CheckboxPrimitive.Root
    className={cn("peer size-5 shrink-0 rounded-md border border-input bg-card shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:border-ok data-[state=checked]:bg-ok data-[state=checked]:text-white", className)}
    {...p}
  >
    <CheckboxPrimitive.Indicator className="flex items-center justify-center"><Check className="size-3.5" strokeWidth={3} /></CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
);

export const Slider = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>) => (
  <SliderPrimitive.Root className={cn("relative flex w-full touch-none select-none items-center py-2", className)} {...p}>
    <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-full bg-muted ring-1 ring-border">
      <SliderPrimitive.Range className="absolute h-full bg-safe" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb aria-label={p["aria-label"]} className="block size-5 rounded-full border-2 border-safe bg-card shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
  </SliderPrimitive.Root>
);
