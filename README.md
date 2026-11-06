# PETs Transformer · Beyond Syntax

Since AI Hackathon 2026 · TrustED challenge. *Protect the data, keep its value.*

A tool that detects privacy risks in a dataset, chooses a proportionate protection per column for a
sharing scenario, transforms the data, and proves with the `pets-eval` scorecard that risk went down
while analytical utility was kept.

## Quick start

You need the challenge pack zip (`TRUSTED_PETS_PROVING_GROUND_2026.zip`, 111 MB) from the team drive.
It is team-only and never goes in git.

```bash
git clone <repo-url> Trusted && cd Trusted
./scripts/setup.sh /path/to/TRUSTED_PETS_PROVING_GROUND_2026.zip
.venv/bin/uvicorn api.main:app --port 8000          # 1. the API (keep it running)
.venv/bin/streamlit run app/streamlit_app.py        # 2a. Streamlit front end → http://localhost:8501
open http://localhost:8000/                         # 2b. React + D3 front end, served by the API
```

`setup.sh` unpacks the pack into `challenge/`, creates a Python 3.12 environment (with
[uv](https://docs.astral.sh/uv/) if you have it), writes `.env` with a fresh pseudonym key, builds
our HEALTH-S1 release into `outputs/`, and builds the React app if Node is installed. It is safe to run again.
The API warms its caches for about 30 seconds after starting.

## How it fits together

```
challenge/ data ──► pets/ (library) ──► api/ (FastAPI, port 8000) ──┬──► app/  Streamlit front end (8501)
                                                                    └──► web/  React + D3 front end (8000/ or 5173 in dev)
```

Both front ends show the same two views from the same API:

- **Mosaic attack**: one public scrap (social post or news clip) → hospital visit → bank, energy, transport,
  school, employer, telecom. Three modes: raw data shared, names removed, our release.
- **Release audit**: who the release is for, every column decision, before/after measurements, every attack,
  file fingerprints, pass/fail checks and the risk left.

API docs: http://localhost:8000/docs Add your `ANTHROPIC_API_KEY` to `.env`
when you work on the LLM steps.

## What's in the repo

The folders split into what we were given and what we built.

```
challenge/            WHAT WE WERE GIVEN (git-ignored, see challenge/README.md)
  brief/              challenge brief, presentation, pack zip
  proving_ground/     unpacked pack: 10 datasets, 27 scenarios, ground truth, pets-eval toolkit

pets/                 WHAT WE BUILT: the library
  health_s1.py        HEALTH-S1 release, every column decision with its reason     ✅ working
  transform.py        HMAC pseudonyms, age bands, hour-only, k ≥ 5 enforcement     ✅ working
  evaluate.py         wrapper around the official pets-eval scorecard              ✅ working
  manifest.py         release manifest with SHA-256 of every released file         ✅ working
  attack_demo.py      linkage attacks against a release                            ✅ working
  reid_chain.py       one post or news clip → one patient → other datasets         ✅ working
  mosaic.py           attack cases in three modes, release audit                   ✅ working
  detect.py           column classifier, rules + LLM                               ⏳ stub
  text.py             free-text PII redaction, rules + LLM                         ⏳ stub
  plan.py             generic per-column PET choice                                ⏳ stub
api/main.py           FastAPI: /api/summary, /api/cases, /api/cases/{id}, /api/audit/{dataset}
app/                  Streamlit front end
  streamlit_app.py    dataset browser and baseline scores
  pages/1_Attack_demo.py     single-dataset and two-dataset linkage attacks
  pages/2_Mosaic_attack.py   mosaic attack walkthrough (same look as the team's problem demo)
  pages/3_Release_audit.py   release audit
web/                  React + D3 front end (Vite): mosaic attack and release audit
scripts/
  setup.sh            one-time setup after cloning
  build_health_s1.py  build, score and document the HEALTH-S1 release
docs/
  PLAN.md             build plan, team split, timeline, rules
  artifacts/          shareable pages (plan, dataset guide, results, attack demos)
outputs/              protected releases and scorecards (git-ignored, rebuilt by setup)
```

## Results so far (HEALTH-S1, self-assessed with pets-eval)

| | Names removed | Our release |
|---|---|---|
| Re-identified via social posts | 54 % | 0 % |
| Records with k < 5 | 100 % | 0 % |
| Privacy / utility / composite | – | 1.00 / 0.98 / 0.99 (baseline B2-k: 0.52 / 0.44 / 0.48) |

Starting from one public scrap, an attacker narrows the names-removed hospital data to exactly one verified
patient for 407 of 948 posts and 140 of 220 news clips. On our release, no scrap narrows it to one visit.
**Residual risk:** 8 of 1,168 scraps narrow it to 2–4 visits that include the real person, because length of
stay and diagnosis group are not covered by the k ≥ 5 check. The release audit reports this as a failed check.

## Common tasks

```bash
.venv/bin/python scripts/build_health_s1.py          # rebuild our release and scorecard
.venv/bin/pets-eval --help                           # official toolkit CLI
rm -rf outputs/health && ./scripts/setup.sh          # clean rebuild
```

## Rules

- Never publish `rowmap_*.csv`; they exist only for scoring.
- Every privacy claim states its method and parameters.
- Never commit `.env`, anything in `challenge/`, or `outputs/`. The `.gitignore` enforces this.
- All data is synthetic (CC BY 4.0). Use only the provided data.
