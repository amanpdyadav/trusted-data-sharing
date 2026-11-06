"""PETs Transformer API: one backend for both front ends (Streamlit and the React + D3 app).

Run: .venv/bin/uvicorn api.main:app --port 8000
Docs: http://localhost:8000/docs
"""
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pets import OUTPUTS, mosaic  # noqa: E402

app = FastAPI(title="PETs Transformer API", version="0.1.0",
              description="Mosaic attack cases and release audits for the TrustED PETs Transformer. All data is synthetic.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8501"],
                   allow_methods=["GET"], allow_headers=["*"])


@app.on_event("startup")
def warm_up() -> None:
    """The first survey takes ~20 s; start it in the background so the first request is fast."""
    def warm():
        mosaic.summary(), mosaic.case_list()
        if (OUTPUTS / "health" / "manifest.json").exists():
            mosaic.audit("health")
    threading.Thread(target=warm, daemon=True).start()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "release_built": (OUTPUTS / "health" / "manifest.json").exists()}


@app.get("/api/summary")
def summary() -> dict:
    """How often one public scrap leads to one verified patient, for posts and news clips."""
    return mosaic.summary()


@app.get("/api/cases")
def cases(limit: int = 60, source: str | None = None) -> list[dict]:
    """Cases that resolve to one verified person, featured ones first."""
    rows = [c for c in mosaic.case_list() if source in (None, c["source"])]
    return rows[:limit]


@app.get("/api/cases/{case_id}")
def case(case_id: str) -> dict:
    """One case with its steps in each mode: raw (names shared), names (names removed), ours (our release)."""
    try:
        return mosaic.build_case(case_id)
    except KeyError:
        raise HTTPException(404, f"No post or news clip called {case_id}")


@app.get("/api/audit/{dataset}")
def audit(dataset: str) -> dict:
    """Release audit: decisions, measurements, attacks, files, checks and residual risks."""
    if not (OUTPUTS / dataset / "manifest.json").exists():
        raise HTTPException(404, f"No release built for {dataset}. Run scripts/build_health_s1.py")
    return mosaic.audit(dataset)


# Serve the built React app (web/dist) from the same port when it exists.
DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(DIST / "index.html")
