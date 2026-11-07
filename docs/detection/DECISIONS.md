# Detection decisions

One entry per decision: what we chose, what else we considered, why, and the source. Newest last.

## D1 · Values first, column names second (7 Nov)
- **Decision:** classify mainly from the values (format checks, value statistics). Column names only adjust confidence.
- **Options:** names first (like baseline B1); values first; names and values equal.
- **Why:** the unseen HR file names its columns `c01…c26` (S-UNSEEN), and 171 of 475 catalog columns carry
  "traps" that names miss, e.g. an ambulance unit code that reveals the home area (S-DICT). B1 is name-led and
  finds only 10 % of sensitive attributes (S-BENCH).
- **Source:** S-UNSEEN, S-DICT, S-BENCH.

## D2 · Develop on 5 datasets, report on 4 held out, plus "names hidden" (7 Nov)
- **Decision:** tune rules only on `health, finance, cyber, customer_service, education` (331 columns).
  Report the final score on `mobility, smart_city, energy, public_admin` (144 columns), which we do not look at
  while tuning. Also score every dataset with column names replaced by `c01, c02…` to simulate the unseen file.
- **Options:** tune on all 9 (higher number, but it would partly measure memorisation); no split.
- **Why:** the catalog is the answer key. Tuning on all of it would overstate how well the detector works on new
  data, which is the real test (S-UNSEEN). Reporting both numbers is honest.
- **Source:** S-CAT, S-EVAL.

## D3 · Detection records what a column is and what it is needed for (7 Nov)
- **Decision:** each column carries `needed_by`, the utility tasks that use it, next to its privacy role.
- **Why:** utility is half the challenge score, and a required task we make unanswerable scores 0 (S-EVAL).
  The plan step must know which columns to protect rather than drop. Value depends on the scenario: HEALTH-S1
  needs length of stay, HEALTH-S3 needs vital signs.
- **Source:** S-EVAL, pack `metadata/scenarios.json`.

## D4 · Every label carries evidence and a basis (7 Nov)
- **Decision:** no label without `evidence` (what fired) and `basis` (IDs from `SOURCES.md`).
- **Why:** the brief asks for explainable choices; a reviewer must be able to check each label without reading code.
- **Source:** S-PLAN, L-GDPR-5.

## D5 · Local model only, and only where rules are unsure (7 Nov)
- **Decision:** rules decide first. Only columns below a confidence threshold go to the local model
  (Ollama qwen2.5:7b), with the plan's rules: same answer every time, fixed JSON, every value it cites must appear in
  the data, answers cached. Its label is marked `method: llm`.
- **Why:** team plan (S-PLAN, page 5); the model is slow (about 2 s per call) and rules are explainable.
- **Source:** S-PLAN.

## D6 · The held-out test showed overfitting; later fixes are not a clean test (7 Nov)
- **Finding:** v3 scored macro-F1 0.959 on the dev datasets but 0.620 on the held-out ones, against 0.632 for the
  organisers' baseline B1 on the same held-out columns. The rules had fitted the dev data.
- **What the held-out errors show:** (1) travel-card numbers pass the Luhn check, so a card checker also needs the
  issuer prefix (ISO/IEC 7812 IIN); (2) confidences (0.987) and kWh readings passed as GPS coordinates; (3) the same
  coordinate is personal on a trip and not personal on a bus stop: tables that describe places or equipment are not
  about people; (4) vocabulary gaps (late payments, payment plans, medical devices).
- **Decision:** fix these as general rules (v4), but report v4's held-out score as **"after seeing held-out errors"**,
  not as a clean test. The remaining clean test is the unseen HR file, which the organisers score.
- **Why:** reporting only the best number would overstate how the detector does on new data, which is what the
  judges and the unseen file test.

## D7 · Combine both detectors; stronger evidence wins (7 Nov)
- **Decision:** run Aman's rule-based detector and the layered detector side by side. Agreeing labels stand; on a
  disagreement the higher-confidence label wins; ties keep the rule-based label.
- **Options tested** (all reported, none tuned further): rule-based only, layered only, higher confidence with either
  tie-break. The two tie-breaks scored the same.
- **Why:** the detectors make different mistakes (65 disagreements: layered right 38, rule-based 25). The combination
  is best overall (0.930) and with names hidden (0.790), and never the worst on any split.
- **Caveat:** each detector's held-out set is the other's tuning data, so the held-out numbers are not clean.

## D8 · The post and news sweep is a release gate (7 Nov)
- **Decision:** `validate` replays all 1,050 public posts and news clips whose person visited the ED, and fails a
  release where any scrap leaves the real visit in a group of 1-4 (`evaluation/scrap_sweep.py`, `targets.yaml`).
- **Why:** the two demo attacks pass easily (240 candidates), but the sweep found 8 exposed people in the HEALTH-S1
  release, 3 narrowed to a single visit, all through exact length of stay plus town, sex from the first name and
  symptoms. Two hand-picked cases cannot show that; the whole attacker file can.
