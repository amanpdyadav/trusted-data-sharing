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
.venv/bin/streamlit run app/streamlit_app.py
```

`setup.sh` unpacks the pack into `challenge/`, creates a Python 3.12 environment (with
[uv](https://docs.astral.sh/uv/) if you have it), writes `.env` with a fresh pseudonym key, and builds
our HEALTH-S1 release into `outputs/`. It is safe to run again. Add your `ANTHROPIC_API_KEY` to `.env`
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
  reid_chain.py       one social post → full profile across all datasets           ✅ working
  detect.py           column classifier, rules + LLM                               ⏳ stub
  text.py             free-text PII redaction, rules + LLM                         ⏳ stub
  plan.py             generic per-column PET choice                                ⏳ stub
app/                  Streamlit UI
  streamlit_app.py    dataset browser and baseline scores
  pages/1_Attack_demo.py     single-dataset and two-dataset linkage attacks
  pages/2_From_one_post.py   presenter-mode story: one post → named person
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
| Privacy / utility / composite | – | 1.00 / 0.98 / 0.99 |

Baseline B2-k gets utility 0.40 on the same scenario. Starting from one public post, an attacker narrows
the names-removed hospital data to exactly one patient for 263 of 948 posts. 75 of them end with a
verified name and home address.

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
