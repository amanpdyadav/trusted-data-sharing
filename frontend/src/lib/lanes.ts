// How a column can be shared, in plain words. One entry per protection technique.
export type Lane = { technique: string; icon: string; name: string; help: string };

export const LANES: Lane[] = [
  { technique: "keep", icon: "✓", name: "Shared as is", help: "The receiver sees the real value." },
  { technique: "generalise", icon: "🔍", name: "Made less exact", help: "Rounded or grouped: a birth date becomes an age group, a time becomes an hour." },
  { technique: "pseudonymise", icon: "🔒", name: "Replaced by a code", help: "The same person always gets the same code; the real value stays here." },
  { technique: "redact_text", icon: "📝", name: "Personal details hidden", help: "Names, numbers and addresses inside the text are blacked out." },
  { technique: "drop", icon: "✂", name: "Removed", help: "Not shared at all." },
];
export const laneOf = (technique: string) => LANES.find(l => l.technique === technique) ?? LANES[0];

/** Badge colour for a protection: dropped in red, kept or withheld as is, anything that changes the value in blue. */
export const techniqueTone = (technique: string): "risk" | "outline" | "safe" =>
  technique === "drop" ? "risk" : technique === "keep" || technique === "withheld" ? "outline" : "safe";

/** The tables a plan releases as rows, in plan order. */
export const planTables = (plan: { actions: { table: string }[] }) => [...new Set(plan.actions.map(a => a.table))];

export const TIME_UNITS = ["week", "month", "day", "hour", "time_of_day"];
export const RECEIVER_ICON: Record<string, string> = { public: "🌍", controlled_research: "🎓", contractual: "🤝", internal: "🏢" };
