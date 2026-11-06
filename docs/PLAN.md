# TrustED PETs Transformer: build plan (Beyond Syntax)

> **Protect the data, keep its value.** Submissions close **Sun 8 Nov, 10:00**. Company Q&A Sat 09:00–12:00 and 14:30–18:00.

## 1. What the challenge actually asks for

Build **one working privacy tool** that, for a synthetic dataset and a defined sharing scenario:

1. **Detects** what each column / free-text field contains (direct identifier, quasi-identifier, sensitive attribute, technical ID, free text...).
2. **Selects** a proportionate PET per field, justified against the scenario (who receives the data, why, threat model).
3. **Transforms** the data (pseudonymise, generalise, suppress, redact, DP, synthesise...).
4. **Demonstrates** measured before/after: re-identification risk down, analytical utility kept, and honest residual risks.

Judging (Since AI criteria): **technical implementation** (correct PET choices) · **innovation** (intelligent, explainable) · **impact** (measured risk reduction with utility kept) · **presentation** (clear scenario, before/after, honest limitations).

Submission: working prototype + short demo video (English) + description + repo. The demo must show the identified data types, PET choices, protected output, measured utility before/after, and one realistic sharing scenario.

## 2. What we were given (`challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026/`)

- **10 synthetic datasets** from one population of 100k people in Southwest Finland: health, mobility, smart_city, energy, finance, cyber, education, public_admin, customer_service, plus `unseen` (an HR export with obfuscated headers `c01..c26`, no labels).
- **27 sharing scenarios** (`docs/SCENARIOS.md`), 3 per dataset, each with recipient, threat model, utility tasks and suggested privacy targets.
- **Ground truth for scoring:** `metadata/field_catalog.csv` (column labels), 354k labelled PII spans in free text, attacker knowledge (`adversary/`, `truth/`), holdout records.
- **`pets-eval` toolkit** (Python): scores detection, text redaction, k-anonymity, linkage attacks, utility tasks, and produces a **before/after HTML scorecard**. This gives us the measurement layer for free.
- **Baselines B0–B4 to beat** (`docs/BENCHMARK.md`). Key lessons from it:
  - Baseline detection of **sensitive attributes is weak** (F1 0.16): room to win with an LLM.
  - **Regex redaction misses names, spoken numbers and spelled-out emails.** The docs say free text is "where most teams can win".
  - Strong privacy (k ≥ 5) often destroys utility (e.g. HEALTH-S1 utility 0.79 → 0.40). Being smarter about this trade-off is what scores.

## 3. Our angle: the "privacy engineer in a box"

Most teams will write one-off scripts for one dataset. We are product builders, so we build **the tool a data-sharing team would actually use**: upload a dataset, pick a scenario, and get a justified, measured, protected release.

```
Upload dataset ─► 1 DETECT ─► 2 PLAN ─► 3 TRANSFORM ─► 4 MEASURE ─► 5 TRUST REPORT
                  LLM + rules  per-field   deterministic   pets-eval     plain-language
                  per column   PET choice  Python code     scorecard     + residual risks
                               + reasons   (HMAC, bands,   before/after
                               (editable)  redaction, DP)
```

- **The LLM is used where it adds value** (the brief explicitly asks for this): classifying columns from names + sample values, finding PII in free text (names, spoken numbers, spelled emails), and explaining each choice in plain language.
- **Deterministic code does the protection:** HMAC pseudonyms, generalisation, k-anonymity suppression, DP noise. That makes it reliable and defensible.
- **A human stays in the loop:** the user can override any field decision and re-run, and watch the privacy and utility scores move.
- **The trade-off is visible:** a privacy-vs-utility view per scenario. This is our "innovation + presentation" winner.

## 4. Scope: what we demo

Do two datasets really well, plus one bonus.

| Priority | Dataset + scenario | Why |
|---|---|---|
| **Main demo** | `health` · **HEALTH-S1** (research, row-level) | Flagship story: tables + clinical free text + linkage attacks. Baselines are beatable (B2-k utility 0.40). |
| **Second** | `customer_service` · CS-S1 | Free-text redaction benchmark: an LLM + rules hybrid should clearly beat regex. Shows the "AI where it adds value" story. |
| **Bonus** | `unseen` detection | Proves our detector generalises with no labels. Organisers can score it against private labels. |
| Stretch | HEALTH-S2 (public dashboard with DP) | Only if time: shows a second PET family (differential privacy). |

## 5. Tech stack (agent-friendly)

- **Python 3.11+** throughout, because the `pets-eval` toolkit is Python. Note: this Mac has Python 3.14; use a venv and fall back to 3.12 if packages fail.
- **UI:** Streamlit, the fastest way to a polished interactive demo in Python. (Alternative: FastAPI + a React front end only if someone on the team is strong at front-end work.)
- **LLM:** Claude API (`claude-sonnet-5-5` for speed and cost, `claude-opus-5-5` for the hardest redaction cases). The data is fully synthetic and CC BY 4.0, so sending samples to the API is allowed. Still never send secrets or rowmaps.
- **Measurement:** `pets-eval` (installed from `toolkit/`).
- **Repo layout (proposal):**
  ```
  app/            Streamlit UI
  pets/detect.py  column classifier (rules + LLM)
  pets/text.py    free-text redactor (rules + LLM, typed placeholders)
  pets/plan.py    scenario-aware PET selection + reasons
  pets/transform.py  deterministic transforms
  pets/evaluate.py   wraps pets-eval, scorecards
  pets_submission/   outputs for optional organiser checks
  ```

## 6. Team split (5 people)

| Person | Owns |
|---|---|
| 1 | **Detect**: column classifier, scored with `pets-eval detect`; `unseen` labels |
| 2 | **Free text**: rules + LLM redactor, scored with `pets-eval text` (recall-first, F2) |
| 3 | **Transform**: HMAC pseudonyms, generalisation, k ≥ 5 suppression, rowmaps for scoring |
| 4 | **UI + evaluation**: Streamlit flow, scorecard integration, before/after charts |
| 5 | **Story + submission**: scenario narrative, trust report wording, demo video, README, Q&A with organisers on Saturday |

## 7. Timeline

| When | Milestone |
|---|---|
| **Fri evening** | Install toolkit, run quickstart and baselines' scorecards. Agree on interfaces between modules. Skeleton app runs end-to-end on HEALTH-S1 with B2-level transforms. |
| **Sat morning** | Detector and redactor v1 scored. Use the morning Q&A to check our scenario choice and what the judges value. |
| **Sat afternoon** | Beat the baselines on HEALTH-S1 (privacy **and** utility). Customer-service redaction scored. Trust report generated. |
| **Sat evening** | UI polish, trade-off view, `unseen` labels, `pets_submission/` folder. Feature freeze at ~22:00. |
| **Sun 07:00–09:30** | Record demo video, write description, final checks (no rowmaps or secrets in public materials). **Submit before 10:00.** |

## 8. Rules we must not break

- Never publish `rowmap_*.csv`. They are for scoring only.
- Every privacy claim needs a method and parameters (e.g. "k ≥ 5 on age band, sex, municipality, arrival week", or "ε = 1, person-level, max 4 visits").
- Use only the provided synthetic data. Disclose residual risks honestly.

## 9. Open questions for the Saturday Q&A

1. Do judges expect one scenario done deeply, or several datasets?
2. Will organisers run the hidden attackers on our outputs before judging, and should we request it?
3. Is an LLM API (sending synthetic samples) acceptable, or do they prefer local models?

## 10. Additions from the sponsor research (agreed 6 Nov)

1. **Data minimisation framing.** Pitch the tool as data minimisation for datasets; every PET decision cites the scenario's purpose.
2. **Release manifest.** Each release ships `manifest.json` + a readable page: recipient, purpose, per-column transform and parameters, before/after scores, residual risks, SHA-256 of each output file. Owner: Transform; UI renders it.
3. **Plain-language trust report** for non-experts, drafted by the LLM from real scorecard numbers. Owner: Story and submission.

## 11. Dataset findings that change the build

- HEALTH-S1 attackers match on exact arrival date/time, municipality, age, sex and name; the utility tasks need only arrival hour, 30-day revisit gaps, triage, LOS, diagnosis by municipality and the visit→lab join. Plan: keep hour-of-day as its own column, shift dates per patient with a secret offset, one keyed pseudonym across visits/labs/notes, age band derived from HETU then drop HETU.
- Hidden identifiers to detect: ambulance unit codes (area), sex-specific lab reference ranges, lab sample times (re-link), staff names/IDs.
- Free text is trilingual (fi 73 %, en 20 %, sv 6 %) and includes speech-recognition text with spoken numbers.
- Fix deliberate data-quality glitches (°F temps, swapped BP, impossible heart rates) and report it.
