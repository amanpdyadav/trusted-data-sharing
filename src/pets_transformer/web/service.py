"""What the web app does, as plain functions over a session. The HTTP layer only parses requests and calls these.

Steps: data -> scan (detect + risk scan) -> plan (preset or custom receiver) -> review -> approve -> run -> results.
Everything runs on this machine with the same engine as the command line.
"""

import io
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pandas as pd

from pets_transformer.aggregate import BudgetExceededError, EpsilonLedger
from pets_transformer.assess.lookalikes import attacker_views, lookalikes
from pets_transformer.assess.riskscan import scan
from pets_transformer.assess.usefulness import column_changes, dp_accuracy
from pets_transformer.config import Settings
from pets_transformer.contracts import (
    ColumnAction,
    ColumnDetection,
    Evidence,
    EvidenceKind,
    Plan,
    PrivacyRole,
    Subtype,
    Technique,
)
from pets_transformer.detect.rules import detect_source
from pets_transformer.keys import DerivedKeyProvider, KeyScope
from pets_transformer.pipeline import RunSettings, protect_table, publish_aggregates, run_release
from pets_transformer.plan.common import REVIEW
from pets_transformer.plan.policy import RulePolicy
from pets_transformer.plan.scenario import Scenario, load_scenarios
from pets_transformer.plan.statistics import load_codelists
from pets_transformer.text.redactor import build_redactor
from pets_transformer.web.workspace import Session, Workspace, WorkspaceError

PREVIEW_ROWS = 6
TEXT_SAMPLES = 6
K_VALUES = (2, 3, 5, 8, 10, 15, 20)
EPSILON_FACTORS = (0.25, 0.5, 1.0, 2.0, 4.0)
TAG = re.compile(r"\[([A-Z_]+)\]")


@dataclass(frozen=True)
class Override:
    """A reviewer's correction of one detected column."""

    table: str
    column: str
    privacy_role: str
    subtype: str
    by: str = ""


@dataclass(frozen=True)
class ActionEdit:
    """A reviewer's change of the protection for one column."""

    table: str
    column: str
    technique: str
    params: dict[str, Any]


@dataclass(frozen=True)
class App:
    settings: Settings
    workspace: Workspace

    # ------------------------------------------------------------ catalogue
    def samples(self) -> list[dict[str, Any]]:
        """Example datasets that ship with the challenge package (synthetic), if it is present."""
        root = self.settings.package_root / "data"
        if not root.is_dir():
            return []
        out = []
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            tables = sorted(folder.glob("*.csv"))
            if tables:
                out.append({"name": folder.name, "tables": [t.stem for t in tables]})
        return out

    def scenarios(self) -> list[dict[str, Any]]:
        return [_scenario_card(s) for s in load_scenarios(self.settings.scenario_dirs).values()]

    def policy(self) -> RulePolicy:
        return RulePolicy(load_codelists(self.settings.codelist_dir))

    # ------------------------------------------------------------ data
    def open_sample(self, name: str) -> Session:
        if name not in {s["name"] for s in self.samples()}:
            raise WorkspaceError(f"unknown sample dataset {name!r}")
        return self.workspace.from_folder(name, self.settings.package_root / "data" / name)

    def overview(self, s: Session) -> dict[str, Any]:
        return {
            "id": s.id, "name": s.name,
            "tables": [
                {"name": t, "rows": len(f), "columns": list(f.columns), "preview": _records(f.head(PREVIEW_ROWS))}
                for t, f in s.tables().items()
            ],
            "steps": {"scanned": s.detections is not None, "planned": s.plan is not None,
                      "approved": bool(s.plan and s.plan.approved), "released": s.outcome is not None},
        }  # fmt: skip

    # ------------------------------------------------------------ scan
    def scan(self, s: Session) -> dict[str, Any]:
        if s.detections is None:
            s.detections = detect_source(s.source(), s.name)
        risk = scan(s.detections, s.tables())
        return {"detections": s.detections.model_dump(mode="json"), "risk": risk.as_dict()}

    def override(self, s: Session, o: Override) -> dict[str, Any]:
        det = _need(s.detections, "scan the data first")
        new = ColumnDetection(
            table=o.table, column=o.column, privacy_role=PrivacyRole(o.privacy_role), subtype=Subtype(o.subtype),
            confidence=1.0, evidence=[Evidence(kind=EvidenceKind.MANUAL, detail=f"set by {o.by or 'reviewer'}")],
        )  # fmt: skip
        if not any(c.table == o.table and c.column == o.column for c in det.columns):
            raise WorkspaceError(f"no column {o.table}.{o.column}")
        cols = [new if (c.table, c.column) == (o.table, o.column) else c for c in det.columns]
        s.detections = det.model_copy(update={"columns": cols})
        s.changed("detections")
        return new.model_dump(mode="json")

    # ------------------------------------------------------------ plan
    def make_plan(self, s: Session, scenario_id: str | None, custom: dict[str, Any] | None) -> dict[str, Any]:
        det = _need(s.detections, "scan the data first")
        if custom is not None:
            scenario = Scenario.model_validate({"schema_version": "1", "dataset": s.name, **custom})
        else:
            found = load_scenarios(self.settings.scenario_dirs)
            if scenario_id not in found:
                raise WorkspaceError(f"unknown receiver {scenario_id!r}")
            scenario = found[scenario_id]
        try:
            plan = self.policy().plan(det, scenario)
        except ValueError as exc:
            raise WorkspaceError(f"this receiver's request does not fit the data: {exc}") from exc
        s.scenario, s.plan = scenario, plan.model_copy(update={"dataset": s.name})
        s.changed("plan")
        return self.plan_view(s)

    def plan_view(self, s: Session) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        reviews = [f"{a.table}.{a.column}" for a in plan.actions if a.reason.startswith(REVIEW)]
        reviews += [f"statistic {a.name}" for a in plan.aggregates if a.reason.startswith(REVIEW)]
        withheld = sorted(set(s.tables()) - set(plan.tables) - {a.table for a in plan.aggregates})
        return {
            "plan": plan.model_dump(mode="json"), "scenario": _scenario_card(s.scenario) if s.scenario else None,
            "reviews": reviews, "withheld_tables": withheld,
        }  # fmt: skip

    def edit_action(self, s: Session, e: ActionEdit) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        old = plan.action_for(e.table, e.column)
        if old is None:
            raise WorkspaceError(f"the plan has no decision for {e.table}.{e.column}")
        new = ColumnAction(
            table=e.table, column=e.column, technique=Technique(e.technique), params=e.params,
            reason=f"Changed in review from {old.technique.value} to {e.technique}.",
        )  # fmt: skip
        actions = [new if a is old else a for a in plan.actions]
        gone = str(old.params.get("rename_to", e.column)) if new.technique is Technique.DROP else None
        qis = {t: [q for q in cols if not (t == e.table and q == gone)] for t, cols in plan.quasi_identifiers.items()}
        s.plan = plan.model_copy(update={"actions": actions, "quasi_identifiers": qis, "approved": False})
        s.changed("plan")
        return self.plan_view(s)

    def set_k(self, s: Session, k: int) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        s.plan = Plan.model_validate(plan.model_dump() | {"k_target": k, "approved": False, "approved_by": None})
        s.changed("plan")
        return self.plan_view(s)

    def approve(self, s: Session, by: str, confirm_review: bool) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        view = self.plan_view(s)
        if not by.strip():
            raise WorkspaceError("type the name of the person who approves the plan")
        if view["reviews"] and not confirm_review:
            raise WorkspaceError(f"open review items: {', '.join(view['reviews'])}; check them, then confirm")
        s.plan = plan.model_copy(update={"approved": True, "approved_by": by.strip()})
        return self.plan_view(s)

    # ------------------------------------------------------------ run and results
    def scope(self, s: Session, receiver: str) -> KeyScope:
        plan = _need(s.plan, "make a plan first")
        month = plan.created_at.strftime("%Y-%m")
        return KeyScope(DerivedKeyProvider.from_env(), f"{plan.scenario_id}/{receiver}/{month}")

    def run(self, s: Session, receiver: str) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        if not plan.approved:
            raise WorkspaceError("approve the plan before releasing")
        receiver = re.sub(r"[^A-Za-z0-9_\-]", "-", receiver.strip()) or "receiver"
        if s.layout.root.joinpath("release").exists():
            for sub in ("release", "private"):
                for f in (s.root / sub).glob("*"):
                    f.unlink()
        s.outcome = run_release(s.source(), plan, self.scope(s, receiver), s.layout, RunSettings())
        s.receiver, s.published = receiver, False
        return self.results(s)

    def results(self, s: Session) -> dict[str, Any]:
        plan, outcome = _need(s.plan, "make a plan first"), _need(s.outcome, "run the release first")
        raw = s.tables()
        released = {t.name: t.frame for t in outcome.tables}
        published = {a.name: a.frame for a in outcome.aggregates}
        scope = self.scope(s, s.receiver)
        return {
            "release_id": outcome.manifest.release_id,
            "files": [f.model_dump(mode="json") for f in outcome.manifest.files],
            "tables": [
                {"name": t.name, "rows_in": t.rows_in, "rows_out": len(t.frame),
                 "preview": _records(t.frame.head(PREVIEW_ROWS)),
                 "raw_preview": _records(raw[t.name].head(PREVIEW_ROWS)),
                 "changes": [asdict(c) for c in column_changes(plan, t.name, raw[t.name], t.frame)],
                 "suppression": None if t.suppression is None else {
                     "rows_removed": t.suppression.rows_removed, "cells_blanked": t.suppression.cells_blanked}}
                for t in outcome.tables
            ],
            "attacker": [v.as_dict() for v in attacker_views(plan, raw, released)],
            "statistics": [
                {"name": a.name, "preview": _records(a.frame.head(12)), "cells": len(a.frame)}
                for a in outcome.aggregates
            ],
            "accuracy": [asdict(a) for a in dp_accuracy(plan, raw, published, scope)],
            "text": self._text_samples(s),
            "residual_risks": outcome.manifest.residual_risks,
            "epsilon": plan.epsilon_spent if plan.aggregates else None,
            "published": s.published,
        }  # fmt: skip

    def _text_samples(self, s: Session) -> list[dict[str, Any]]:
        plan, raw = _need(s.plan, "make a plan first"), s.tables()
        out = []
        for a in (a for a in plan.actions if a.technique is Technique.REDACT_TEXT):
            refs = [str(r).split(".", 1) for r in a.params.get("known_from", [])]
            names = [v for t, c in refs if t in raw and c in raw[t] for v in raw[t][c] if v]
            redactor = build_redactor(names)
            values = [v for v in raw[a.table][a.column] if v][:200]
            picked = sorted(values, key=lambda v: -len(redactor.spans(v)))[:TEXT_SAMPLES]
            out.append({"column": f"{a.table}.{a.column}", "samples": [_parts(v, redactor.spans(v)) for v in picked]})
        return out

    # ------------------------------------------------------------ trade-offs and comparison
    def tradeoff(self, s: Session) -> dict[str, Any]:
        """How privacy and usefulness move with k (row releases) or epsilon (statistics), without releasing."""
        plan = _need(s.plan, "make a plan first")
        raw, scope = s.tables(), self.scope(s, "preview")
        out: dict[str, Any] = {"k": [], "epsilon": []}
        if plan.quasi_identifiers:
            for k in K_VALUES:
                trial = plan.model_copy(update={"k_target": k})
                guess, kept_cells, kept_rows = [], 0.0, 0.0
                for table, qis in plan.quasi_identifiers.items():
                    t = protect_table(table, raw[table], trial, scope, raw)
                    guess.append(lookalikes(t.frame, qis).guess_chance)
                    filled = (t.frame[qis] != "").to_numpy().mean() if len(t.frame) else 0.0
                    kept_cells, kept_rows = float(filled), len(t.frame) / max(t.rows_in, 1)
                out["k"].append({"k": k, "guess_chance": round(max(guess), 4), "cells_kept": round(kept_cells, 4),
                                 "rows_kept": round(kept_rows, 4), "current": k == plan.k_target})  # fmt: skip
        if plan.aggregates:
            for f in EPSILON_FACTORS:
                aggs = [a.model_copy(update={"epsilon": a.epsilon * f}) for a in plan.aggregates]
                trial = plan.model_copy(update={"aggregates": aggs, "epsilon": None})
                published = {a.name: a.frame for a in publish_aggregates(trial, raw, scope)}
                acc = [a for a in dp_accuracy(trial, raw, published, scope) if a.mean_relative_error is not None]
                weights = np.array([a.compared_cells for a in acc], dtype=float)
                err = float(np.average([a.mean_relative_error for a in acc], weights=weights)) if acc else None
                out["epsilon"].append(
                    {"epsilon": round(trial.epsilon_spent, 4), "mean_error": err, "current": f == 1.0}
                )
        return out

    def compare(self, s: Session, scenario_ids: list[str]) -> dict[str, Any]:
        """The same columns under different receivers: what each one would get."""
        det = _need(s.detections, "scan the data first")
        found = load_scenarios(self.settings.scenario_dirs)
        plans = {i: self.policy().plan(det, found[i]) for i in scenario_ids if i in found}
        if s.plan is not None and s.scenario is not None:
            plans[s.scenario.id] = s.plan
        rows = []
        for c in det.columns:
            row: dict[str, Any] = {"table": c.table, "column": c.column, "role": c.privacy_role.value}
            for sid, p in plans.items():
                a = p.action_for(c.table, c.column)
                stats = [
                    g.name
                    for g in p.aggregates
                    if g.table == c.table and any(d.column == c.column for d in g.dimensions)
                ]
                row[sid] = a.technique.value if a else ("statistics" if stats else "withheld")
            rows.append(row)
        return {"receivers": [_scenario_card(found.get(i) or s.scenario) for i in plans], "rows": rows}  # type: ignore[arg-type]

    # ------------------------------------------------------------ downloads
    def release_zip(self, s: Session) -> bytes:
        """The shareable release: protected tables and manifest only. Publishing spends the privacy budget."""
        plan, outcome = _need(s.plan, "make a plan first"), _need(s.outcome, "run the release first")
        if plan.aggregates and not s.published:
            dp = plan.differential_privacy
            ledger = EpsilonLedger(self.settings.epsilon_ledger, dp.budget_cap if dp else None)
            try:
                ledger.record(outcome.manifest.release_id, outcome.manifest.key_domain, plan.epsilon_spent,
                              datetime.now(UTC))  # fmt: skip
            except BudgetExceededError as exc:
                raise WorkspaceError(str(exc)) from exc
        s.published = True
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted((s.root / "release").iterdir()):
                z.write(f, f"{outcome.manifest.release_id}/{f.name}")
        return buf.getvalue()

    def plan_yaml(self, s: Session) -> str:
        path = s.root / "plan.yaml"
        _need(s.plan, "make a plan first").save(path)
        return path.read_text(encoding="utf-8")

    def detection_json(self, s: Session) -> str:
        return _need(s.detections, "scan the data first").model_dump_json(indent=2)


# ---------------------------------------------------------------- helpers
T = TypeVar("T")


def _need(value: T | None, message: str) -> T:
    if value is None:
        raise WorkspaceError(message)
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()} for row in frame.to_dict("records")]


def _parts(text: str, spans: list[Any]) -> list[dict[str, str]]:
    parts, cursor = [], 0
    for sp in spans:
        if sp.start < cursor:
            continue
        parts += [{"t": text[cursor : sp.start]}, {"t": text[sp.start : sp.end], "label": sp.label.value}]
        cursor = sp.end
    parts.append({"t": text[cursor:]})
    return [p for p in parts if p["t"]]


def _scenario_card(s: Scenario) -> dict[str, Any]:
    return {
        "id": s.id, "title": s.title, "recipient": s.recipient, "purpose": s.purpose, "dataset": s.dataset,
        "trust_level": s.trust_level.value, "kind": "statistics" if s.statistics and not s.needs else "rows",
        "legal_context": s.legal_context, "needs": [n.model_dump() for n in s.needs],
        "statistics": [st.name for st in s.statistics], "k": s.targets.k, "epsilon": s.targets.epsilon,
    }  # fmt: skip


def package_path(settings: Settings) -> Path:
    return settings.package_root
