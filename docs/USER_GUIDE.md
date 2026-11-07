# User guide

This guide walks through the web app. Start it with `make web` and open http://127.0.0.1:8765.

The bar at the top of the screen always shows which step you are on and the next thing to do (top right).
Values are always shown as they are in your data: the app runs on this computer only. Bottom left,
**Light / Dark / Auto** sets the colours (light by default; Auto follows your computer's setting).

## 1. Data

Bring the tables you want to share:

- **Upload:** drop CSV files or one ZIP of CSV files. Each file becomes a table; the file name is the table name.
- **Example:** pick one of the synthetic datasets from the challenge package.
- **Earlier work:** open a dataset from **Your workspace**. Your scan, plan and releases come back as you left them.

When the files are read, the page shows a **Dataset ready** card with the number of tables, rows and columns.

**Columns without a name.** If a table has blank headers, codes like `c07`, or no header row at all, a note above
the table says so. **Name the columns** opens a dialog that lists only those columns (columns that have a name are
never renamed). Format checks fill in what they are sure of (ID codes, IBANs, phones, emails, plates ...). When the
local AI is on, the button reads **Suggest names** and the AI suggests the rest from a short summary of each column:
a few sample values, never the whole table. Change any name, keep an original header, or ask again for one column;
nothing changes until **Use these names**. If the first row looks like data, **Read the first row as data** fixes
it. The release uses the new names, and the manifest keeps the original headers.

Click **Scan for risks**.

## 2. Risk scan

The scan reads every column and shows what could go wrong if the data were shared as it is.

- **Headline tiles:** how many people can be singled out, how many columns match outside sources (public
  registers, social media, leaked lists), how many tables are joined, and whether there is special category data
  (GDPR Article 9, for example health data).
- **How your data connects:** a map of the tables, the keys that join them, and the columns an outsider could match.
- **Attack replay:** an outsider knows a few everyday facts about one person (for example birth date, sex,
  postcode). The tool shows that these facts fit exactly one person, which reveals their name and ID code.
  Click **Play the attack** to watch it again, or **Another person** to attack someone else.
- **Follow the trail:** from the first table, each arrow follows a key (for example `visit_id`) into the next
  table, and each card shows what that table gives away. This is the mosaic effect.
- **Tabs below:** exposure per table, one person's file (facts that repeat in every record shown once, grouped by
  what they give away, then what changes from record to record), and **What each column is**.

**If a column is labelled wrong,** open it with **Details** in **What each column is**, and change what it is
(for example from "harmless" to "sensitive fact"). Your correction is saved with your name and the plan follows it.

## 3. Receiver & plan

Each step starts with a short "what to do here" strip. On this step:

1. **Pick who gets the data.** Each card says what that receiver gets: individual records (protected) or only
   counts. Choose **Someone else** to describe your own receiver and tick the columns they need.
2. **Check what they will receive.** Every column sits in one of five lanes:
   ✓ Shared as is · 🔍 Made less exact · 🔒 Replaced by a code · 📝 Personal details hidden · ✂ Removed.
   Below the lanes, **One record, now and as they will see it** shows a real record (the person from the attack)
   before and after, for example `1958-02-07 → 60-69`.
3. **Change anything that looks wrong.** Click a column to see why it was chosen and pick another way to share
   it. Columns marked ⚠ need your decision.

**Protection level** shows, as a slider, how many look-alikes each person has. Moving it shows the chance that an
outsider picks the right person and how many details the receiver keeps. Click **Use this level** to apply it.

## 4. Review & approve

Two tiles sum up what **leaves your organisation** and what **stays on this computer**. Below them, the tables
are listed on the left (all selected; search, filter or tick the ones you want) and their fields on the right,
each with what happens to it: shared as is, made less exact, replaced by a code, removed, counted only, or stays
here. Tick the checks
(the receiver needs the data, any undecided columns were checked, you may approve), type your full name and click
**Approve and continue**. The button only unlocks when every check is ticked. Your name is written into the plan
and into every release.

## 5. Release & proof

Click **Create the release** and give the receiver's name. Each receiver gets codes from a different key, so two
receivers cannot join their copies.

The proof page shows:

- **The same attack on the release:** the outsider with the same facts now faces many equally likely people and
  no name, ID code or contact details. The verdict says **Attack fails** or, if not, what to change.
- **Records before → after:** released rows under the records they came from. Click a pair to see it in full.
- **Column changes, attacker's view, free text, statistics accuracy and remaining risks.**
- **History & compare:** every release you made. Tick two to compare them side by side.

Click **Download release** to get the ZIP. For statistics, the download asks first, because publishing spends
privacy budget (ε).

## Show the risk

Two pages in the sidebar, outside the five steps:

- **Release audit.** *Your releases*: every release made in the app, from every dataset, with who it was for, who
  approved it, what was done to each column and why, the attack before and after, the risk left and the
  fingerprint of every shared file. *Receivers benchmark*: how the automatic planner does for each of the
  challenge's 27 receivers, next to the organisers' baselines (B0, B2, B2-k), with a filter for the receivers
  that fit the data you have open.
- **Mosaic attack.** On the challenge's hospital data: how many public posts and news clips single out one patient
  once names are removed, and how many still do on your release. Pick one and follow it into the bank, energy,
  transport and school data, with raw data, names removed and your release side by side. It appears once its
  data is built (`make screens`, see the runbook).

## Glossary

| Term | Meaning |
|---|---|
| Direct identifier | A value that names a person on its own: name, ID code, phone, email, address |
| Quasi-identifier | A value that is harmless alone but identifies people in combination: birth date, sex, postcode, town |
| Sensitive attribute | What must not be linked to a person: diagnosis, grades, income |
| Singled out | Nobody else in the data shares the person's quasi-identifiers, so anyone who knows them finds the person |
| k-anonymity | Every person looks like at least k−1 others on the quasi-identifiers |
| Pseudonymise | Replace an identifier with a keyed code (HMAC, Hash-based Message Authentication Code). Same person, same code; without the key the code cannot be reversed |
| Generalise | Make a value coarser: birth date → age band, timestamp → hour, diagnosis code → first 3 characters |
| Suppress | Blank a value or remove a row so that every row has look-alikes |
| Differential privacy (DP) | Add calibrated random noise to published counts, so no single person changes the result much |
| ε (epsilon) | The privacy budget of differential privacy: smaller means more noise and more privacy |
| Mosaic effect | Pieces that are harmless alone identify a person when put together across tables |
| Row map | The private list of which released row came from which original record. It never leaves your computer |
| Manifest | `manifest.json` in the release: what was done, who approved it, file fingerprints and the remaining risks |
| GDPR | General Data Protection Regulation (EU) |
