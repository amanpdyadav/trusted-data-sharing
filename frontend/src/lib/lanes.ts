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

export const TIME_UNITS = ["week", "month", "day", "hour", "time_of_day"];
export const RECEIVER_ICON: Record<string, string> = { public: "🌍", controlled_research: "🎓", contractual: "🤝", internal: "🏢" };
