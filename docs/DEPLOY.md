# Deploying the web app on a VPS (Docker + Traefik)

The app runs as one container behind a Traefik you already run as its own stack. This repo does **not** start
Traefik; it only joins the external `traefik` network and tells Traefik how to route to it with labels.

```
internet ─► Traefik (other stack, :443, TLS) ─► pets-transformer:8765 (network "traefik", no published port)
```

## What is in the repo

| File | Purpose |
| --- | --- |
| `Dockerfile` | Two stages: builds `frontend/` with Node, then a slim Python 3.12 image running uvicorn as user `app` (uid 1000). |
| `docker-compose.yml` | The app service, its volumes, Traefik labels (router, TLS, security headers). |
| `.env.docker.example` | Every variable the compose file needs. Copy to `.env` on the server. |
| `.dockerignore` | Keeps `.env`, the data package, outputs and dev files out of the image. |

## Volumes

| Mount | Kind | Holds | Back up? |
| --- | --- | --- | --- |
| `/app/out` | named volume `pets_out` | sessions, uploaded tables, releases, **private row maps**, the ε ledger, AI cache | **Yes**: this is all the work. |
| `/app/results` | named volume `pets_results` | evaluation results and screen data; seeded from the image the first time | Optional |
| `/data/package` | bind mount, read-only | the TrustED data package (`$PETS_PACKAGE_HOST_DIR`); its `data/` gives the sample datasets | It is your source; keep the original |

Scenarios (`scenarios/`) and code lists (`codelists/`) are baked into the image: change them in git and redeploy.
The container's root filesystem is read-only; only the volumes and a `/tmp` tmpfs are writable.

## First deploy

On the VPS, with Traefik already running and its network called `traefik`:

```bash
git clone <this repo> pets-transformer && cd pets-transformer
```

```bash
cp .env.docker.example .env
```

Fill in `.env`:

- `APP_DOMAIN`: a hostname whose DNS points at the VPS.
- `TRAEFIK_ENTRYPOINT` / `TRAEFIK_CERTRESOLVER`: the names used in your Traefik static config (defaults
  `websecure` / `letsencrypt`).
- `PETS_MASTER_KEY`: `openssl rand -base64 48`. Store a copy somewhere safe: pseudonyms from earlier releases can
  only be reproduced with the same key.
- `PETS_PACKAGE_HOST_DIR`: where you unpacked the TrustED package on the VPS.

Then:

```bash
docker compose up -d --build
```

```bash
docker compose ps
```

Open `https://$APP_DOMAIN`.

## Update

```bash
git pull && docker compose up -d --build
```

Volumes are kept across rebuilds, so sessions and releases stay.

## Back up and restore `out`

```bash
docker run --rm -v pets-transformer_pets_out:/v:ro -v "$PWD":/b alpine tar czf /b/pets_out-$(date +%F).tgz -C /v .
```

```bash
docker run --rm -v pets-transformer_pets_out:/v -v "$PWD":/b alpine sh -c 'tar xzf /b/pets_out-YYYY-MM-DD.tgz -C /v && chown -R 1000:1000 /v'
```

The archive contains row maps and raw uploads: treat it as sensitive data.

## Notes and limits

- **Exposure.** The app has no login, and no auth is configured in front of it: anyone who reaches
  `https://$APP_DOMAIN` can upload data and download releases. The container publishes no port, so Traefik is the
  only way in. To restrict access, add a Traefik middleware (`basicauth`, `forwardauth` or `ipallowlist`) to the
  router's `middlewares` label.
- **Local AI is off.** `PETS_LLM_URL` must be a localhost address by design, so Ollama in another container cannot be
  used. Everything works on rules alone.
- **One worker.** Sessions are folders on disk; one uvicorn process keeps writes ordered. Uploads are capped at
  500 MB by the app.
- **Logs:** `docker compose logs -f app`.
