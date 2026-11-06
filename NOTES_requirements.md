# TrustED PETs Transformer — requirements & design notes

Working notes from reading the challenge brief, the Proving Ground package (v1.0.0) and both websites.
Written 2026-11-06 (Friday, event day 1). Submission deadline: **Sun 8 Nov 10:00 EET** on sinceai.app.

---

## 1. What we must deliver (hard requirements)

From the brief (`TrustED_PETs_Transformer_Challenge_Brief_FINAL_REVIEW (1).docx`) and START_HERE:

| # | Demo must show | Evidence |
|---|---|---|
| 1 | Data types identified | Our detector output, per column + free-text spans (scored by `pets-eval detect` / `pets-eval text`) |
| 2 | PET chosen per data type, justified for the scenario | Per-field plan with reason |
| 3 | Transformed dataset / protected view | Actual output files |
| 4 | Utility before vs after | `pets-eval scorecard` utility tasks for the scenario |
| 5 | Sharing scenario it is fit for + residual risk | Scenario card + honest residual-risk list |

Submission (sinceai.app): name, one-line tagline, description, tech used, repo link, **YouTube demo video**
(English narration), source .zip, accept IP terms. Disclose AI tools used. Never publish real data, secrets or `rowmap_*.csv`.

Judging (Since AI criteria, no extra rubric): technical correctness of PET choices · innovation (intelligent,
explainable) · impact (measured risk reduction with preserved utility) · presentation (clear scenario,
before/after, honest limitations).

Who judges what:
- **TrustED** picks the challenge top 3 → rewards substance and rigour.
- **Participant vote** (every builder does 20 pairwise comparisons by Sun 12:00) → rewards a visual hook.
- **Finals** (5 teams, live jury) → both.

Optional organiser checks (put in `pets_submission/`): hidden stronger attackers per domain, `unseen`
field labels (`column,privacy_role,subtype`), `customer_service` eval-split redaction.

---

## 2. Who TrustED is (to align the pitch)

Horizon Europe GA 101168467, coordinator Gradiant (+ InfoCert, Fraunhofer ISST/AISEC, TREE, Promptly Health,
SESTEK, ULS Coimbra, …). Themes: self-sovereign identity / EUDI wallet, privacy-preserving computation
(secure aggregation, HE, federated learning), **data minimisation**, trusted European data spaces. Pilots are
mostly **health** (hospital data). → Health scenario as flagship; "share less" and machine-readable,
verifiable release metadata fit their language.

---

## 3. How `pets-eval` actually scores (read from the code)

- **Privacy** = `1 − (0.5·worst + 0.5·mean)` over all risk components of all released tables. One bad component dominates.
- **Utility** = mean of the scenario's required tasks; a required task that is not answerable = 0.
- **Composite** = weighted harmonic mean (privacy 30, utility 25).
- Risk components per table:
  - direct identifiers retained (catalogued direct-id values still present verbatim)
  - hashed ids reversible (unsalted MD5/SHA1/SHA256 dictionary attack — keyed HMAC is safe)
  - **records with k<5** over *catalogued* QI columns that are kept under their original names
  - linkage re-identification = max over attacks of re-id rate **or attribute-inference advantage** (all candidates share one sensitive value)
  - free-text identifier leakage (gold span values surviving, normalised; withheld column = 0)
  - trajectory unicity (mobility / smart_city)
  - synthetic path (no row map): exact copies + membership-inference advantage vs `holdout/`
- Linkage matching tolerates generalisation: age bands → intervals, week/month/day → time windows,
  truncated postcodes, coordinate precision → geo tolerance. Names: all attacker tokens must appear.
- Regex residual scan is reported but not scored.

**Caveat (do not exploit):** the k<5 check only sees columns with the catalogue's names, so renaming
`date_of_birth` → `age` hides it from the check. Real data has no catalogue, so our tool must compute
its own honest k / uniqueness over the QIs *it* detected and report that number.

### Measured reference point (quickstart, HEALTH-S1)
privacy 0.373 · utility 0.793 · composite 0.491. Direct re-id already low (news 18.5% → 5.5%,
social 54% → 2%, directory 57% → 0%) but **99% of rows have k<5** because `arrival_ts` at hour precision +
sex + municipality + arrival_mode is near-unique. H-U7 missing because `lab_results` was not released.

### HEALTH-S1 utility needs (from `utility/health.py`)
- H-U2: `triage` + `los_minutes` (or arrival+discharge)
- H-U4: `municipality` + `icd10_primary` (3-char codes or groups OK)
- H-U6: `readmit_30d` or a consistent patient pseudonym + age
- H-U7: `lab_results` released, `visit_id` consistent across both tables, `temp_c`
- H-U8: `arrival_ts` must still contain a time of day (`HH:MM`)
- Tension to solve: hour-of-day (H-U8) vs k≥5 on arrival time. Options: coarse date + exact hour,
  hour bands, or move the hour to a separate column and accept H-U8 cost; measure each.

Baselines to beat (docs/BENCHMARK.md): B2-k gets privacy ~0.5 but kills utility (HEALTH-S2 0.00, FIN-S1 0.06).
B1 detector macro-F1 0.65, sensitive-attribute recall 0.10. Free-text redaction is the biggest open win.

---

## 4. The data world (facts worth remembering)

- One synthetic population: 100k residents of SW Finland; **72,029** appear in some dataset;
  23,835 in 2, 10,999 in 3, **3,477 in 4+**, 36 in 6. `truth/*.csv` maps every record and attacker row to `person_id`.
- Read every CSV with `dtype=str`.
- Free-text gold spans: 354k across 10 text columns; labels & rules in `metadata/pii_span_guidelines.md`
  (spoken digits in fi/sv/en, split across turns, spelled e-mails, lowercase names, secrets, HEALTH).
- `metadata/field_catalog.csv` has a `traps` column with 171 field-level pitfalls — use as test cases, not runtime input.

### Verified mosaic chain (hero demo candidate), using only public scraps + name matching
`P016956` "Riitta Lipponen": social post *"slipped on ice, wrist pain"* → ED visit (S52.5 wrist fracture) →
public directory (Aaltokatu 30 A 1, 20100 Turku) → leaked customer list (phone) → bank (income 30–45k,
employer Meridian Logistics Oy) → Meridian SOC identity (Warehouse Clerk). Other 5-domain candidates:
P044055, P062151, P036339 (news clip), P054940, P067543.

---

## 5. Production requirements (the tool must be usable later on real company data)

1. **No dependence on package metadata at runtime.** Detection works from column names + values only;
   catalogue, truth and attacker files are used only for evaluation and tests.
2. **Data never leaves the machine.** All detection/NER local. If an LLM is used it is local, or sees only
   schema + aggregate statistics, never raw values. Configurable, default off for cloud.
3. **Secrets handled properly.** HMAC / prefix-preserving keys come from env or a KMS, never code.
   Separate key domain per recipient/release (prevents cross-release linkage); rotation supported.
4. **Policy as configuration.** Scenarios are YAML/JSON (recipient, trust level, purpose, required analyses,
   threat model, targets: k, ε, text recall). The 27 package scenarios ship as presets; companies add their own.
5. **Human in the loop.** Detector proposes roles with confidence + evidence; a data steward reviews and
   overrides; the approved plan is saved and re-runnable.
6. **Own risk engine.** k-anonymity / uniqueness on detected QIs, l-diversity on sensitive attributes,
   text leakage self-check, DP ε ledger across releases. `pets-eval` is a validator on synthetic data only.
7. **Audit-ready release manifest** per output: input fingerprint, config, PET + parameters per column,
   metrics, residual risks, approver, timestamp; optionally signed (fits TrustED verifiable-credential theme).
   Row maps / key material never written into the release folder.
8. **Deterministic & reproducible** (seeded), with a clear separation: `detect → plan → transform → assess → report`.
9. **Scale**: 1.6M-row tables must run in minutes — vectorised ops, chunking.
10. **Languages**: Finnish, Swedish, English text; HETU checksum validation; Finnish phone/IBAN/plate formats
    as plug-in validators so other locales can be added.
11. **Extensible**: detectors and transforms are plug-ins with a common interface.

---

## 6. Proposed product shape

Pipeline: **Detect → Plan → Transform → Prove → Report**, with a web UI on top of a Python engine.

Showcase: HEALTH-S1 (flagship, tabular + labs join + notes), CS-S1 (transcripts to external LLM vendor,
free-text), HEALTH-S2 (public dashboard, DP vs small-cell differencing). `unseen` detection as proof of
generalisation.

Visual hook for voters: the mosaic attack (Riitta chain) lighting up across datasets, then "Protect" breaks the
links and shows the measured numbers; scenario switcher showing the same column get different PETs; live redaction.
Every on-screen number comes from our engine / `pets-eval`.

Environment: project venv at `.venv` (Python 3.11, `pets-eval` installed editable). Package tests: 21 passed.

---

## 7. Local LLM (Ollama) — decisions and measured results (2026-11-06)

Machine: Apple M1 Max, 32 GB, Ollama 0.40.9 on `localhost:11434`. Installed: qwen2.5:7b, qwen3.5:4b, qwen2.5:3b,
llama3.2:3b, nomic-embed-text, embeddinggemma. Probe: `scratchpad/llm_probe.py` style call to `/api/generate` with a
JSON-schema `format`, `temperature 0`, `think: false`.

| Model | Result on 4 sample texts (fi/sv/en) | Speed (warm) |
|---|---|---|
| qwen2.5:7b | Caught spoken Finnish phone ("nolla neljä viisi…"), neighbour name + address, e-mail, digit-by-digit phone. One false positive ("hej" labelled NATIONAL_ID). | ~1.5–2.5 s per short text |
| qwen3.5:4b | Tagged every Finnish number word as PERSON — not usable for text. | ~1.5–3 s |

Implication: ~1,500–2,400 short texts/hour single stream → cannot run on all 140k chat turns. Use selectively.

Where the local LLM is used (owner):
1. Detection fallback for columns rules cannot place, esp. the `unseen` HR file — name + 10 sample values + stats → role (Hari).
2. Text redaction second pass only on sentences the rules flag as uncertain (digit words, capitalised tokens, cue words) and on the eval split (Chinedu).
3. Plain-language explanation of each PET choice; the deterministic engine decides (Aman).
4. Draft scenario YAML from a plain-language request; a human approves (Silenat).
5. LLM attacker test: read protected text, try to guess identity/condition; report hit rate on a sample (Silenat).
6. Release-note prose around numbers filled in from metrics.json (Aman).

Guardrails: localhost only; temperature 0; JSON-schema output; every returned span must occur verbatim in the input
(drop hallucinations) and pass validators where one exists; cache by input hash; timeout → fall back to rules;
the LLM never sets privacy parameters; record model name + digest in the release manifest.

### 7b. Zero-shot column test on the unseen HR file (qwen2.5:7b, 26 columns, 77 s)

- Wrong on clear identifiers: names (c04) → free_text; HETU (c05), phone (c08), IBAN (c10) → technical_identifier.
  Validators/regex beat the LLM here.
- Missed the key Art. 9 trap: c13 `AY-TK/AY-PS/AY-HL` (likely trade-union codes, AY = ammattiyhdistys) → technical_identifier, art9 false.
- False alarms: salary (c11) marked Art. 9; work-time % (c24: 50/100) read as salary.
- Right: c16 free text "Polven nivelkierukan repeämä, lääkärintodistus…" flagged as health (Art. 9); c21 workplace as QI; dates as QI.

Verdict: the LLM is a helper, not the detector. Rules and validators decide; the LLM gives a second opinion and a
plain "meaning" line for unplaced columns and never overrides a validator. Keep: explanations/release note.
Experiment (decide at H6 on ~300 labelled turns): text second pass. Stretch only: LLM attacker test (a weak attacker
failing proves little). Never: transforms, k, DP.
