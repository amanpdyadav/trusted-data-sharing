# PETs Transformer

**Share data without exposing the people in it.** PETs Transformer (Privacy-Enhancing Technologies Transformer)
reads your tables, shows how a person could be re-identified, protects the data for one named receiver, and
proves that the protection works. Everything runs on your own computer.

Built by team Beyond Syntax for the TrustED "PETs Transformer" challenge (Since AI Hackathon 2026), and made to
run later on real company data.

## What it does, in five steps

| Step | What happens | What you get |
|---|---|---|
| 1. Data | Upload CSV files (or a ZIP), or open an example dataset | A local copy of your tables |
| 2. Risk scan | Finds names, ID codes, phones, addresses, dates and how the tables connect. Replays an attack: a few public facts lead to one person and all their linked records | `detection.json`, the risk picture |
| 3. Receiver & plan | You pick who gets the data (a research group, the public, a partner). The tool chooses one protection per column and says why | `plan.yaml` |
| 4. Review & approve | A named person checks what leaves and signs off. Nothing leaves without this | The approved plan |
| 5. Release & proof | Writes the protected files and replays the same attack on them | Release ZIP with `manifest.json` |

## Quick start

You need Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv venv .venv -p 3.11
make install
cp .env.example .env
```

Open `.env` and set `PETS_MASTER_KEY` to a long random secret (at least 32 characters). Then start the app:

```bash
make web
```

Open http://127.0.0.1:8765 in your browser. The app only listens on this computer.

Check your setup at any time:

```bash
.venv/bin/pets-transformer doctor
```

## The same steps on the command line

```bash
.venv/bin/pets-transformer detect --dataset health --out out/health/detection.json
.venv/bin/pets-transformer plan --detection out/health/detection.json --scenario HEALTH-S1 --out out/health/plan.yaml
.venv/bin/pets-transformer approve out/health/plan.yaml --by "Your Name"
.venv/bin/pets-transformer run --plan out/health/plan.yaml --receiver uni-research --out out/health
```

If the plan has items marked `REVIEW`, `approve` stops and lists them. Check them in `plan.yaml`, then approve
again with `--confirm-review`.

Use `--source csv:path/to/folder` with `detect` and `run` to read your own CSV folder instead of the example data.

## What leaves, and what never leaves

| Leaves (in the release ZIP) | Never leaves (stays in the local folder) |
|---|---|
| Protected tables (`.csv`) | Your original data |
| Published statistics, if the receiver gets statistics only | Row maps (`rowmap_*.csv`: which released row came from which record) |
| `manifest.json`: what was done, who approved it, file fingerprints, remaining risks | The secret key (`.env`) |

## Documentation

- [User guide](docs/USER_GUIDE.md): the web app screen by screen, and a glossary of the terms.
- [How it works](docs/HOW_IT_WORKS.md): the pipeline, the protections, the checks and the safety rules.
- [Contributing](CONTRIBUTING.md): code layout, tests and how to add a new protection or detector.
- [Requirements notes](NOTES_requirements.md): what the challenge asks for and the decisions we made.

## Folders

| Folder | What is in it |
|---|---|
| `src/pets_transformer/` | The tool: detect, text, plan, transform, aggregate, assess, report, web app backend |
| `frontend/` | The web app's source (React + TypeScript + shadcn/ui); built into the package, so only needed to change it |
| `scenarios/` | Receivers described in YAML (who, why, what they need, privacy targets) |
| `plans/` | Example plans |
| `codelists/` | Code groupings for statistics (for example diagnosis groups) |
| `evaluation/` | Scoring against the organisers' toolkit (uses answer files; never part of the tool) |
| `tests/` | Unit tests and rule guards (`make check`) |
| `demo/` | Demo pages for the presentation |

## Good to know

- The local AI (Ollama) is optional and off by default. Every feature works without it.
- The tool never reads the challenge's answer files. Its checks use only your data, so they work on company data too.
- Never commit `.env`, `out/`, the data package or row maps.
