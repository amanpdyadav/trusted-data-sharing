"""What the web app does, as plain functions over a session. The HTTP layer only parses requests and calls these.

Steps: data -> scan (detect + risk scan) -> plan (preset or custom receiver) -> review -> approve -> run -> results.
Everything runs on this machine with the same engine as the command line.
"""

import csv
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pandas as pd

from pets_transformer.aggregate import BudgetExceededError, EpsilonLedger
from pets_transformer.assess import attack
from pets_transformer.assess.lookalikes import attacker_views, lookalikes
from pets_transformer.assess.riskscan import TableLink, find_links, scan
from pets_transformer.assess.usefulness import column_changes, dp_accuracy
from pets_transformer.columns import NamingError, check_names, is_unnamed, looks_headerless, suggest
from pets_transformer.config import Settings
from pets_transformer.contracts import (
    ColumnAction,
    ColumnDetection,
    ColumnName,
    Evidence,
    EvidenceKind,
    Plan,
    PrivacyRole,
    Subtype,
    Technique,
)
from pets_transformer.detect.rules import detect_source
from pets_transformer.keys import DerivedKeyProvider, KeyScope
from pets_transformer.llm import build_llm
from pets_transformer.pipeline import (
    ProtectedTable,
    RunOutcome,
    RunSettings,
    protect_table,
    publish_aggregates,
    release_id,
    run_release,
    transform_rows,
)
from pets_transformer.plan.common import REVIEW
from pets_transformer.plan.diff import describe, plan_changes
from pets_transformer.plan.policy import RulePolicy
from pets_transformer.plan.scenario import Scenario, load_scenarios
from pets_transformer.plan.statistics import load_codelists
from pets_transformer.text.redactor import build_redactor
from pets_transformer.web.workspace import Session, Workspace, WorkspaceError

PREVIEW_ROWS = 6
EXAMPLE_ROWS = 3
TEXT_SAMPLES = 6
K_VALUES = (2, 3, 5, 8, 10, 15, 20)
EPSILON_FACTORS = (0.25, 0.5, 1.0, 2.0, 4.0)
TAG = re.compile(r"\[([A-Z_]+)\]")
RESULTS = Path("results")  # committed benchmark results and the presentation screens' data (built by evaluation)


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
class NewName:
    """A name for one unnamed column, as confirmed in the dialog."""

    original: str
    name: str
    suggested_by: str = "person"  # rules | ai | person (the person changed or typed it)
    meaning: str = ""


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
        ai = self.settings.llm
        return {
            "id": s.id, "name": s.name,
            "tables": [
                {"name": t, "rows": len(f), "columns": list(f.columns), "preview": _records(f.head(PREVIEW_ROWS)),
                 "naming": self._naming(s, t)}
                for t, f in s.tables().items()
            ],
            "ai": {"on": ai.enabled, "model": ai.model if ai.enabled else None},  # the "Suggest names" button
            "steps": {"scanned": s.detections is not None, "planned": s.plan is not None,
                      "approved": bool(s.plan and s.plan.approved), "released": s.outcome is not None},
            "released": s.released,  # released data is frozen: duplicate to change it
        }  # fmt: skip

    # ------------------------------------------------------------ columns without a name
    def _naming(self, s: Session, table: str) -> dict[str, Any]:
        """Which input columns have no real name, and the names they were given so far."""
        raw = s.raw_columns(table)
        given = {c.original: c for c in s.column_names if c.table == table}
        unnamed = [
            {"original": c, "name": given[c].name if c in given else None,
             "suggested_by": given[c].suggested_by if c in given else None}
            for c in raw if is_unnamed(c)
        ]  # fmt: skip
        headerless = table in s.headerless
        return {
            "unnamed": unnamed,
            "headerless": headerless,
            "headerless_guess": not headerless and looks_headerless(raw),
        }

    def suggest_names(
        self, s: Session, table: str, columns: list[str] | None, avoid: dict[str, list[str]] | None
    ) -> dict[str, Any]:
        """Rules first, then the local AI on a short summary of each column. Nothing is renamed here."""
        s.editable()
        if table not in s.tables():
            raise WorkspaceError(f"no table {table!r} in {s.name}")
        frame = s.raw_source().read(table)
        todo = columns if columns else [c for c in frame.columns if is_unnamed(c)]
        try:
            return suggest(frame, table, todo, build_llm(self.settings.llm), avoid).as_dict()
        except NamingError as exc:
            raise WorkspaceError(str(exc)) from exc

    def set_names(self, s: Session, table: str, names: list[NewName]) -> dict[str, Any]:
        """Use the confirmed names for one table's unnamed columns. The scan and plan start over."""
        s.editable()
        if table not in s.tables():
            raise WorkspaceError(f"no table {table!r} in {s.name}")
        model = self.settings.llm.model
        given = [
            ColumnName(table=table, original=n.original, name=n.name.strip(), suggested_by=n.suggested_by,
                       model=model if n.suggested_by == "ai" else None, meaning=n.meaning[:200])
            for n in names if n.name.strip()
        ]  # fmt: skip
        try:
            check_names(s.raw_columns(table), given)
        except NamingError as exc:
            raise WorkspaceError(str(exc)) from exc
        s.set_columns(table, given)
        return self.overview(s)

    def set_headerless(self, s: Session, table: str, headerless: bool) -> dict[str, Any]:
        """The file has no header row: its first row is data. Names given to its columns start over."""
        s.editable()
        if table not in s.tables():
            raise WorkspaceError(f"no table {table!r} in {s.name}")
        s.set_columns(table, headerless=headerless)
        return self.overview(s)

    # ------------------------------------------------------------ scan
    def scan(self, s: Session) -> dict[str, Any]:
        """Detections, risk scan and the attack on one person. Kept with the session: it is slow on big data."""
        if s.detections is None:
            det = detect_source(s.source(), s.name)
            given = {(c.table, c.name): c.original for c in s.column_names}
            if given:  # detection.json keeps the input header of every column a person named
                cols = [c.model_copy(update={"source_column": given.get((c.table, c.column))}) for c in det.columns]
                det = det.model_copy(update={"columns": cols})
            s.detections = det
            s.save()
        cached = s.cached_scan()
        if cached is None:
            det, frames = s.detections, s.tables()
            links = find_links(det, frames)
            cached = {"risk": scan(det, frames, links).as_dict(), "links": [asdict(x) for x in links]}
            cached |= self._attack_on(s, attack.pick_target(det, frames, links), links)
            s.cache_scan(cached)
        return {"detections": s.detections.model_dump(mode="json"), "risk": cached["risk"], "attack": cached["attack"]}

    def another_person(self, s: Session, seed: int | None) -> dict[str, Any] | None:
        """Attack someone else, picked at random among the people whose records reach the most tables."""
        self.scan(s)
        cached = s.cached_scan() or {}
        det, frames = _need(s.detections, "scan the data first"), s.tables()
        if "links" not in cached:  # a scan saved by an earlier version
            cached["links"] = [asdict(x) for x in find_links(det, frames)]
        links = [TableLink(**x) for x in cached["links"]]
        target = attack.pick_target(det, frames, links, np.random.default_rng(seed))
        cached |= self._attack_on(s, target, links)
        s.cache_scan(cached)
        return self.attack(s)

    def _attack_on(self, s: Session, target: attack.Target | None, links: list[TableLink]) -> dict[str, Any]:
        if target is None:
            return {"attack": None, "target": None}
        det, frames = _need(s.detections, "scan the data first"), s.tables()
        before = attack.on_raw(det, frames, target, attack.reach(det, frames, links, target))
        trail = [asdict(h) for h in attack.trail(det, frames, links, target)]
        return {"attack": {"before": before.as_dict(), "trail": trail, "after": None}, "target": asdict(target)}

    def attack(self, s: Session) -> dict[str, Any] | None:
        """The linkage attack on one person, on the raw data and (once released) on the release."""
        if s.cached_scan() is None:
            self.scan(s)
        cached = s.cached_scan()
        if not cached or not cached["target"]:
            return None
        out: dict[str, Any] = {**cached["attack"], "after": None}
        if s.outcome is not None and s.plan is not None:
            det, frames = _need(s.detections, "scan the data first"), s.tables()
            released = {t.name: t.frame for t in s.outcome.tables}
            ids = {t.name: t.record_ids for t in s.outcome.tables if t.record_ids is not None}
            copy = attack.ReleasedCopy(s.plan, released, ids)
            out["after"] = attack.on_release(det, frames, attack.Target(**cached["target"]), copy).as_dict()
        return out

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
        s.save()
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
        s.scenario, s.plan = scenario, plan.model_copy(update={"dataset": s.name, "column_names": s.column_names})
        s.changed("plan")
        s.record_plan(f"New plan for {scenario.recipient}")
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
        s.record_plan(f"{e.table}.{e.column}: {describe(old)} → {describe(new)}")
        return self.plan_view(s)

    def set_k(self, s: Session, k: int) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        s.plan = Plan.model_validate(plan.model_dump() | {"k_target": k, "approved": False, "approved_by": None})
        s.changed("plan")
        s.record_plan(f"Protection level {plan.k_target} → {k}")
        return self.plan_view(s)

    def approve(self, s: Session, by: str, confirm_review: bool) -> dict[str, Any]:
        plan = _need(s.plan, "make a plan first")
        view = self.plan_view(s)
        if not by.strip():
            raise WorkspaceError("type the name of the person who approves the plan")
        if view["reviews"] and not confirm_review:
            raise WorkspaceError(f"open review items: {', '.join(view['reviews'])}; check them, then confirm")
        s.plan = plan.model_copy(update={"approved": True, "approved_by": by.strip()})
        s.record_plan(f"Approved by {by.strip()}")
        return self.plan_view(s)

    # ------------------------------------------------------------ plan versions
    def plan_versions(self, s: Session) -> dict[str, Any]:
        released = {r["plan_version"]: r["release_id"] for r in s.releases() if r.get("plan_version")}

        def card(v: dict[str, Any]) -> dict[str, Any]:
            plan, scenario = v["plan"], v["scenario"] or {}
            return {
                "version": v["version"], "created_at": v["created_at"], "note": v["note"], "approved": plan["approved"],
                "approved_by": plan.get("approved_by"), "recipient": scenario.get("recipient", plan["scenario_id"]),
                "released_as": released.get(v["version"]),
            }  # fmt: skip

        return {"current": s.plan_version, "versions": [card(v) for v in s.plan_versions()]}

    def plan_yaml_at(self, s: Session, version: int | None) -> str:
        plan = s.plan_at(version)[0] if version else _need(s.plan, "make a plan first")
        return plan.to_yaml()

    def compare_plans(self, s: Session, a: int, b: int) -> dict[str, Any]:
        old, new = s.plan_at(a)[0], s.plan_at(b)[0]
        return {
            "changes": [asdict(c) for c in plan_changes(old, new)],
            "yaml_a": old.to_yaml(),
            "yaml_b": new.to_yaml(),
        }

    def restore_plan(self, s: Session, version: int) -> dict[str, Any]:
        """Make an earlier version the current plan. An approved version stays approved: it is what was signed."""
        plan, scenario, _ = s.plan_at(version)
        s.plan, s.scenario = plan, scenario
        s.changed("plan")
        s.record_plan(f"Back to version {version}")
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
        created = datetime.now(UTC)
        while (s.releases_dir / release_id(plan, created)).exists():  # two releases in one second keep apart
            created += timedelta(seconds=1)
        s.outcome = run_release(s.source(), plan, self.scope(s, receiver), s.layout, RunSettings(clock=lambda: created))
        s.receiver, s.published = receiver, False
        results = self.results(s)
        s.archive(s.outcome.manifest.release_id, results)
        return results

    def results(self, s: Session) -> dict[str, Any]:
        plan, outcome = _need(s.plan, "make a plan first"), _need(s.outcome, "run the release first")
        raw = s.tables()
        released = {t.name: t.frame for t in outcome.tables}
        published = {a.name: a.frame for a in outcome.aggregates}
        scope = self.scope(s, s.receiver)
        attacker = [v.as_dict() for v in attacker_views(plan, raw, released)]
        attack_replay = self.attack(s)
        return {
            "release_id": outcome.manifest.release_id,
            "files": [f.model_dump(mode="json") for f in outcome.manifest.files],
            "tables": [
                {"name": t.name, "rows_in": t.rows_in, "rows_out": len(t.frame),
                 "preview": _records(t.frame.head(PREVIEW_ROWS)),
                 "raw_preview": _records(raw[t.name].head(PREVIEW_ROWS)),
                 "pairs": _pairs(raw[t.name], t, plan.record_keys.get(t.name)),
                 "changes": [asdict(c) for c in column_changes(plan, t.name, raw[t.name], t.frame)],
                 "suppression": None if t.suppression is None else {
                     "rows_removed": t.suppression.rows_removed, "cells_blanked": t.suppression.cells_blanked}}
                for t in outcome.tables
            ],
            "attacker": attacker,
            "attack": attack_replay,
            "summary": _summary(s, plan, outcome, attacker, attack_replay),
            "techniques": {f"{c.table}.{c.column}": _technique(plan, c.table, c.column, detail=True)
                           for c in _need(s.detections, "scan the data first").columns},
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

    def plan_example(self, s: Session) -> dict[str, Any]:
        """A few records before and after the plan, made by the real transforms (the attacked person first)."""
        plan = _need(s.plan, "make a plan first")
        raw, scope = s.tables(), self.scope(s, "preview")
        target = (s.cached_scan() or {}).get("target") or {}
        out = []
        for table in plan.tables:
            frame = raw[table]
            first = [int(target["row"])] if target.get("table") == table else []
            rows = frame.iloc[list(dict.fromkeys([*first, *range(min(EXAMPLE_ROWS, len(frame)))]))[:EXAMPLE_ROWS]]
            after = _records(transform_rows(table, rows, plan, scope, raw))
            renamed = {a.column: str(a.params.get("rename_to", a.column)) for a in plan.actions if a.table == table}
            pairs = [{"raw": r, "after": p} for r, p in zip(_records(rows), after, strict=True)]
            out.append({"table": table, "renamed": renamed, "rows": pairs})
        return {"tables": out}

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
        """The same columns under different receivers: what each one would get.

        Only receivers that fit this data are compared. One made for other data (it asks for tables this dataset
        does not have) or whose request the data cannot meet is listed under `left_out` with the reason, so one
        unfit receiver never breaks the comparison of the others.
        """
        det = _need(s.detections, "scan the data first")
        found = load_scenarios(self.settings.scenario_dirs)
        have = set(s.tables())
        plans: dict[str, Plan] = {}
        left_out: list[dict[str, str]] = []
        for i in scenario_ids:
            if i not in found:
                continue
            missing = sorted(_receiver_tables(found[i]) - have)
            if missing:
                reason = f"made for the {found[i].dataset.replace('_', ' ')} data; needs {', '.join(missing)}"
                left_out.append({"id": i, "recipient": found[i].recipient, "reason": reason})
                continue
            try:
                plans[i] = self.policy().plan(det, found[i])
            except ValueError as exc:
                left_out.append({"id": i, "recipient": found[i].recipient, "reason": str(exc)})
        if s.plan is not None and s.scenario is not None:
            plans[s.scenario.id] = s.plan
        rows = []
        for c in det.columns:
            row: dict[str, Any] = {"table": c.table, "column": c.column, "role": c.privacy_role.value}
            for sid, p in plans.items():
                row[sid] = _technique(p, c.table, c.column)
            rows.append(row)
        receivers = [_scenario_card(found.get(i) or s.scenario) for i in plans]  # type: ignore[arg-type]
        return {"receivers": receivers, "rows": rows, "left_out": left_out}

    # ------------------------------------------------------------ downloads
    def sessions(self) -> list[dict[str, Any]]:
        """Everything worked on in this app: datasets, how far each got, and the releases made from them."""
        out = []
        for x in self.workspace.listing():
            files = sorted(x.data.glob("*.csv"))
            releases = x.releases()
            out.append({
                "id": x.id, "name": x.name, "created_at": x.created_at, "tables": [f.stem for f in files],
                "bytes": sum(f.stat().st_size for f in files), "receiver": x.scenario.recipient if x.scenario else None,
                "steps": {"scanned": x.detections is not None, "planned": x.plan is not None,
                          "approved": bool(x.plan and x.plan.approved)},
                "releases": len(releases), "last_release": releases[0] if releases else None,
                "released": bool(releases),
            })  # fmt: skip
        return out

    def releases(self, s: Session) -> list[dict[str, Any]]:
        return s.releases()

    # ------------------------------------------------------------ release audit (every release, every dataset)
    def audit_releases(self) -> list[dict[str, Any]]:
        """Every release made in this app, newest first, with the dataset it came from."""
        out = [
            {
                **r,
                "session_id": x.id,
                "dataset": x.name,
                "published": (x.release(str(r["release_id"])) / "published").exists(),
            }
            for x in self.workspace.listing()
            for r in x.releases()
        ]
        return sorted(out, key=lambda r: str(r["created_at"]), reverse=True)

    def audit_release(self, s: Session, release_id: str) -> dict[str, Any]:
        """One release's record: the manifest that travelled with it, the attack before and after, the risk left."""
        folder = s.release(release_id)
        results: dict[str, Any] = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        with zipfile.ZipFile(folder / "release.zip") as z:
            manifest = json.loads(z.read(f"{release_id}/manifest.json"))
        return {
            "dataset": s.name, "summary": results["summary"], "manifest": manifest, "attack": results.get("attack"),
            "attacker": results.get("attacker", []), "residual_risks": results.get("residual_risks", []),
            "published": (folder / "published").exists(), "scorecard": _scorecard_for(release_id),
        }  # fmt: skip

    def receivers_benchmark(self) -> dict[str, Any]:
        """The automatic planner measured on every receiver: results/receivers.csv (`make receivers`)."""
        path = RESULTS / "receivers.csv"
        if not path.exists():
            return {"rows": [], "measured_at": None}
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        num = ("privacy", "utility", "composite", "epsilon")
        for r in rows:
            for k in num:
                r[k] = float(r[k]) if r.get(k) else None
            r["released_tables"] = int(r["released_tables"] or 0)
        return {"rows": rows, "measured_at": max((r["measured_at"] for r in rows), default=None)}

    def screens(self) -> list[str]:
        """The presentation screens whose data has been built (`python -m evaluation screens`)."""
        return [n for n in ("mosaic", "audit") if (RESULTS / "screens" / f"{n}.json").exists()]

    def release_results(self, s: Session, release_id: str) -> dict[str, Any]:
        results: dict[str, Any] = json.loads((s.release(release_id) / "results.json").read_text(encoding="utf-8"))
        results["published"] = (s.release(release_id) / "published").exists()
        return results

    def release_zip(self, s: Session, release_id: str | None = None) -> tuple[str, bytes]:
        """A kept release: protected tables and manifest only. Publishing statistics spends the privacy budget."""
        if release_id is None:
            release_id = _need(s.outcome, "run the release first").manifest.release_id
        folder, summary = s.release(release_id), self.release_results(s, release_id)["summary"]
        if summary.get("epsilon") is not None and not (folder / "published").exists():
            ledger = EpsilonLedger(self.settings.epsilon_ledger, summary.get("budget_cap"))
            try:
                ledger.record(release_id, summary["key_domain"], summary["epsilon"], datetime.now(UTC))
            except BudgetExceededError as exc:
                raise WorkspaceError(str(exc)) from exc
        (folder / "published").touch()
        if s.outcome is not None and s.outcome.manifest.release_id == release_id:
            s.published = True
        return f"{release_id}.zip", (folder / "release.zip").read_bytes()

    def plan_yaml(self, s: Session) -> str:
        return _need(s.plan, "make a plan first").to_yaml()

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


def _technique(plan: Plan, table: str, column: str, *, detail: bool = False) -> str:
    """What a plan does with one column: its technique, statistics only, or withheld."""
    a = plan.action_for(table, column)
    if a is None:
        stats = any(g.table == table and any(d.column == column for d in g.dimensions) for g in plan.aggregates)
        return "statistics" if stats else "withheld"
    if detail and a.technique is Technique.GENERALISE:
        to = a.params.get("to")
        return f"generalise: {a.params.get('unit') if to == 'time' else to}"
    return a.technique.value


def _pairs(raw: pd.DataFrame, t: ProtectedTable, key: str | None) -> list[dict[str, dict[str, str]]]:
    """The first released rows next to the raw records they came from (matched with the private row map)."""
    if key is None or t.record_ids is None or key not in raw.columns:
        return []
    by_id = raw.assign(_id=raw[key].astype(str)).drop_duplicates("_id").set_index("_id")
    out = []
    for pos, rid in enumerate(t.record_ids[:PREVIEW_ROWS]):
        if rid in by_id.index:
            out.append({"raw": _records(by_id.loc[[rid]])[0], "released": _records(t.frame.iloc[[pos]])[0]})
    return out


def _summary(
    s: Session, plan: Plan, outcome: RunOutcome, attacker: list[dict[str, Any]], replay: dict[str, Any] | None
) -> dict[str, Any]:
    """The headline numbers of one release, for the release history and release-to-release comparison."""
    dp = plan.differential_privacy
    worst = max(attacker, key=lambda v: v["before"]["unique_share"], default=None)
    after = (replay or {}).get("after") or {}
    return {
        "release_id": outcome.manifest.release_id, "created_at": outcome.manifest.created_at.isoformat(),
        "receiver": s.receiver, "scenario_id": plan.scenario_id, "plan_version": s.plan_version,
        "recipient": s.scenario.recipient if s.scenario else plan.scenario_id, "approved_by": plan.approved_by,
        "k": plan.k_target if plan.quasi_identifiers else None,
        "epsilon": plan.epsilon_spent if plan.aggregates else None, "budget_cap": dp.budget_cap if dp else None,
        "key_domain": outcome.manifest.key_domain, "files": [f.name for f in outcome.manifest.files],
        "singled_out_before": worst["before"]["unique_share"] if worst else None,
        "singled_out_after": worst["after"]["unique_share"] if worst else None,
        "guess_chance_after": worst["after"]["guess_chance"] if worst else None,
        "attack_outcome": after.get("outcome"), "attack_matches": after.get("matches"),
    }  # fmt: skip


def _scorecard_for(release_id: str) -> dict[str, Any] | None:
    """The organisers' scorecard of this release, when `python -m evaluation screens` scored it."""
    path = RESULTS / "screens" / "audit.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data if (data.get("manifest") or {}).get("release_id") == release_id else None


def _receiver_tables(s: Scenario) -> set[str]:
    """The tables a receiver asks for: the app offers it only for data that has all of them."""
    return {n.table for n in s.needs if n.table} | {st.table for st in s.statistics}


def _scenario_card(s: Scenario) -> dict[str, Any]:
    return {
        "id": s.id, "title": s.title, "recipient": s.recipient, "purpose": s.purpose, "dataset": s.dataset,
        "trust_level": s.trust_level.value, "kind": "statistics" if s.statistics and not s.needs else "rows",
        "legal_context": s.legal_context, "needs": [n.model_dump() for n in s.needs],
        "statistics": [st.name for st in s.statistics], "k": s.targets.k, "epsilon": s.targets.epsilon,
        "tables": sorted(_receiver_tables(s)),
    }  # fmt: skip


def package_path(settings: Settings) -> Path:
    return settings.package_root
