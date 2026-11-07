"""Replay a linkage attack on one person: what an outsider learns from the raw data, then from the release.

The outsider knows a few background facts about someone (birth date, sex, postcode: things found in public
registers or on social media). In the raw data those facts often match one row, which hands over the name, the
ID code and, through shared keys, every linked record. The same facts are then looked up in the release.

The target is followed into the release through the private row map (record ids), which stays on this machine;
only counts and the facts the outsider already had are shown.
"""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace

import numpy as np
import pandas as pd

from pets_transformer.assess.kanon import group_sizes
from pets_transformer.assess.riskscan import TableLink
from pets_transformer.contracts import DetectionReport, Plan, PrivacyRole, Subtype, Technique
from pets_transformer.plan.common import PERSON_KEYS

R, S = PrivacyRole, Subtype
EVENT_TIMES = frozenset({S.TIMESTAMP, S.DATE})  # when something happened: rarely background knowledge
MAX_FACTS = 4


class _Dropped:
    technique = Technique.DROP


_DROPPED = _Dropped()  # columns without an action never leave


@dataclass(frozen=True)
class Target:
    table: str
    row: int  # position of the row in the raw table


@dataclass(frozen=True)
class AttackResult:
    table: str
    rows: int  # rows the outsider searches
    known: dict[str, str]  # facts the outsider has, as they know them
    matches: int  # rows that fit those facts (1 = singled out)
    usable: list[str] = field(default_factory=list)  # released columns the facts could still be matched on
    revealed: dict[str, str] = field(default_factory=dict)  # identifiers readable once singled out
    hidden: dict[str, str] = field(default_factory=dict)  # identifier -> how the release hides it
    linked: dict[str, int] = field(default_factory=dict)  # linked table -> rows reached through keys
    outcome: str = ""  # identified / one_in_n / removed / withheld

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _personal(det: DetectionReport, table: str) -> list[str]:
    return [
        c.column for c in det.columns
        if c.table == table and c.privacy_role is R.QUASI_IDENTIFIER and c.subtype not in EVENT_TIMES
    ]  # fmt: skip


def background(det: DetectionReport, table: str) -> list[str]:
    """Quasi-identifiers an outsider is likely to know: personal facts first, event times only if nothing else."""
    qis = [c.column for c in det.columns if c.table == table and c.privacy_role is R.QUASI_IDENTIFIER]
    return (_personal(det, table) or qis)[:MAX_FACTS]


def person_column(det: DetectionReport, table: str) -> str | None:
    return next((c.column for c in det.columns if c.table == table and c.subtype in PERSON_KEYS), None)


CANDIDATES = 25  # people tried when choosing whom to attack: enough to find a rich trail, quick on big data
MAX_SHOWN = 3  # distinct values shown per column in the trail
MAX_TEXT = 90  # characters of one value: a readable line


def pick_target(
    det: DetectionReport,
    frames: Mapping[str, pd.DataFrame],
    links: Sequence[TableLink] = (),
    rng: np.random.Generator | None = None,
) -> Target | None:
    """Someone an attacker would go after, in the table with the most personal facts about people.

    With a person key, a few people with several records are tried, and the one whose records reach the most
    linked tables is attacked (with rng: one of those, at random). Without a person key: a row nobody resembles.
    """
    tables = sorted((t for t in frames if background(det, t)), key=lambda t: -len(_personal(det, t)))
    for table in tables:
        frame, key = frames[table], person_column(det, table)
        if key is not None:
            ids = frame[key].astype(str).to_numpy()
            counts = pd.Series(ids[ids != ""]).value_counts()
            pool = counts[(counts > 1) & (counts <= 5)]  # a few records, not a test account
            values = list((pool if not pool.empty else counts).index)
            if values:
                picked = values[:CANDIDATES] if rng is None else list(rng.permutation(values)[:CANDIDATES])
                targets = [Target(table, int(np.flatnonzero(ids == v)[0])) for v in picked]
                return _richest(det, frames, links, targets, rng)
        sizes = group_sizes(frame, background(det, table))
        alone = np.flatnonzero((sizes == 1).to_numpy())
        if len(alone):
            return Target(table, int(alone[0] if rng is None else rng.choice(alone[:1000])))
    return None


def _richest(
    det: DetectionReport,
    frames: Mapping[str, pd.DataFrame],
    links: Sequence[TableLink],
    targets: Sequence[Target],
    rng: np.random.Generator | None,
) -> Target:
    """Prefer people the facts single out, then those whose records span the most tables and rows."""

    def score(t: Target) -> tuple[int, int, int]:
        frame = frames[t.table]
        alone = _matches(frame, frame.iloc[t.row], background(det, t.table), person_column(det, t.table)) == 1
        found = reach(det, frames, links, t)
        return int(alone), len(found), sum(found.values())

    scored = [(score(t), t) for t in targets]
    best = max(s[:2] for s, _ in scored)
    top = [t for s, t in scored if s[:2] == best]
    return top[0] if rng is None else top[int(rng.integers(len(top)))]


def _matches(frame: pd.DataFrame, row: pd.Series, columns: Sequence[str], person: str | None) -> int:
    """How many people fit the facts: distinct person codes when there are any, else rows."""
    hit = pd.Series(True, index=frame.index)
    for c in columns:
        hit &= frame[c].astype(str) == str(row[c])
    if person is not None and person in frame.columns:
        return int(frame.loc[hit, person].nunique())
    return int(hit.sum())


def _value(v: object) -> str:
    return "" if pd.isna(v) else str(v)  # type: ignore[call-overload]


def on_raw(
    det: DetectionReport, frames: Mapping[str, pd.DataFrame], target: Target, linked: Mapping[str, int]
) -> AttackResult:
    frame, facts = frames[target.table], background(det, target.table)
    row = frame.iloc[target.row]
    matches = _matches(frame, row, facts, person_column(det, target.table))
    direct = [c.column for c in det.columns if c.table == target.table and c.privacy_role is R.DIRECT_IDENTIFIER]
    revealed = {c: _value(row[c]) for c in direct if _value(row[c])} if matches == 1 else {}
    return AttackResult(
        table=target.table, rows=len(frame), known={c: _value(row[c]) for c in facts}, matches=matches,
        usable=facts, revealed=revealed, linked=dict(linked) if matches == 1 else {},
        outcome="identified" if matches == 1 else "one_in_n",
    )  # fmt: skip


@dataclass(frozen=True)
class ReleasedCopy:
    plan: Plan
    tables: Mapping[str, pd.DataFrame]
    record_ids: Mapping[str, Sequence[str]]  # released row -> original record id (private row map)

    def name_of(self, table: str, column: str, *, matchable: bool = True) -> str | None:
        """The column's name in the release; None when dropped (or, if matchable, coded with a secret key)."""
        a = self.plan.action_for(table, column)
        hidden = (Technique.DROP, Technique.PSEUDONYMISE) if matchable else (Technique.DROP,)
        if a is None or a.technique in hidden:
            return None
        name = str(a.params.get("rename_to", column))
        return name if name in self.tables[table].columns else None


def on_release(
    det: DetectionReport, frames: Mapping[str, pd.DataFrame], target: Target, copy: ReleasedCopy
) -> AttackResult:
    """The same outsider, the same facts, the release instead of the raw data."""
    table, raw = target.table, frames[target.table]
    source = raw.iloc[target.row]
    facts = background(det, table)
    base = AttackResult(table=table, rows=0, known={c: _value(source[c]) for c in facts}, matches=0)
    if table not in copy.tables:
        return replace(base, outcome="withheld")
    out, key = copy.tables[table].reset_index(drop=True), copy.plan.record_keys.get(table)
    ids = list(copy.record_ids.get(table) or [])
    record = _value(source[key]) if key else ""
    if record not in ids:
        return replace(base, rows=len(out), outcome="removed")
    row = out.iloc[ids.index(record)]
    usable = [n for n in (copy.name_of(table, c) for c in facts) if n is not None and _value(row[n])]
    key_col = person_column(det, table)
    matches = _matches(out, row, usable, copy.name_of(table, key_col, matchable=False) if key_col else None)
    direct = [c.column for c in det.columns if c.table == table and c.privacy_role is R.DIRECT_IDENTIFIER]
    hidden = {c: (copy.plan.action_for(table, c) or _DROPPED).technique.value for c in direct}
    revealed = {c: _value(source[c]) for c, t in hidden.items() if t == "keep" and matches == 1}
    links = {t: len(f) for t, f in copy.tables.items() if t != table}  # joinable only after a right guess
    return replace(
        base, rows=len(out), matches=matches, usable=usable, revealed=revealed,
        hidden={c: t for c, t in hidden.items() if c not in revealed},
        linked=links if matches == 1 else {}, outcome="identified" if matches == 1 else "one_in_n",
    )  # fmt: skip


@dataclass(frozen=True)
class Hop:
    """One table on the attacker's trail: how it was reached and what it gives away about the person."""

    table: str
    rows: int
    via: str = ""  # the key followed into this table ("" for the table the outsider searched)
    from_table: str = ""
    learnt: dict[str, str] = field(default_factory=dict)  # column -> the values found (a few, summarised)


def _found(
    det: DetectionReport, frames: Mapping[str, pd.DataFrame], links: Sequence[TableLink], target: Target
) -> list[tuple[Hop, pd.DataFrame]]:
    """The person's rows, then every table reached by following keys from rows already found, in either direction."""
    frame = frames[target.table]
    key = person_column(det, target.table)
    row = frame.iloc[target.row]
    person = frame[frame[key].astype(str) == str(row[key])] if key else frame.iloc[[target.row]]
    found: dict[str, tuple[Hop, pd.DataFrame]] = {target.table: (Hop(target.table, len(person)), person)}
    grew = True
    while grew:  # multi-hop: transactions -> cards -> customers
        grew = False
        for link in links:
            for have, want, have_col, want_col in (
                (link.to_table, link.from_table, link.to_column, link.from_column),
                (link.from_table, link.to_table, link.from_column, link.to_column),
            ):
                if have in found and want not in found:
                    values = set(found[have][1][have_col].astype(str)) - {""}
                    rows = frames[want][frames[want][want_col].astype(str).isin(values)]
                    if len(rows):
                        found[want] = (Hop(want, len(rows), via=want_col, from_table=have), rows)
                        grew = True
    return list(found.values())


def reach(
    det: DetectionReport, frames: Mapping[str, pd.DataFrame], links: Sequence[TableLink], target: Target
) -> dict[str, int]:
    """Rows unlocked once the target row is known: the same person's other rows, then rows linked by keys."""
    return {hop.table: hop.rows for hop, _ in _found(det, frames, links, target)}


# what a trail shows per table, in this order: who it is, what is sensitive about them, what was written
SHOWN_PER_ROLE = ((R.DIRECT_IDENTIFIER, 3), (R.SENSITIVE_ATTRIBUTE, 3), (R.FREE_TEXT, 1))


def trail(
    det: DetectionReport, frames: Mapping[str, pd.DataFrame], links: Sequence[TableLink], target: Target
) -> list[Hop]:
    """What each table on the way gives away: identifiers, sensitive facts and free text, a few values each."""
    facts = set(background(det, target.table))
    hops = []
    for hop, rows in _found(det, frames, links, target):
        own = [c for c in det.columns if c.table == hop.table and c.column not in facts]
        cols = [c for role, limit in SHOWN_PER_ROLE for c in [c for c in own if c.privacy_role is role][:limit]]
        learnt = {}
        for c in cols:
            seen = [v for v in dict.fromkeys(rows[c.column].astype(str)) if v and v != "nan"]
            if seen:
                text = [v if len(v) <= MAX_TEXT else v[: MAX_TEXT - 1] + "…" for v in seen[:MAX_SHOWN]]
                more = f" +{len(seen) - MAX_SHOWN} more" if len(seen) > MAX_SHOWN else ""
                learnt[c.column] = " · ".join(text) + more
        hops.append(replace(hop, learnt=learnt))
    return hops
