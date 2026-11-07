// Describe a receiver of your own (who, why, trust level, what they need) when no ready-made one fits.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox, Input, Label, Select } from "@/components/ui/form";
import { Spinner, TableWrap, Td, Th } from "@/components/ui/misc";
import type { Column } from "@/lib/api";
import { ROLE_LABEL, ROLE_TONE, words } from "@/lib/format";
import { TIME_UNITS } from "@/lib/lanes";
import { makePlan, useApp } from "@/lib/store";

export function CustomReceiver({ onClose }: { onClose: () => void }) {
  const cat = useApp(s => s.cat!), columns = useApp(s => s.scan!.detections.columns), busy = useApp(s => s.busy === "plan");
  const det = columns.filter(c => c.privacy_role !== "record_key");
  const [C, setC] = useState({ recipient: "Partner organisation", purpose: "Analysis agreed in the data-sharing contract", trust_level: "contractual", k: 5, epsilon: 1, rows_per_person: 3 });
  const [needs, setNeeds] = useState<Record<string, string>>({}), [stats, setStats] = useState<string[][]>([["", "", ""]]), [error, setError] = useState("");
  const pub = C.trust_level === "public";
  const detail = (c: Column, forStats: boolean) => ["TIMESTAMP", "DATE"].includes(c.subtype) ? TIME_UNITS : c.subtype === "BIRTH_DATE" ? ["age_band"]
    : forStats && c.subtype === "DIAGNOSIS_CODE" && cat.codelists.includes("diagnosis_group") ? ["diagnosis_group"] : [""];
  const find = (key: string) => det.find(c => `${c.table}.${c.column}` === key)!;
  const submit = async () => {
    const id = "CUSTOM-" + (C.recipient.toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24) || "RECEIVER");
    const base = { id, title: C.purpose, recipient: C.recipient, purpose: C.purpose, trust_level: C.trust_level, threat_model: "Outsider linking with public, social and leaked sources" };
    let custom;
    if (pub) {
      const statistics = stats.map(s => s.filter(Boolean)).filter(s => s.length).map((s, i) => {
        const by = s.map(key => { const c = find(key); return { table: c.table, column: c.column, detail: detail(c, true)[0] || null }; });
        return { name: `table_${i + 1}_by_${by.map(b => b.column.toLowerCase().replace(/[^a-z0-9]+/g, "_")).join("_")}`, table: by[0].table, by: by.map(({ column, detail }) => ({ column, detail })) };
      });
      if (!statistics.length) return setError("Choose at least one column to count by.");
      custom = { ...base, statistics, targets: { epsilon: +C.epsilon, rows_per_person: +C.rows_per_person } };
    } else {
      const list = Object.entries(needs).map(([key, d]) => { const c = find(key); return { table: c.table, column: c.column, detail: d || null }; });
      if (!list.length) return setError("Tick at least one column the receiver needs.");
      custom = { ...base, needs: list, targets: { k: +C.k } };
    }
    if (await makePlan({ custom }, "custom")) onClose();
  };
  const field = (label: string, key: "recipient" | "purpose") => <div className="flex flex-col gap-1.5"><Label>{label}</Label><Input value={C[key]} onChange={e => setC({ ...C, [key]: e.target.value })} /></div>;
  const usable = det.filter(c => ["quasi_identifier", "sensitive_attribute", "non_sensitive"].includes(c.privacy_role));
  return (
    <Dialog open onOpenChange={o => !o && onClose()}>
      <DialogContent wide>
        <DialogHeader><DialogTitle>Describe the receiver</DialogTitle></DialogHeader>
        <DialogBody>
          <div className="grid gap-3 md:grid-cols-3">{field("Receiver", "recipient")}{field("Purpose", "purpose")}
            <div className="flex flex-col gap-1.5"><Label>How far they are trusted</Label>
              <Select value={C.trust_level} onChange={e => setC({ ...C, trust_level: e.target.value })}>{cat.trust_levels.map(t => <option key={t} value={t}>{words(t)}</option>)}</Select></div>
          </div>
          {pub ? <>
            <p className="text-sm text-muted-foreground">Public receivers get counts only, with noise added (differential privacy). No rows leave.</p>
            <div className="flex flex-wrap items-center gap-2 text-sm">Budget ε <Input className="w-20" value={C.epsilon} onChange={e => setC({ ...C, epsilon: +e.target.value })} />
              count each person at most <Input className="w-16" value={C.rows_per_person} onChange={e => setC({ ...C, rows_per_person: +e.target.value })} /> times</div>
            {stats.map((s, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 text-sm">Table {i + 1}: count by
                {[0, 1, 2].map(j => <Select key={j} value={s[j]} onChange={e => setStats(stats.map((x, k) => k === i ? x.map((y, m) => m === j ? e.target.value : y) : x))}>
                  <option value="">—</option>{usable.map(c => <option key={`${c.table}.${c.column}`} value={`${c.table}.${c.column}`}>{c.table}.{c.column}</option>)}</Select>)}</div>
            ))}
            <div><Button size="sm" variant="outline" onClick={() => setStats([...stats, ["", "", ""]])}>Add a table</Button></div>
          </> : <>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">Tick what they need; everything else stays here. Each person must look like at least
              <Input className="w-16" value={C.k} onChange={e => setC({ ...C, k: +e.target.value })} /> others.</div>
            <TableWrap><table className="w-full border-collapse"><thead><tr><Th /><Th>Column</Th><Th>What it is</Th><Th>Detail</Th></tr></thead>
              <tbody>{det.map(c => {
                const key = `${c.table}.${c.column}`, opts = detail(c, false), on = key in needs;
                return <tr key={key}><Td><Checkbox checked={on} onCheckedChange={v => { const n = { ...needs }; if (v) n[key] = opts[0]; else delete n[key]; setNeeds(n); }} aria-label={`Needs ${key}`} /></Td>
                  <Td className="font-mono">{key}</Td><Td className={ROLE_TONE[c.privacy_role]}>{ROLE_LABEL[c.privacy_role]}</Td>
                  <Td>{opts[0] && <Select value={needs[key] ?? opts[0]} onChange={e => on && setNeeds({ ...needs, [key]: e.target.value })}>{opts.map(o => <option key={o}>{o}</option>)}</Select>}</Td></tr>;
              })}</tbody></table></TableWrap>
          </>}
          {error && <p className="text-sm font-medium text-risk">{error}</p>}
        </DialogBody>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={busy} onClick={submit}>{busy && <Spinner className="text-current" />}Make the plan</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
