# web/ · React + D3 front end

The mosaic attack walkthrough and the release audit, in the style of the team's problem demo page.
All numbers come from the FastAPI backend (`api/main.py`), which runs our Python code in `pets/`.

| View | URL | What it shows |
|---|---|---|
| Mosaic attack | `#attack` | One post or news clip → hospital → bank → directory… in three modes: raw data shared, names removed, our release |
| Release audit | `#audit` | HEALTH-S1 release: checks, linkage attacks before/after, one-post attack on our release, k-anonymity, utility, column decisions, file hashes, residual risks |

## Run in development

Start the API first, from the repo root:

```bash
.venv/bin/uvicorn api.main:app --port 8000
```

Then the front end, from `web/`:

```bash
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000. The first request takes about 20 seconds while the
API replays the attack on all posts and news clips.

## Build and serve from the API

```bash
npm run build
```

FastAPI serves `web/dist` when it exists, so the app is then at http://localhost:8000/.

## Layout

```
src/App.jsx                    top nav and hash routing (#attack, #audit)
src/components/AttackView.jsx  case picker, mode toggle, controls, step card, dossier, lessons
src/components/ChainRail.jsx   the chain of datasets (D3)
src/components/Funnel.jsx      log-scale candidate funnel (D3)
src/components/AuditView.jsx   release audit
src/components/charts.jsx      attack bars, pool histogram, utility bars (D3)
src/styles.css                 tokens and styles from the problem demo, light and dark
```

Keyboard: ArrowLeft and ArrowRight step through the chain. Identifiers arrive already partly masked from the API.
