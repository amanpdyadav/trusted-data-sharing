import * as M from "@radix-ui/react-dropdown-menu";
import * as React from "react";
import { cn } from "@/lib/utils";

export const DropdownMenu = M.Root;
export const DropdownMenuTrigger = M.Trigger;

export const DropdownMenuContent = React.forwardRef<React.ElementRef<typeof M.Content>, React.ComponentPropsWithoutRef<typeof M.Content>>(
  ({ className, sideOffset = 6, ...props }, ref) => (
    <M.Portal>
      <M.Content ref={ref} sideOffset={sideOffset} align="end"
        className={cn("z-50 min-w-[11rem] overflow-hidden rounded-xl border bg-popover p-1 text-popover-foreground shadow-lg data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95", className)}
        {...props} />
    </M.Portal>
  ),
);
DropdownMenuContent.displayName = "DropdownMenuContent";

export const DropdownMenuItem = React.forwardRef<React.ElementRef<typeof M.Item>, React.ComponentPropsWithoutRef<typeof M.Item> & { danger?: boolean }>(
  ({ className, danger, ...props }, ref) => (
    <M.Item ref={ref}
      className={cn("flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none focus:bg-accent data-[disabled]:pointer-events-none data-[disabled]:opacity-45 [&_svg]:size-4",
        danger && "text-risk focus:bg-risk-soft", className)}
      {...props} />
  ),
);
DropdownMenuItem.displayName = "DropdownMenuItem";
export const DropdownMenuSeparator = ({ className }: { className?: string }) => <M.Separator className={cn("-mx-1 my-1 h-px bg-border", className)} />;
