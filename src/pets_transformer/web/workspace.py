"""Sessions of the local web app: one folder per piece of work, under the output directory, never uploaded anywhere.

<out>/web/<session>/data/      the tables the user uploaded or picked (CSV)
<out>/web/<session>/release/   protected tables + manifest.json (what may be shared)
<out>/web/<session>/private/   row maps (never offered for download)
"""

import re
import secrets
import shutil
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import pandas as pd

from pets_transformer.contracts import DetectionReport, Plan
from pets_transformer.pipeline import OutputLayout, RunOutcome
from pets_transformer.plan.scenario import Scenario
from pets_transformer.sources import CsvFolderSource

TABLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")
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

    def changed(self, what: str) -> None:
        """Clear what was built on a changed step: new detections need a new plan, a new plan a new run."""
        if what == "detections":
            self.plan = None
        self.outcome = None
        self.published = False


@dataclass
class Workspace:
    root: Path
    sessions: dict[str, Session] = field(default_factory=dict)

    def get(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            raise WorkspaceError(f"unknown session {session_id!r}; start again from the data step")
        return self.sessions[session_id]

    def _new(self, name: str) -> Session:
        sid = secrets.token_hex(6)
        session = Session(sid, _clean_name(name), self.root / sid)
        session.data.mkdir(parents=True)
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
        session = self._new(name)
        for table, content in tables.items():
            (session.data / f"{table}.csv").write_bytes(content)
        return session


def _table_name(filename: str) -> str:
    stem = Path(filename).name.rsplit(".", 1)[0]
    if not TABLE_NAME.match(stem):
        raise WorkspaceError(f"{filename}: table names may use letters, digits, '_' and '-' only")
    return stem


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())[:40]
    return cleaned or "dataset"
