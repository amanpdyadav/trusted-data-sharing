# Runbook: running PETs Transformer, step by step

Everything a teammate needs to go from a fresh clone to a scored, explained release and the submission files.
Every command is run from the project folder. All data is synthetic.

| Part | What you do | Needs the challenge pack? |
|---|---|---|
| [0. Set up](#0-set-up-once) | Install, point to the data, set the secret key | yes, for the example data |
| [1. Web app](#1-use-the-web-app) | Data → risk scan → plan → approve → release | no (upload your own CSV) |
| [2. Command line](#2-the-same-steps-on-the-command-line) | The same five steps, scriptable | no |
| [3. Prove it](#3-prove-it-on-the-challenge-data) | Organisers' scorer, attacks, the post and news sweep | yes |
| [4. Presentation screens](#4-presentation-screens) | Mosaic attack and Release audit | yes |
| [5. Detection](#5-column-detection) | Score detection, label the unseen HR file | yes |
| [6. Free text](#6-free-text-redaction) | Score redaction, write the organisers' check file | yes |
| [7. Compare plans](#7-compare-plan-variants) | Experiments side by side | yes |
| [8. Before you push](#8-before-you-push) | Checks, what never goes in git | no |
| [9. Submission](#9-submission-files) | What we hand in | yes |
| [Troubleshooting](#troubleshooting) | Common problems | |

---

## 0. Set up (once)

**You need:** Python 3.11 or newer, [uv](https://docs.astral.sh/uv/), and the challenge pack
`TRUSTED_PETS_PROVING_GROUND_2026.zip` from the team drive (team-only, never in git).

```bash
git clone https://github.com/MahatHari/Trusted-Unlikable.git Trusted && cd Trusted
git switch combine/best-of-both          # the combined branch (until it is merged)
uv venv .venv -p 3.12
```

Unpack the challenge pack. Either location works; `challenge/` is git-ignored:

```bash
mkdir -p challenge/proving_ground
unzip -q /path/to/TRUSTED_PETS_PROVING_GROUND_2026.zip -d challenge/proving_ground
```

Install the tool and the organisers' toolkit:

```bash
make install PKG=challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026
```

Create `.env` and fill in two values:

```bash
cp .env.example .env
```

- `PETS_MASTER_KEY`: a long random secret, for example the output of
  `python3 -c "import secrets; print(secrets.token_hex(32))"`. Never share it; it makes the pseudonyms.
- `PETS_PACKAGE_ROOT=./challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026`

Check everything is found:

```bash
.venv/bin/pets-transformer doctor
```

Expected: `data package … (found)`, `master key : set`, `scenarios : 2`, `local AI : off (rules only)`.

The "before" release for comparisons is the pack's own quickstart. Create it once:

```bash
(cd challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026 && ../../../.venv/bin/python examples/quickstart.py)
```

---

## 1. Use the web app

```bash
make web
```

Open http://127.0.0.1:8765. It listens on this computer only; files stay in a local folder.

The app is a React + TypeScript front end in `frontend/`, built into `src/pets_transformer/web/static/` (the build is
committed, so `make web` works without Node). After changing anything in `frontend/`, rebuild it (Node 18+):

```bash
make ui                         # npm ci + type check + build into the package
make ui-dev                     # live reload at http://localhost:5173 while `make web` runs
```

| Step (sidebar) | What happens | What you get |
|---|---|---|
| 1. Data | Upload CSV files or a ZIP, or open an example dataset | A local working copy |
| 2. Risk scan | Every column labelled (the combined detector), tables linked, an attack replayed from a few public facts | The risk picture, `detection.json` |
| 3. Receiver & plan | Pick who gets the data (research group, public, …) or describe your own; one protection per column, with a reason | `plan.yaml` |
| 4. Review & approve | A named person checks what leaves and approves. Nothing is released without it | The approved plan |
| 5. Release & proof | Protected files written; the same attack replayed on them; usefulness compared | Release ZIP with `manifest.json` |
| Show the risk → Mosaic attack | One public post or news clip followed across datasets | See [4](#4-presentation-screens) |
| Show the risk → Release audit | Every check, decision and fingerprint of a release | See [4](#4-presentation-screens) |

"Hide personal values on screen" (bottom left) masks names and contact details on the workflow screens, for screen
sharing. The Mosaic attack screen shows its synthetic people as they are, because it demonstrates the attack.

Screen-by-screen details: [USER_GUIDE.md](USER_GUIDE.md).

**Receivers:** the receiver step shows only receivers whose tables your data has. All 27 challenge scenarios exist
(25 generated); which are ready and which need tuning: [RECEIVERS.md](RECEIVERS.md).

---

## 2. The same steps on the command line

```bash
.venv/bin/pets-transformer detect --dataset health --out out/health/detection.json
.venv/bin/pets-transformer plan --detection out/health/detection.json --scenario HEALTH-S1 --out out/health/plan.yaml
.venv/bin/pets-transformer approve out/health/plan.yaml --by "Your Name"
.venv/bin/pets-transformer run --plan out/health/plan.yaml --receiver uni-research --out out/health
```

| Step | Command | Output |
|---|---|---|
| Detect | `detect --dataset <name>` (or `--source csv:folder` for your own data) | `detection.json`: role, type, confidence, evidence, legal basis, and which scenarios request each column (`needed_by`) |
| Plan | `plan --detection … --scenario HEALTH-S1` | `plan.yaml`, never approved automatically |
| Approve | `approve <plan> --by "Name"` | The same file, signed. Open `REVIEW` items stop it until you add `--confirm-review` |
| Release | `run --plan … --receiver … --out …` | `out/…/release/` (share this) and `out/…/private/` (row maps: never share) |

Our hand-tuned plans are in `plans/`:

| Plan | For | Approved? |
|---|---|---|
| `health-s1.yaml` (version 3) | HEALTH-S1, university research group; passes every gate | **Not yet**: changes Aman's version 2 |
| `health-s1.v2.yaml` | HEALTH-S1, Aman's approved version 2 (fails the post and news sweep) | yes |
| `health-s1.auto.yaml` | HEALTH-S1 drafted by the automatic planner | yes |
| `health-s2.yaml` | HEALTH-S2, public dashboard with differential privacy | yes |

```bash
make release PLAN=plans/health-s2.yaml RECEIVER=public OUT=out/health-s2   # HEALTH-S2 public dashboard
```

`make release` on its own uses `plans/health-s1.yaml` and refuses while it is unapproved (by design: nothing is
released without a named approval). Until Aman approves version 3, release an approved copy:

```bash
mkdir -p out/health-s1 && cp plans/health-s1.yaml out/health-s1/plan.approved.yaml
.venv/bin/pets-transformer approve out/health-s1/plan.approved.yaml --by "Your Name (draft)"
make release PLAN=out/health-s1/plan.approved.yaml
```

Aman approves the real plan with `.venv/bin/pets-transformer approve plans/health-s1.yaml --by "Aman Yadav"`.

---

## 3. Prove it on the challenge data

These use the organisers' toolkit (`pets-eval`) and answer files, so they live in `evaluation/`, never in the tool.

```bash
make validate                   # scores out/health-s1/release (from section 2); RELEASE=… ROWMAPS=… for another
```

`validate` runs the organisers' scorecard and our own checks, prints every gate, and records the run in
`results/history.csv`. The full report is `results/runs/<run id>/scorecard.html`.

| Gate | Target | Plan v3 result |
|---|---|---|
| Combined score (pets-eval, privacy and usefulness) | ≥ 0.70 | 0.991 |
| Rows in groups smaller than 5 | ≤ 5 % | 0 % |
| Demo attack POST00635 (the named post) | ≥ 5 candidates | 1,172 |
| Demo attack NEWS00100 (the unnamed news clip) | ≥ 5 candidates | 367 |
| Post and news sweep (all 1,050 public scraps) | 0 leave the real visit in a group of 1-4 | 0 |

Other commands:

```bash
make sweep                                     # only the sweep, and list any scrap that still exposes someone
make baseline                                  # score the pack's quickstart output: our measured "before"
make validate RELEASE=out/health-s2/release ROWMAPS=out/health-s2/private SCENARIO=HEALTH-S2   # the dashboard
.venv/bin/pets-eval check out/health-s1/release                           # scan a release for leftover identifiers
```

The organisers' scorer directly, if you want it without our gates:

```bash
PG=challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026
.venv/bin/pets-eval scorecard --root $PG --original $PG/data/health --protected out/health-s1/release \
  --rowmap out/health-s1/private/rowmap_ed_visits.csv --scenario HEALTH-S1 --out results/pets-eval-health
```

All scores are the toolkit's self-assessment, not the official judging score.

---

## 4. Presentation screens

```bash
.venv/bin/python -m evaluation screens --release out/health-s1/release --rowmaps out/health-s1/private \
  --plan plans/health-s1.yaml
```

This scores the release (like `validate`) and writes `results/screens/mosaic.json` and `audit.json` (git-ignored,
about 3 minutes). Then open the web app (`make web`) and pick a screen under **Show the risk**:

- **Mosaic attack.** Pick a public post or a news clip (every scrap that leads to one verified person). Press
  **Next** to reveal one clue at a time on the hospital data, then one dataset at a time; **Play** runs it. The link
  graph shows how the person is identified (time · town · sex · stay · symptoms, then birth date + postcode, then
  name + postcode), and "What the attacker now knows" builds a block per source. Modes: **Raw data shared**,
  **Names removed**, **Our release** (the chain breaks).
- **Release audit.** Every gate, the scores, the sweep, each column decision with its reason, and the released
  files' fingerprints. It says so when the plan is not approved.

Rebuild the screen data after every new release.

---

## 5. Column detection

```bash
make detect-all                 # score every labelled dataset with the organisers' scorer
```

Expected: development macro-F1 about 0.93, sensitive attributes found about 90 %. Education is the "held out" set but
was used to tune one of the two detectors, so do not present that number as clean (see
[detection/SCORES.md](detection/SCORES.md)).

Label the unseen HR file (names are `c01…c26`, no answer key locally; the organisers score it):

```bash
.venv/bin/pets-transformer detect --dataset unseen \
  --source csv:challenge/proving_ground/TRUSTED_PETS_PROVING_GROUND_2026/data/unseen \
  --out out/unseen/detection.json --labels-csv pets_submission/unseen_field_labels.csv
```

How the detectors work, the laws and standards behind each label, and every measured score:
[detection/README.md](detection/README.md).

---

## 6. Free-text redaction

```bash
make text-score                 # leakage and recall against the organisers' gold spans (dev and held-out)
make redact-eval                # writes pets_submission/customer_service_eval_redacted.csv
```

---

## 7. Compare plan variants

```bash
B=plans/health-s1.v2.yaml        # the approved base plan the variants change
.venv/bin/python -m evaluation experiment stay-length --plan $B       # stay bands, top-coding, sex, town merging
.venv/bin/python -m evaluation experiment arrival-time --plan $B      # week, date + hour, time of day
.venv/bin/python -m evaluation experiment suppression-order --plan $B # which column k-anonymity blanks first
```

Variants keep the base plan's approval, so the base must be approved: use version 2 until Aman approves version 3.
Each variant is released, scored with every gate and added to `results/history.csv`. Experiments take about
75 seconds per variant because of the sweep.

---

## 8. Before you push

```bash
make check                      # lint, format check, strict type check, tests (about 530)
```

Never commit: `.env`, `out/` (releases and private row maps), `challenge/` or the pack zip, `results/runs/`,
`results/screens/`. The `.gitignore` covers them; still commit with explicit paths.

---

## 9. Submission files

| File | What it is | How it is made |
|---|---|---|
| `pets_submission/unseen_field_labels.csv` | Our labels for the unseen HR file (`column,privacy_role,subtype`) | [5](#5-column-detection) |
| `pets_submission/customer_service_eval_redacted.csv` | Redacted customer-service texts for the organisers' hidden check | [6](#6-free-text-redaction) |
| The HEALTH-S1 release | `out/health-s1/release/` (tables + `manifest.json`), never the `private/` folder | [2](#2-the-same-steps-on-the-command-line) |
| Scorecard and history | `results/runs/<run id>/scorecard.html`, `results/history.csv` | [3](#3-prove-it-on-the-challenge-data) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `doctor` says `data package … NOT FOUND` | Set `PETS_PACKAGE_ROOT` in `.env` to the unpacked pack folder |
| `PETS_MASTER_KEY is not set` | Put a long random value in `.env` (not the `change-me…` placeholder) |
| `make release` or an experiment refuses: plan not approved | Approve it (or an approved copy) with `pets-transformer approve … --by "Name"`; experiments: `--plan plans/health-s1.v2.yaml` |
| `make baseline` says quickstart output missing | Run the pack's `examples/quickstart.py` (see [0](#0-set-up-once)) |
| Mosaic attack or Release audit says "no data yet" | Run `python -m evaluation screens …` ([4](#4-presentation-screens)) |
| `FileNotFoundError` for an old data path | A server started before the data moved is still running: stop it and start it again |
| The web app shows old screens after a `git pull` | Restart `make web` (the Python side changed) and reload the page; if `frontend/` changed, run `make ui` |
| `make web`: port 8765 in use | The app is already running: open http://127.0.0.1:8765, or stop it, or `pets-transformer web --port 8766` |
| `validate` is slow | The sweep replays 1,050 scraps (about a minute); that is expected |
| `pets-eval check` reports about 22 PHONE and 1 PAYMENT_CARD hits in the HEALTH-S1 release | False positives: they are our 16-character keyed pseudonyms (`visit_id`, `patient_pseudonym`) that happen to be all digits, e.g. `3602078199529040`, and match the scanner's number patterns. No real phone or card number is released. Suggested fix: give pseudonyms a letter prefix (`v…`, `pt…`) in `transform/pseudonymise.py` |
