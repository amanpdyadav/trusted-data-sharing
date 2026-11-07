# User guide

This guide walks through the web app. Start it with `make web` and open http://127.0.0.1:8765.

The bar at the top of the screen always shows which step you are on and the next thing to do (top right).
The switch **Hide personal values on screen** (left, on by default) masks names, ID codes and free text, so you
can share your screen safely. It only changes what you see, not the data. Next to it, **Light / Dark / Auto** sets the
colours (light by default; Auto follows your computer's setting).

## 1. Data

Bring the tables you want to share:

- **Upload:** drop CSV files or one ZIP of CSV files. Each file becomes a table; the file name is the table name.
- **Example:** pick one of the synthetic datasets from the challenge package.
- **Earlier work:** open a dataset from **Your workspace**. Your scan, plan and releases come back as you left them.

When the files are read, the page shows a **Dataset ready** card with the number of tables, rows and columns.
Click **Scan for risks**.

## 2. Risk scan

The scan reads every column and shows what could go wrong if the data were shared as it is.

- **Headline tiles:** how many people can be singled out, how many columns match outside sources (public
  registers, social media, leaked lists), how many tables are joined, and whether there is special category data
  (GDPR Article 9, for example health data).
- **Attack replay:** an outsider knows a few everyday facts about one person (for example birth date, sex,
  postcode). The tool shows that these facts fit exactly one person, which reveals their name and ID code.
  Click **Play the attack** to watch it again, or **Another person** to attack someone else.
- **Follow the trail:** from the first table, each arrow follows a key (for example `visit_id`) into the next
  table, and each card shows what that table gives away. This is the mosaic effect.
- **How your data connects:** a map of the tables, the keys that join them, and the columns an outsider could match.
- **Tabs below:** exposure per table, one person's full file, and **What each column is**.

**If a column is labelled wrong,** open it with **Details** in **What each column is**, and change what it is
(for example from "harmless" to "sensitive fact"). Your correction is saved with your name and the plan follows it.

## 3. Receiver & plan

Choose who gets the data. The receiver decides how strong the protection must be.

- **A preset receiver**, for example a research group under contract (gets coded rows) or the public (gets noisy
  statistics only).
- **Describe your own:** name the receiver, the purpose, how far they are trusted, and tick the columns they need.
  For a public receiver, choose what to count instead.

The plan lists every column, grouped by table, with its protection and the reason. You can change a protection
in the list. Two tabs help you choose:

- **Privacy versus usefulness:** what each value of k or ε (epsilon) would cost, computed on your data without
  releasing anything. Click a value of k to use it.
- **Same data, other receivers:** what each receiver would get from the same columns.

## 4. Review & approve

Click **Review and approve**. The dialog lists every column that leaves, the tables that stay here, and any
questions a person must check. Tick that you checked them, type your name and approve. The approval is written
into the plan and into every release.

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
