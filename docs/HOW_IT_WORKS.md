# How it works

One pipeline, used the same way by the web app and the command line:

```
tables ──> detect ──> risk scan ──> plan ──> approve ──> transform ──> assess ──> release
           (what is    (who can be   (one       (a named   (apply the    (prove it)   (files +
            in each     found, how    protection  person)    plan)                     manifest)
            column)     tables link)  per column)
```

Each step is its own package in `src/pets_transformer/`, and steps talk through typed files (`contracts/`):
`detection.json`, `plan.yaml`, `manifest.json`.

## 0. Name what has no name (`columns.py`, optional)

A table may arrive with blank headers, codes like `c07`, or no header row. Those columns, and only those, can be
named before the scan. Format checks name what they are sure of; the local AI, when it is on and a person asks,
suggests the rest from a short summary per column (profile, at most 8 short sample values, the neighbouring names;
8 columns per call, about 2,000 tokens at most). A person confirms every name. The names are applied when the
tables are read (`NamedSource`), recorded in the plan and the manifest with the original header and who suggested
them, and the release uses them.

## 1. Detect (`detect/`, `text/`)

Every column gets a **privacy role** (direct identifier, quasi-identifier, sensitive attribute, free text,
record key, harmless) and a **type** (person name, national ID, phone, birth date, diagnosis code, …), with the
evidence written down.

- **Rules first:** column names, value shapes and check digits (Finnish personal identity code, IBAN
  (International Bank Account Number), payment cards), phone formats, name lists, dates, code sets.
- **Two detectors, one answer:** a rule-based detector and a layered detector (values first: trade-union words,
  health context from diagnosis codes, people tables) label every column; where they disagree, the stronger
  evidence wins. Labels cite the law or standard behind them. Details and scores: `docs/detection/`.
- **Free text:** finds names, ID codes, phones, emails, addresses and secrets inside notes and chat messages,
  including spoken or spelled-out numbers and emails (Finnish, Swedish, English).
- A person can correct any column; the correction is kept as evidence.

## 2. Risk scan (`assess/riskscan.py`, `assess/attack.py`)

Uses only the data itself, so it works on any company's files:

- **Links:** columns whose values are another table's key (for example `visit_id` in lab results).
- **Exposure:** per table, the share of people who are **singled out** on their quasi-identifiers.
- **Attack replay:** picks a person the way an attacker would (someone in a well-connected table), takes their
  everyday facts (birth date, sex, postcode, town), and counts how many people fit. If one fits, it shows what
  that reveals.
- **Trail:** follows the keys from that person's rows into every linked table, both ways and over several hops,
  and lists what each table gives away.

## 3. Plan (`plan/`)

A **scenario** (YAML in `scenarios/`) describes the receiver: who, why, how far they are trusted, which columns
they need, and the privacy targets (k for rows, ε for statistics). The planner turns detections + scenario into
one protection per column, each with a reason:

| Column | Typical protection |
|---|---|
| Not needed by the receiver | Drop (data minimisation) |
| Direct identifier needed as a link | Pseudonymise with a keyed code (HMAC-SHA256), one key per receiver |
| Direct identifier not needed | Drop |
| Quasi-identifier | Generalise (age band, hour, 3-character code) and check k together |
| Free text | Redact personal details (`[PERSON]`, `[PHONE]`, …) |
| Public receiver | No rows: noisy statistics only (differential privacy) |

Anything the rules cannot decide is marked **REVIEW** and must be checked by a person before approval.

## 4. Approve

A plan without a named approver cannot run. The approval is stored in the plan and copied into the manifest.

## 5. Transform (`transform/`, `aggregate/`)

- **Pseudonymise:** HMAC (Hash-based Message Authentication Code) with a key derived per receiver and month from
  `PETS_MASTER_KEY`. Two receivers cannot join their copies.
- **Generalise:** dates to age bands or time units, codes to their first characters or to groups (`codelists/`).
- **Suppress:** blanks quasi-identifier values one column at a time (and removes rows if that is not enough)
  until every row has at least k−1 look-alikes.
- **Redact:** replaces personal details in free text with labels.
- **Statistics:** counts with discrete Laplace noise, each person's contribution bounded, every cell published
  (so empty cells reveal nothing), and the privacy budget recorded in a ledger per receiver with a cap.
- Rows are shuffled with a secret seed, so the order reveals nothing.

## 6. Assess (`assess/`)

The proof is computed on your data, not from answer files:

- **Attacker's view:** share of people singled out and the average chance to guess the right person, before
  and after.
- **The same attack on the release:** the same person, the same facts, followed through the private row map.
- **Usefulness:** values kept per column, and for statistics the error against the exact numbers.
- **Remaining risks:** written into the manifest in plain words.

## 7. Release (`report/`, `pipeline.py`)

```
out/<name>/release/   protected tables + manifest.json   → may be shared
out/<name>/private/   rowmap_<table>.csv                 → never leaves this computer
```

The manifest holds the approved plan (with the approver's name), a SHA-256 fingerprint of the input and of each
file, the key domain (never the key), the measured results and the remaining risks. The release stops if the plan
is not approved or if any column has no decision: every column needs keep, drop or a protection.

## Safety rules the build enforces

`tests/test_architecture.py` fails the build if any of these break:

1. The tool never reads the challenge's answer files or imports the organisers' scorer.
2. Only `llm.py` may use the network, and only to a local AI on localhost.
3. Protection and measurement never depend on the AI: everything works with it off. The AI only suggests column
   names, and a person confirms each one.

The web app listens on 127.0.0.1 only, keeps each session in `out/web/`, and the release ZIP never contains row maps.

## Extending

New format checks, protections, text detectors, data sources and receivers are registered, not hard-coded.
See [CONTRIBUTING.md](../CONTRIBUTING.md#how-to-extend).
