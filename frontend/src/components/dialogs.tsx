// Two dialogs used across the app: type a name (rename, duplicate), and confirm (remove, delete).
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/form";
import { Spinner } from "@/components/ui/misc";
import { useApp } from "@/lib/store";

type Open = { open: boolean; onOpenChange: (open: boolean) => void };

export function NameDialog({ open, onOpenChange, title, label, initial, hint, intro, action, busyKey, onSubmit }: Open & {
  title: string; label: string; initial: string; hint?: string; intro?: ReactNode; action: string; busyKey: string;
  onSubmit: (name: string) => Promise<boolean | undefined>;
}) {
  const [name, setName] = useState(initial), busy = useApp(s => s.busy === busyKey);
  useEffect(() => { if (open) setName(initial); }, [open, initial]);
  const submit = async () => { if (await onSubmit(name.trim())) onOpenChange(false); };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <DialogBody>
          {intro && <p className="text-sm">{intro}</p>}
          <div className="flex flex-col gap-1.5"><Label htmlFor="name-input">{label}</Label>
            <Input id="name-input" value={name} autoFocus onChange={e => setName(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()} /></div>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !name.trim()}>{busy && <Spinner className="text-current" />}{action}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ConfirmDialog({ open, onOpenChange, title, action, danger, onConfirm, children }: Open & {
  title: string; action: string; danger?: boolean; onConfirm: () => Promise<unknown>; children: ReactNode;
}) {
  const busy = useApp(s => s.busy === "confirm");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <DialogBody><p className="text-sm">{children}</p></DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={danger ? "risk" : "default"} disabled={busy} onClick={async () => { await onConfirm(); onOpenChange(false); }}>{busy && <Spinner className="text-current" />}{action}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
