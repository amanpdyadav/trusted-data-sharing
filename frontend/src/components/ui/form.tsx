// Small form controls: Input, Label, Checkbox, Switch, Slider (Radix underneath).
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as LabelPrimitive from "@radix-ui/react-label";
import * as SliderPrimitive from "@radix-ui/react-slider";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { Check } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("flex h-9 w-full rounded-lg border border-input bg-card px-3 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...p} />
));
Input.displayName = "Input";

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

export const Switch = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>) => (
  <SwitchPrimitive.Root
    className={cn("inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent bg-input transition-colors data-[state=checked]:bg-safe", className)}
    {...p}
  >
    <SwitchPrimitive.Thumb className="block size-4 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-4" />
  </SwitchPrimitive.Root>
);

export const Slider = ({ className, ...p }: React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>) => (
  <SliderPrimitive.Root className={cn("relative flex w-full touch-none select-none items-center py-2", className)} {...p}>
    <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-full bg-muted ring-1 ring-border">
      <SliderPrimitive.Range className="absolute h-full bg-safe" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb aria-label={p["aria-label"]} className="block size-5 rounded-full border-2 border-safe bg-card shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
  </SliderPrimitive.Root>
);
