# Detection

Step 1 of the PETs Transformer: work out what every column holds, how sure we are, and why it matters.
Owner: Hari (with Chinedu for free text). See the team build plan, pages 5–10.

## What it produces

For every column of a table, one record:

| Field | Meaning |
|---|---|
| `privacy_role` | One of the 7 roles in `metadata/taxonomy.md` (direct identifier, quasi-identifier, sensitive attribute, technical identifier, free text, record key, non-sensitive) |
| `subtype` | One of the taxonomy subtypes, e.g. `NATIONAL_ID`, `BIRTH_DATE`, `DIAGNOSIS_CODE` |
| `sure` | 0–1. How strongly the evidence agrees |
| `method` | `rule` (format checks and value statistics), `name` (column-name hint only) or `llm` (local model, only where rules are unsure) |
| `evidence` | What fired, in plain words: "97 % of 200 samples pass the HETU check character" |
| `basis` | Why that role: the rule, law or standard behind it (see `SOURCES.md`) |
| `needed_by` | Utility tasks that use this column, so the plan protects it instead of dropping it |

Two outputs: `detection.json` (the shared team file, with evidence) and a CSV
`dataset,table,column,privacy_role,subtype` that `pets-eval detect` scores.

## Principles

1. **Values first, names second.** The unseen HR file has columns named `c01…c26`, so detection must work from
   values alone. Column names only raise or lower confidence.
2. **Every label is explained.** No label without evidence and a basis.
3. **Role and usefulness are separate.** Detection says what a column *is*; it also records which analyses
   *need* it. Deciding the protection is the plan's job.
4. **Measured honestly.** We develop on 5 datasets and report the final score on 4 held-out ones, plus a
   "names hidden" score that simulates the unseen file. See `DECISIONS.md` D2.
5. **Local AI only, and only where rules are unsure** (team plan, page 5).

## Files

- `SOURCES.md`: every rule, law and standard we rely on, and what we took from it
- `DECISIONS.md`: each design decision with options, reason and source
- `SCORES.md`: every measured iteration, from the organisers' baseline onwards
