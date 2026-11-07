"""Sessions of the local web app: one folder per piece of work, under the output directory, never uploaded anywhere.

<out>/web/<session>/session.json, detection.json, plan.json, scenario.json   the work so far (reloaded on start)
<out>/web/<session>/scan.json   the last risk scan (slow on large data), dropped when a detection changes
<out>/web/<session>/data/      the tables the user uploaded or picked (CSV)
<out>/web/<session>/release/   the latest protected tables + manifest.json (what may be shared)
<out>/web/<session>/private/   row maps (never offered for download)
<out>/web/<session>/releases/<release_id>/release.zip    every release made, kept for download and comparison
<out>/web/<session>/releases/<release_id>/results.json   its proof page (holds raw previews: stays on this machine)
<out>/web/<session>/releases/<release_id>/summary.json   its headline numbers, for quick listings
"""

import json
import re
import secrets
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
from pydantic import BaseModel

from pets_transformer.contracts import DetectionReport, Plan
from pets_transformer.pipeline import OutputLayout, RunOutcome
from pets_transformer.plan.scenario import Scenario
from pets_transformer.sources import CsvFolderSource

TABLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,95}$")
ModelT = TypeVar("ModelT", bound=BaseModel)
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


class WorkspaceError(ValueError):
    """Something the user can fix: a bad file name, a missing step, an unknown session."""


@dataclass
class Session:
    id: str
    name: str  # dataset name shown to the user and written into plans
    root: Path
    detections: DetectionReport | None = None
    scenario: Scenario | None = None
    plan: Plan | None = None
    outcome: RunOutcome | None = None
    receiver: str = ""
    published: bool = False  # the release was downloaded: its privacy budget is spent
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def layout(self) -> OutputLayout:
        return OutputLayout(self.root)

    def source(self) -> CsvFolderSource:
        return CsvFolderSource(self.data)

    def tables(self) -> dict[str, pd.DataFrame]:
        """All input tables, read once per session (as text, like every other reader in the tool)."""
        if not self.frames:
            src = self.source()
            self.frames = {t: src.read(t) for t in src.table_names()}
        return self.frames

    def save(self) -> None:
        """Write the work so far, so the session survives a restart of the app."""
        (self.root / "session.json").write_text(json.dumps({"id": self.id, "name": self.name,
                                                            "created_at": self.created_at}))  # fmt: skip
        for name, model in (("detection", self.detections), ("plan", self.plan), ("scenario", self.scenario)):
            path = self.root / f"{name}.json"
            if model is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(model.model_dump_json(), encoding="utf-8")

    @classmethod
    def load(cls, root: Path) -> "Session":
        meta = json.loads((root / "session.json").read_text())

        def read(name: str, model: type[ModelT]) -> ModelT | None:
            path = root / f"{name}.json"
            return model.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

        return cls(
            meta["id"], meta["name"], root, detections=read("detection", DetectionReport),
            scenario=read("scenario", Scenario), plan=read("plan", Plan), created_at=meta["created_at"],
        )  # fmt: skip

    # -------------------------------------------------------- releases kept for download and comparison
    @property
    def releases_dir(self) -> Path:
        return self.root / "releases"

    def archive(self, release_id: str, results: dict[str, object]) -> None:
        """Keep this release: the shareable files as a zip (never the row maps) and its proof page."""
        folder = self.releases_dir / release_id
        folder.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(folder / "release.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted((self.root / "release").iterdir()):
                z.write(f, f"{release_id}/{f.name}")
        (folder / "results.json").write_text(json.dumps(results), encoding="utf-8")
        (folder / "summary.json").write_text(json.dumps(results["summary"]), encoding="utf-8")

    def releases(self) -> list[dict[str, object]]:
        """Summaries of every release, newest first."""
        found = []
        for folder in (p.parent for p in self.releases_dir.glob("*/results.json")):
            summary = folder / "summary.json"
            if not summary.exists():  # kept by an earlier version: write the summary once
                summary.write_text(json.dumps(json.loads((folder / "results.json").read_text())["summary"]))
            found.append(json.loads(summary.read_text(encoding="utf-8")))
        return sorted(found, key=lambda r: str(r["created_at"]), reverse=True)

    # -------------------------------------------------------- the last risk scan, kept because it is slow on big data
    @property
    def _scan_file(self) -> Path:
        return self.root / "scan.json"

    def cached_scan(self) -> dict[str, Any] | None:
        return json.loads(self._scan_file.read_text(encoding="utf-8")) if self._scan_file.exists() else None

    def cache_scan(self, scan: dict[str, Any]) -> None:
        self._scan_file.write_text(json.dumps(scan), encoding="utf-8")

    def release(self, release_id: str) -> Path:
        folder = self.releases_dir / release_id
        if not RELEASE_ID.match(release_id) or not (folder / "results.json").exists():
            raise WorkspaceError(f"unknown release {release_id!r}")
        return folder

    @property
    def released(self) -> bool:
        return any(self.releases_dir.glob("*/results.json"))

    def editable(self) -> None:
        if self.released:
            raise WorkspaceError("this dataset has releases, so its data is frozen; duplicate it to change the data")

    def start_over(self) -> None:
        """The tables changed: the scan, the plan and any unreleased run no longer fit them."""
        self.detections = self.scenario = self.plan = self.outcome = None
        self.frames, self.published = {}, False
        self._scan_file.unlink(missing_ok=True)
        self.save()

    def changed(self, what: str) -> None:
        """Clear what was built on a changed step: new detections need a new plan, a new plan a new run."""
        if what == "detections":
            self.plan = None
            self._scan_file.unlink(missing_ok=True)
        self.outcome = None
        self.published = False


@dataclass
class Workspace:
    root: Path
    sessions: dict[str, Session] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reopen the sessions saved in earlier runs of the app."""
        for meta in sorted(self.root.glob("*/session.json")):
            try:
                session = Session.load(meta.parent)
            except (ValueError, KeyError):
                continue  # a folder from an older version: leave it alone
            self.sessions[session.id] = session

    def listing(self) -> list[Session]:
        return sorted(self.sessions.values(), key=lambda s: s.created_at, reverse=True)

    def get(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            raise WorkspaceError(f"unknown session {session_id!r}; start again from the data step")
        return self.sessions[session_id]

    def _new(self, name: str) -> Session:
        sid = secrets.token_hex(6)
        session = Session(sid, _clean_name(name), self.root / sid)
        session.data.mkdir(parents=True)
        session.save()
        self.sessions[sid] = session
        return session

    def from_folder(self, name: str, folder: Path) -> Session:
        """Copy a folder of CSV files (e.g. one of the sample datasets) into a new session."""
        tables = sorted(folder.glob("*.csv"))
        if not tables:
            raise WorkspaceError(f"no CSV files in {folder}")
        session = self._new(name)
        for path in tables:
            shutil.copy2(path, session.data / path.name)
        return session

    def from_uploads(self, name: str, files: list[tuple[str, bytes]]) -> Session:
        """CSV files, or ZIP archives of CSV files. File names become table names."""
        tables = _read_uploads(files)
        session = self._new(name)
        for table, content in tables.items():
            (session.data / f"{table}.csv").write_bytes(content)
        return session

    # ------------------------------------------------------------ managing datasets
    def add_tables(self, session: Session, files: list[tuple[str, bytes]]) -> list[str]:
        """Add tables to a dataset that has no releases yet (a table with the same name is replaced)."""
        session.editable()
        tables = _read_uploads(files)
        for table, content in tables.items():
            (session.data / f"{table}.csv").write_bytes(content)
        session.start_over()
        return sorted(tables)

    def remove_table(self, session: Session, table: str) -> None:
        session.editable()
        path = session.data / f"{table}.csv"
        if not TABLE_NAME.match(table) or not path.exists():
            raise WorkspaceError(f"no table {table!r} in {session.name}")
        if len(list(session.data.glob("*.csv"))) == 1:
            raise WorkspaceError("a dataset needs at least one table; start a new dataset instead")
        path.unlink()
        session.start_over()

    def duplicate(self, session: Session, name: str = "") -> Session:
        """A new dataset with the same tables and the same column corrections, ready to change and release again."""
        copy = self._new(name or f"{session.name}-copy")
        for path in sorted(session.data.glob("*.csv")):
            shutil.copy2(path, copy.data / path.name)
        copy.detections = session.detections
        copy.save()
        return copy

    def rename(self, session: Session, name: str) -> None:
        session.name = _clean_name(name)
        session.save()

    def delete(self, session: Session) -> None:
        """Remove a dataset that was never released. Released ones stay: each release must stay traceable."""
        if session.released:
            raise WorkspaceError(f"{session.name} has releases and stays as their record; duplicate it to start again")
        if session.root.parent.resolve() != self.root.resolve():
            raise WorkspaceError("refusing to delete a folder outside the workspace")
        shutil.rmtree(session.root)
        del self.sessions[session.id]


def _read_uploads(files: list[tuple[str, bytes]]) -> dict[str, bytes]:
    """Table name -> CSV bytes, from CSV files and ZIP archives of CSV files."""
    tables: dict[str, bytes] = {}
    for filename, content in files:
        if len(content) > MAX_UPLOAD_BYTES:
            raise WorkspaceError(f"{filename} is larger than {MAX_UPLOAD_BYTES // 2**20} MB")
        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(BytesIO(content)) as z:
                for member in z.namelist():
                    if member.lower().endswith(".csv") and not member.startswith("__MACOSX"):
                        tables[_table_name(member)] = z.read(member)
        elif filename.lower().endswith(".csv"):
            tables[_table_name(filename)] = content
        else:
            raise WorkspaceError(f"{filename}: upload CSV files or a ZIP of CSV files")
    if not tables:
        raise WorkspaceError("no CSV tables found in the upload")
    return tables


def _table_name(filename: str) -> str:
    stem = Path(filename).name.rsplit(".", 1)[0]
    if not TABLE_NAME.match(stem):
        raise WorkspaceError(f"{filename}: table names may use letters, digits, '_' and '-' only")
    return stem


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())[:40]
    return cleaned or "dataset"
