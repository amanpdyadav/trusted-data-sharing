// A line-by-line diff (longest common subsequence), enough for plan files of a few hundred lines.
export type DiffLine = { kind: "same" | "added" | "removed"; text: string; a?: number; b?: number };

export function lineDiff(before: string, after: string): DiffLine[] {
  const A = before.split("\n"), B = after.split("\n"), n = A.length, m = B.length;
  const lcs = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) lcs[i][j] = A[i] === B[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const out: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { out.push({ kind: "same", text: A[i], a: i + 1, b: j + 1 }); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { out.push({ kind: "removed", text: A[i], a: i + 1 }); i++; }
    else { out.push({ kind: "added", text: B[j], b: j + 1 }); j++; }
  }
  while (i < n) { out.push({ kind: "removed", text: A[i], a: i + 1 }); i++; }
  while (j < m) { out.push({ kind: "added", text: B[j], b: j + 1 }); j++; }
  return out;
}

/** Keep changed lines with a little context; long unchanged runs fold into one "… n unchanged lines" marker. */
export function foldUnchanged(lines: DiffLine[], context = 3): (DiffLine | { kind: "fold"; count: number })[] {
  const keep = lines.map((l, i) => l.kind !== "same" || lines.slice(Math.max(0, i - context), i + context + 1).some(x => x.kind !== "same"));
  const out: (DiffLine | { kind: "fold"; count: number })[] = [];
  let skipped = 0;
  lines.forEach((l, i) => {
    if (keep[i]) { if (skipped) { out.push({ kind: "fold", count: skipped }); skipped = 0; } out.push(l); }
    else skipped++;
  });
  if (skipped) out.push({ kind: "fold", count: skipped });
  return out;
}
