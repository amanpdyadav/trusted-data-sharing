"""Turning the engine's objects into the plain dicts the web app shows. No I/O and no decisions: presentation only."""

from typing import Any

import pandas as pd

from pets_transformer.contracts import Plan, Technique
from pets_transformer.pipeline import ProtectedTable, RunOutcome
from pets_transformer.plan.scenario import Scenario
from pets_transformer.web.workspace import Session


def records(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()} for row in frame.to_dict("records")]


def text_parts(text: str, spans: list[Any]) -> list[dict[str, str]]:
    parts, cursor = [], 0
    for sp in spans:
        if sp.start < cursor:
            continue
        parts += [{"t": text[cursor : sp.start]}, {"t": text[sp.start : sp.end], "label": sp.label.value}]
        cursor = sp.end
    parts.append({"t": text[cursor:]})
    return [p for p in parts if p["t"]]


def technique(plan: Plan, table: str, column: str, *, detail: bool = False) -> str:
    """What a plan does with one column: its technique, statistics only, or withheld."""
    a = plan.action_for(table, column)
    if a is None:
        stats = any(g.table == table and any(d.column == column for d in g.dimensions) for g in plan.aggregates)
        return "statistics" if stats else "withheld"
    if detail and a.technique is Technique.GENERALISE:
        to = a.params.get("to")
        return f"generalise: {a.params.get('unit') if to == 'time' else to}"
    return a.technique.value


def pairs(raw: pd.DataFrame, t: ProtectedTable, key: str | None, limit: int) -> list[dict[str, dict[str, str]]]:
    """The first released rows next to the raw records they came from (matched with the private row map)."""
    if key is None or t.record_ids is None or key not in raw.columns:
        return []
    by_id = raw.assign(_id=raw[key].astype(str)).drop_duplicates("_id").set_index("_id")
    out = []
    for pos, rid in enumerate(t.record_ids[:limit]):
        if rid in by_id.index:
            out.append({"raw": records(by_id.loc[[rid]])[0], "released": records(t.frame.iloc[[pos]])[0]})
    return out


def release_summary(
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


def receiver_tables(s: Scenario) -> set[str]:
    """The tables a receiver asks for: the app offers it only for data that has all of them."""
    return {n.table for n in s.needs if n.table} | {st.table for st in s.statistics}


def scenario_card(s: Scenario) -> dict[str, Any]:
    """A receiver as the app lists it, with the tables it needs (it is offered only for data that has them all)."""
    return {
        "id": s.id, "title": s.title, "recipient": s.recipient, "purpose": s.purpose, "dataset": s.dataset,
        "trust_level": s.trust_level.value, "kind": "statistics" if s.statistics and not s.needs else "rows",
        "legal_context": s.legal_context, "needs": [n.model_dump() for n in s.needs],
        "statistics": [st.name for st in s.statistics], "k": s.targets.k, "epsilon": s.targets.epsilon,
        "tables": sorted(receiver_tables(s)),
    }  # fmt: skip
