# PETs Transformer

**Share data without exposing the people in it.** PETs Transformer (Privacy-Enhancing Technologies Transformer)
reads your tables, shows how a person could be re-identified, protects the data for one named receiver, and proves
that the protection works. Everything runs on your own computer: nothing is uploaded, and the app makes no outside
connections.

Built by team Beyond Syntax for the TrustED "PETs Transformer" challenge (Since AI Hackathon 2026), and made to run
later on real company data.

## What it does

| Step | What happens | What you get |
|---|---|---|
| 1. Data | Upload CSV files (or a ZIP), or open an example. Columns without a real name can be named first; format checks and, if you turn it on, a local AI suggest names | A local copy of your tables |
| 2. Risk scan | Finds names, ID codes, phones, addresses, dates and how the tables connect, then replays an attack: a few everyday facts lead to one person and all their records | `detection.json` and the risk picture |
| 3. Receiver & plan | You pick who gets the data (a research group, the public, a partner). The tool chooses one protection per column and says why | `plan.yaml` |
| 4. Review & approve | A named person checks what leaves and signs off. Nothing leaves without this | The approved plan |
| 5. Release & proof | Writes the protected files and replays the same attack on them | A release ZIP with `manifest.json` |

Two more pages sit beside the steps:

- **Release audit:** every release made in the app (who it was for, who approved it, every column decision, the
  attack before and after, the risk left, file fingerprints), and a benchmark of all 27 challenge receivers next to
  the organisers' baselines.
- **Mosaic attack:** on the challenge's hospital data, one public post or news clip followed into eight
  organisations' data, with raw data, names removed and our release side by side.

## Quick start

You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). Node is only needed to change the web app.

```bash
uv venv .venv -p 3.11
make install
cp .env.example .env
```

Open `.env` and set `PETS_MASTER_KEY` to a long random secret (at least 32 characters). Then start the app:

```bash
make web
```

Open http://127.0.0.1:8765. The app only listens on this computer. `.venv/bin/pets-transformer doctor` checks the
setup at any time, and `make help` lists every command.

To try it on the challenge data, unpack the challenge pack and point `PETS_PACKAGE_ROOT` in `.env` at it (see the
[runbook](docs/RUNBOOK.md#0-set-up-once)); its datasets then appear as examples in the app.

## The same steps on the command line

```bash
.venv/bin/pets-transformer detect --dataset health --out out/health/detection.json
.venv/bin/pets-transformer plan --detection out/health/detection.json --scenario HEALTH-S1 --out out/health/plan.yaml
.venv/bin/pets-transformer approve out/health/plan.yaml --by "Your Name"
.venv/bin/pets-transformer run --plan out/health/plan.yaml --receiver uni-research --out out/health
```

`approve` stops while the plan has items marked `REVIEW`; check them, then approve again with `--confirm-review`.
Use `--source csv:path/to/folder` with `detect` and `run` to read your own CSV folder.

## What leaves, and what never leaves

| Leaves (in the release ZIP) | Never leaves (stays in the local folder) |
|---|---|
| Protected tables (`.csv`) | Your original data |
| Published statistics, when the receiver gets statistics only | Row maps (`rowmap_*.csv`: which released row came from which record) |
| `manifest.json`: what was done, who approved it, file fingerprints, the risk left | The secret key (`.env`) |

## Results on the challenge data

Self-assessed with the organisers' `pets-eval` toolkit. The commands live in `evaluation/`, apart from the tool,
because they read the challenge's answer files; the tool itself never does.

| What | Result | How to reproduce |
|---|---|---|
| Column detection, 9 labelled datasets | macro-F1 0.930, sensitive attributes found 88 % (organisers' baseline 0.646 and 10 %) | `make detect-all` |
| HEALTH-S1, tuned plan (`plans/health-s1.yaml`) | privacy 1.00, usefulness 0.980, combined 0.991; 0 of 1,050 public posts and news clips expose anyone | `make release validate sweep` |
| All 27 receivers, automatic plan | 8 ready (combined ≥ 0.70), 7 public dashboards released with differential privacy, 12 need tuning | `make receivers` |
| Against the organisers' B2-k baseline | better on both privacy and usefulness for 13 of the 20 scored receivers | `make receivers` |
| Mosaic attack | names removed: 404 of 948 posts and 119 of 220 news clips lead to one patient | `make screens` |

Details: [receivers and benchmark](docs/RECEIVERS.md), [detection](docs/detection/README.md),
[runbook](docs/RUNBOOK.md).

## How it is built

```
tables ──> name columns ──> detect ──> risk scan ──> plan ──> approve ──> transform ──> assess ──> release
           (optional)       (what is   (who can be   (one      (a named   (apply the   (prove     (files +
                            in each    found, how    protection person)   plan)        it)        manifest)
                            column)    tables link)  per column)
```

One engine serves the web app and the command line. Each step is its own package in `src/pets_transformer/`, and the
steps talk through typed files (`contracts/`): `detection.json`, `plan.yaml`, `manifest.json`. The build enforces the
safety rules (`tests/test_architecture.py`): the tool never reads the challenge's answer files, only `llm.py` may
open a connection (and only to a local AI), and protection never depends on the AI. Full description:
[how it works](docs/HOW_IT_WORKS.md).

## Project layout

| Folder | What is in it |
|---|---|
| `src/pets_transformer/` | The tool: `detect/`, `text/`, `plan/`, `transform/`, `aggregate/`, `assess/`, `contracts/`, `web/` (the app's backend), `pipeline.py`, `cli.py` |
| `frontend/` | The web app's source (React, TypeScript, Tailwind, shadcn/ui). Its build is committed in the package, so users need only Python |
| `scenarios/` | The 27 receivers as YAML: who, why, what they need, privacy targets |
| `plans/` | Hand-tuned plans (HEALTH-S1, HEALTH-S2) |
| `codelists/` | Code groupings for published statistics (diagnosis groups) |
| `evaluation/` | Scoring against the organisers' toolkit; never part of the tool |
| `results/` | Committed measurements: run history, the receivers benchmark, the organisers' baselines, text redaction |
| `pets_submission/` | Files for the organisers: unseen-file field labels, redacted customer-service texts |
| `examples/` | One example of each shared file, kept in step with the contracts |
| `demo/` | The presentation walkthrough and the original problem demo |
| `docs/` | Runbook, user guide, how it works, receivers, detection, requirements |
| `tests/` | Unit tests, rule guards, and checks on the real data (skipped without the pack) |

## Configuration

Settings come from the environment; `.env` (copied from `.env.example`) is loaded automatically and anything already
set in the shell wins.

| Variable | Meaning | Default |
|---|---|---|
| `PETS_MASTER_KEY` | Secret for keyed pseudonyms; each receiver gets its own derived key | required |
| `PETS_PACKAGE_ROOT` | The challenge pack (example datasets, evaluation) | `./TRUSTED_PETS_PROVING_GROUND_2026` |
| `PETS_OUT_DIR` | Releases, private row maps, the app's workspace | `./out` |
| `PETS_RESULTS_DIR` | Measurements the app shows on the Release audit page | `./results` |
| `PETS_SCENARIO_DIRS` | Receiver folders, `:`-separated (add your company's presets) | `scenarios` |
| `PETS_CODELIST_DIR` | Code lists for statistics | `codelists` |
| `PETS_LLM_ENABLED`, `PETS_LLM_URL`, `PETS_LLM_MODEL` | Optional local AI (Ollama, localhost only) for column-name suggestions | off |

## Documentation

- [Runbook](docs/RUNBOOK.md): every step from a fresh clone to a scored release and the submission files.
- [User guide](docs/USER_GUIDE.md): the web app screen by screen, and a glossary.
- [How it works](docs/HOW_IT_WORKS.md): the pipeline, the protections, the checks and the safety rules.
- [Receivers](docs/RECEIVERS.md): where the 27 receivers come from and how each one scores.
- [Detection](docs/detection/README.md): the two detectors, the laws and standards behind each label, every score.
- [Requirements and decisions](docs/REQUIREMENTS.md): what the challenge asks for and what we decided.
- [Contributing](CONTRIBUTING.md): code layout, principles, tests, and how to add a protection or a detector.

## Good to know

- The local AI is optional and off by default; every feature works without it. When on, it only suggests column
  names, and a person confirms each one.
- The tool never reads the challenge's answer files. Its checks use only your data, so they work on company data too.
- Never commit `.env`, `out/`, the challenge pack or row maps; `.gitignore` keeps them out.
