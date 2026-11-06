# Beyond Syntax · PETs Transformer: how we work

Detect privacy risks, apply proportionate protections for a named receiver, and prove the before/after.
Built for the TrustED challenge (Since AI Hackathon 2026) and to run later on real company data.
Requirements and decisions: [`NOTES_requirements.md`](NOTES_requirements.md).

## Setup (5 minutes)

```bash
uv venv .venv -p 3.11            # once
make install                     # package + dev tools (ruff, mypy, pytest)
cp .env.example .env             # then set PETS_MASTER_KEY; never commit .env
set -a; source .env; set +a
.venv/bin/pets-transformer doctor
make check                       # lint + types + fast tests: run before every push
```

The local AI (Ollama) is **optional** and off by default (`PETS_LLM_ENABLED=false`). Everything must work
without it.

## Layout: one package per pipeline step

```
src/pets_transformer/
  contracts/   the shared files as typed models: detection, plan, metrics, manifest, spans, taxonomy
  detect/      Hari     what each column holds (validators.py, later columns.py, llm_fallback.py)
  text/        Chinedu  find and hide personal details in free text
  plan/        Aman     scenarios (YAML) -> one protection per column, with a reason
  transform/   Aman     apply the plan: pseudonymise (HMAC), generalise, suppress, noise ...
  assess/      Aman+Silenat  our own risk checks (k-anonymity, attacks, text leaks)
  report/      Aman     manifest and fingerprints
  sources.py   where tables come from (CSV now; DB later)
  keys.py      secret keys from the environment, one derived key per receiver
  llm.py       the only door to the local AI
  plugins.py   extensions from other packages
  cli.py       command line
scenarios/     scenario presets (Silenat converts the package's 27)
examples/      sample shared files to build against before the real ones exist
tests/         unit/, integration/ (needs the data package), test_architecture.py (rule guards)
ui/            Anjali   web app (added at hour 1)
```

## Principles we hold each other to

- **Single responsibility, separation of concerns.** One step per package. Detectors find, the planner
  decides, transforms apply, assess measures. A module that does two of these gets split.
- **Depend on interfaces.** Code takes a `Validator`, `ColumnDetector`, `SpanDetector`, `ColumnTransform`,
  `TableSource`, `KeyProvider` or `LlmClient`, never a concrete class. Tests pass fakes.
- **Open for extension.** New validators, transforms, text detectors and sources are *registered*, not wired in
  with `if/else`. See "How to extend" below.
- **DRY.** The shared file formats exist once, as models in `contracts/`. JSON schemas are generated from them
  (`make schemas`); never hand-edit a schema. Shared helpers (`io.read_table`, validators) are reused by
  detect and text alike.
- **No premature optimisation.** Write the clear version first, measure on the 1.6M-row table at hour 6,
  optimise only what the profile shows.
- **Small pure functions,** type hints everywhere (mypy runs on `src/`), no hidden global state except the
  registries.

## Rules the build enforces (`tests/test_architecture.py`)

1. Runtime code never reads answer files (`truth/`, `field_catalog`, `attack_specs`, `pii_spans`) or imports
   `pets_eval`. Those are for evaluation only.
2. Only `llm.py` may touch the network, and it refuses anything but localhost.
3. `transform/`, `assess/`, `plan/`, `contracts/` and `keys.py` never import the AI helper: protection and
   measurement stay deterministic with the AI off.

## How to extend

| Add a ... | Do this | Example |
|---|---|---|
| Format check | class with `name`, `subtype`, `is_valid()`, then `VALIDATORS.register(...)` | `detect/validators.py` |
| Protection technique | class with `technique`, `apply(values, params, ctx)`, then `TRANSFORMS.register(...)` | `transform/pseudonymise.py` |
| Text detector | class with `name`, `find(text) -> list[Span]`, then `SPAN_DETECTORS.register(...)` | `text/base.py` |
| Data source | class with `table_names()`, `read()`, then `SOURCES.register("scheme", Class)` | `sources.py` |
| Scenario | a YAML file in `scenarios/` or any folder in `PETS_SCENARIO_DIRS` | `scenarios/HEALTH-S1.yaml` |
| Outside package | entry point in group `pets_transformer.plugins` with `register(hub)` | `plugins.py` |

A detector that uses the local AI must catch `LlmUnavailableError` and fall back to rules.

## Shared files (contracts)

| File | Model | Written by | Read by |
|---|---|---|---|
| `detection.json` | `DetectionReport` | Detect | Plan, UI |
| `plan.yaml` | `Plan` | Plan (approved in UI) | Transform, manifest |
| `release/` + `manifest.json` | `ReleaseManifest` | Release | the receiver |
| `metrics.json` | `Metrics` | Check | UI, video, manifest |

Changing a contract: change the model, run `make schemas`, update `examples/`, tell the team in one line.
`make check` fails if the examples stop matching.

## Tests

- `make test`: fast unit tests and rule guards (no data, no AI). Must stay green.
- `make test-all`: also `integration` (needs the data package) and `ollama` (needs Ollama running) tests.
- Every new function gets a test; every bug gets a test first.
- Evaluation against the organisers' scorer lives outside `src/` (it uses answer files).

## Git

- Branch per task: `feat/<step>-<what>`, `fix/...`. Small commits, one concern each.
- `make check` green before pushing. Never commit `.env`, `out/`, the data package or row maps.
