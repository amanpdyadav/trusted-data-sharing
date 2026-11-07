"""HTTP layer of the local web app: parse the request, call the service, return JSON or a file.

Run with `pets-transformer web`. It listens on 127.0.0.1 only: the data never leaves this machine.
"""

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pets_transformer.config import Settings
from pets_transformer.contracts import PrivacyRole, Subtype, TrustLevel
from pets_transformer.keys import MissingKeyError
from pets_transformer.web.service import ActionEdit, App, Override
from pets_transformer.web.workspace import Workspace, WorkspaceError

STATIC = Path(__file__).with_name("static")


class SampleRequest(BaseModel):
    name: str


class OverrideRequest(BaseModel):
    table: str
    column: str
    privacy_role: str
    subtype: str
    by: str = ""


class SeedRequest(BaseModel):
    seed: int | None = None  # None: a fresh random pick


class PlanRequest(BaseModel):
    scenario_id: str | None = None
    custom: dict[str, Any] | None = None  # a receiver described in the app (same fields as a scenario YAML)


class ActionRequest(BaseModel):
    table: str
    column: str
    technique: str
    params: dict[str, Any] = Field(default_factory=dict)


class KRequest(BaseModel):
    k: int = Field(ge=2, le=100)


class ApproveRequest(BaseModel):
    by: str
    confirm_review: bool = False


class RunRequest(BaseModel):
    receiver: str


class CompareRequest(BaseModel):
    scenario_ids: list[str]


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    svc = App(settings, Workspace(settings.out_dir / "web"))
    api = FastAPI(title="PETs Transformer", docs_url="/api/docs", redoc_url=None)

    @api.exception_handler(WorkspaceError)
    async def _user_error(_: Request, exc: WorkspaceError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @api.exception_handler(MissingKeyError)
    async def _no_key(_: Request, exc: MissingKeyError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @api.exception_handler(ValueError)
    async def _bad_value(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    def session(sid: str) -> Any:
        return svc.workspace.get(sid)

    @api.get("/api/catalogue")
    def catalogue() -> dict[str, Any]:
        return {
            "samples": svc.samples(), "receivers": svc.scenarios(),
            "roles": [r.value for r in PrivacyRole], "subtypes": [x.value for x in Subtype],
            "trust_levels": [t.value for t in TrustLevel], "codelists": sorted(svc.policy().codelists),
        }  # fmt: skip

    @api.get("/api/sessions")
    def sessions() -> list[dict[str, Any]]:
        return svc.sessions()

    @api.post("/api/sessions/sample")
    def open_sample(req: SampleRequest) -> dict[str, Any]:
        return svc.overview(svc.open_sample(req.name))

    @api.post("/api/sessions/upload")
    async def upload(
        files: Annotated[list[UploadFile], File()], name: Annotated[str, Form()] = "my-data"
    ) -> dict[str, Any]:
        contents = [(f.filename or "table.csv", await f.read()) for f in files]
        return svc.overview(svc.workspace.from_uploads(name, contents))

    @api.get("/api/sessions/{sid}")
    def overview(sid: str) -> dict[str, Any]:
        return svc.overview(session(sid))

    @api.post("/api/sessions/{sid}/scan")
    def scan(sid: str) -> dict[str, Any]:
        return svc.scan(session(sid))

    @api.post("/api/sessions/{sid}/attack/another")
    def another_person(sid: str, req: SeedRequest) -> dict[str, Any] | None:
        return svc.another_person(session(sid), req.seed)

    @api.post("/api/sessions/{sid}/detections")
    def override(sid: str, req: OverrideRequest) -> dict[str, Any]:
        return svc.override(session(sid), Override(**req.model_dump()))

    @api.post("/api/sessions/{sid}/plan")
    def make_plan(sid: str, req: PlanRequest) -> dict[str, Any]:
        return svc.make_plan(session(sid), req.scenario_id, req.custom)

    @api.get("/api/sessions/{sid}/plan")
    def plan_view(sid: str) -> dict[str, Any]:
        return svc.plan_view(session(sid))

    @api.post("/api/sessions/{sid}/plan/action")
    def edit_action(sid: str, req: ActionRequest) -> dict[str, Any]:
        return svc.edit_action(session(sid), ActionEdit(**req.model_dump()))

    @api.post("/api/sessions/{sid}/plan/k")
    def set_k(sid: str, req: KRequest) -> dict[str, Any]:
        return svc.set_k(session(sid), req.k)

    @api.post("/api/sessions/{sid}/approve")
    def approve(sid: str, req: ApproveRequest) -> dict[str, Any]:
        return svc.approve(session(sid), req.by, req.confirm_review)

    @api.post("/api/sessions/{sid}/run")
    def run(sid: str, req: RunRequest) -> dict[str, Any]:
        return svc.run(session(sid), req.receiver)

    @api.get("/api/sessions/{sid}/results")
    def results(sid: str) -> dict[str, Any]:
        return svc.results(session(sid))

    @api.get("/api/sessions/{sid}/tradeoff")
    def tradeoff(sid: str) -> dict[str, Any]:
        return svc.tradeoff(session(sid))

    @api.post("/api/sessions/{sid}/compare")
    def compare(sid: str, req: CompareRequest) -> dict[str, Any]:
        return svc.compare(session(sid), req.scenario_ids)

    @api.get("/api/sessions/{sid}/download/release.zip")
    def release_zip(sid: str) -> Response:
        name, body = svc.release_zip(session(sid))
        return Response(body, media_type="application/zip", headers=_attachment(name))

    @api.get("/api/sessions/{sid}/releases")
    def releases(sid: str) -> list[dict[str, Any]]:
        return svc.releases(session(sid))

    @api.get("/api/sessions/{sid}/releases/{rid}")
    def release_results(sid: str, rid: str) -> dict[str, Any]:
        return svc.release_results(session(sid), rid)

    @api.get("/api/sessions/{sid}/releases/{rid}/release.zip")
    def kept_release_zip(sid: str, rid: str) -> Response:
        name, body = svc.release_zip(session(sid), rid)
        return Response(body, media_type="application/zip", headers=_attachment(name))

    @api.get("/api/sessions/{sid}/download/plan.yaml")
    def plan_yaml(sid: str) -> PlainTextResponse:
        return PlainTextResponse(
            svc.plan_yaml(session(sid)), headers={"Content-Disposition": 'attachment; filename="plan.yaml"'}
        )

    @api.get("/api/sessions/{sid}/download/detection.json")
    def detection_json(sid: str) -> PlainTextResponse:
        body = svc.detection_json(session(sid))
        return PlainTextResponse(body, media_type="application/json", headers=_attachment("detection.json"))

    @api.get("/api/{rest:path}")
    def unknown(rest: str) -> None:
        raise HTTPException(404, f"no such API route: /api/{rest}")

    @api.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    api.mount("/static", StaticFiles(directory=STATIC), name="static")

    @api.middleware("http")
    async def recheck_page(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"  # the browser rechecks, so an updated app is never stale
        return response

    return api


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn  # noqa: PLC0415 (only needed when serving)

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("the app serves this machine only; use 127.0.0.1")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
