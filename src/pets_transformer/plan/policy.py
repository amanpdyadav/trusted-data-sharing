"""Rule-based planner: detections + scenario -> an unapproved draft plan with a reason for every column.

Rules, first match wins:
  free text      requested text is redacted (names, ID codes, contacts, numbers, secrets -> tags); never public
  contact        name, phone, e-mail, address never leave, even when asked for
  tables         a table the data request does not touch is withheld entirely
  keys           row keys and join keys become keyed codes for non-public receivers; other links only if requested
  minimisation   a column the data request does not ask for is dropped (GDPR Art. 5(1)(c))
  identifiers    other requested identifiers only as keyed codes
  quasi          requested quasi-identifiers are generalised and checked together for k, in request order
  diagnosis      requested diagnosis codes are cut to 3 characters
  keep           requested sensitive facts and harmless columns are kept
A requested column flagged only by weak evidence is kept with a REVIEW reason instead of being destroyed.
A person reviews and approves the draft (production rule 5); the planner never approves.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pets_transformer.contracts import (
    ColumnAction,
    ColumnDetection,
    DetectionReport,
    Plan,
    PrivacyRole,
    Subtype,
    Technique,
    TrustLevel,
)
from pets_transformer.plan.scenario import Need, Scenario

R, S, T = PrivacyRole, Subtype, Technique
CONTACT = frozenset({S.PERSON_NAME, S.PHONE, S.EMAIL, S.STREET_ADDRESS})
PERSON_KEYS = frozenset({S.NATIONAL_ID, S.PATIENT_ID, S.STUDENT_ID, S.CUSTOMER_ID})
DEFAULT_TIME_UNIT = {
    TrustLevel.PUBLIC: "month",
    TrustLevel.CONTRACTUAL: "week",
    TrustLevel.CONTROLLED_RESEARCH: "week",
    TrustLevel.INTERNAL: "day",
}
DEFAULT_K = 5
REVIEW = "REVIEW"  # reasons starting with this need a person's decision before approval
WEAK_EVIDENCE = 0.6  # below this detection confidence, an explicit request wins (and is flagged)
CODE = {"length": 16}


@dataclass(frozen=True)
class Decision:
    technique: Technique
    reason: str
    params: dict[str, Any]
    quasi_identifier: bool = False  # a released quasi-identifier joins the k check


@dataclass(frozen=True)
class Context:
    column: ColumnDetection
    need: Need | None
    scenario: Scenario
    detections: DetectionReport
    requested_tables: frozenset[str]  # empty when the scenario has no data request
    join_keys: frozenset[tuple[str, str]]  # (table, column) links that match another released table's row key

    @property
    def public(self) -> bool:
        return self.scenario.trust_level is TrustLevel.PUBLIC

    @property
    def wanted(self) -> bool:
        return self.need is not None or not self.scenario.needs

    @property
    def weak(self) -> bool:
        """Requested, but identified as sensitive only by weak evidence: keep and ask the reviewer."""
        return self.need is not None and self.column.confidence < WEAK_EVIDENCE


def _drop(reason: str) -> Decision:
    return Decision(T.DROP, reason, {})


# ---------------------------------------------------------------- rules
def free_text(x: Context) -> Decision | None:
    if x.column.privacy_role is not R.FREE_TEXT:
        return None
    if not x.wanted:
        return _drop("Free text not in the data request (data minimisation).")
    if x.public:
        return _drop("Public release: free text is withheld; details left after redaction can still identify people.")
    names = [f"{c.table}.{c.column}" for c in x.detections.columns if c.subtype is S.PERSON_NAME]
    why = "Text kept for its meaning; names, ID codes, contacts, account numbers and secrets become tags like [PERSON]."
    return Decision(T.REDACT_TEXT, why, {"known_from": names} if names else {})


def contact(x: Context) -> Decision | None:
    c = x.column
    if c.privacy_role is not R.DIRECT_IDENTIFIER or c.subtype not in CONTACT:
        return None
    asked = " It was requested, but contact details never leave." if x.need else ""
    return _drop(f"{c.subtype.value.replace('_', ' ').lower()} identifies a person on its own.{asked}")


def unrequested_table(x: Context) -> Decision | None:
    if not x.requested_tables or x.column.table in x.requested_tables:
        return None
    return _drop("Table not in the data request: withheld entirely.")


def row_keys(x: Context) -> Decision | None:
    if x.column.privacy_role is not R.RECORD_KEY:
        return None
    if x.public:
        return _drop("Public release: no codes that link records to a person.")
    return Decision(T.PSEUDONYMISE, "Row key as a keyed code: tables stay joinable, original numbers hidden.", CODE)


def links(x: Context) -> Decision | None:
    c = x.column
    is_link = c.privacy_role is R.TECHNICAL_IDENTIFIER or (
        c.privacy_role is R.DIRECT_IDENTIFIER and c.subtype in PERSON_KEYS
    )
    if not is_link:
        return None
    if x.public:
        return _drop("Public release: no codes that link records to a person.")
    if (c.table, c.column) in x.join_keys:
        return Decision(T.PSEUDONYMISE, "Same keyed code as the linked table's row key: the join survives.", CODE)
    if not x.wanted:
        return _drop("Link not in the data request (data minimisation).")
    if x.weak:
        return _review(x)
    return Decision(
        T.PSEUDONYMISE, "Requested link as a keyed code: repeat visits survive; reversal needs the key.", CODE
    )


def _review(x: Context) -> Decision:
    c = x.column
    why = (
        f"{REVIEW}: requested, and detected as {c.privacy_role.value} only with weak evidence "
        f"(confidence {c.confidence:.2f}); kept for the analysis. Confirm or change before approving."
    )
    return Decision(T.KEEP, why, {})


def minimisation(x: Context) -> Decision | None:
    return None if x.wanted else _drop("Not in the data request (data minimisation).")


def identifiers(x: Context) -> Decision | None:
    if x.column.privacy_role is not R.DIRECT_IDENTIFIER:
        return None
    if x.weak:
        return _review(x)
    return Decision(T.PSEUDONYMISE, "Requested identifier released only as a keyed code.", CODE)


def quasi(x: Context) -> Decision | None:
    c = x.column
    if c.privacy_role is not R.QUASI_IDENTIFIER:
        return None
    detail = x.need.detail if x.need else None
    if c.subtype is S.BIRTH_DATE:
        params: dict[str, Any] = {"to": "age_band", "width": 10, "top": 80, "rename_to": "age"}
        ref = _reference_time(x)
        params |= {"reference_column": ref} if ref else {"at": datetime.now(UTC).date().isoformat()}
        return Decision(T.GENERALISE, "Age groups answer the questions; birth dates single people out.", params, True)
    if c.subtype in (S.TIMESTAMP, S.DATE):
        unit = detail or DEFAULT_TIME_UNIT[x.scenario.trust_level]
        why = f"Time released as {unit.replace('_', ' ')}: exact times link to news, posts and receipts."
        return Decision(T.GENERALISE, why, {"to": "time", "unit": unit}, True)
    if c.subtype is S.POSTCODE:
        why = "3-digit postcode areas: small areas identify residents."
        return Decision(T.GENERALISE, why, {"to": "truncate", "length": 3}, True)
    if c.subtype is S.GPS_COORDINATE:
        return _drop("Exact coordinates point to homes; no safe coarsening configured yet.")
    return Decision(T.KEEP, "Requested; checked for k with the other quasi-identifiers.", {}, True)


def diagnosis(x: Context) -> Decision | None:
    if x.column.subtype is not S.DIAGNOSIS_CODE:
        return None
    why = "3-character codes keep diagnosis groups; rare sub-codes single people out."
    return Decision(T.GENERALISE, why, {"to": "truncate", "length": 3})


def keep(x: Context) -> Decision:
    if x.column.privacy_role is R.SENSITIVE_ATTRIBUTE:
        return Decision(T.KEEP, "Requested sensitive fact; kept, its link to a person is broken.", {})
    return Decision(T.KEEP, "Requested and not identifying.", {})


RULES: tuple[Callable[[Context], Decision | None], ...] = (
    free_text, contact, unrequested_table, row_keys, links, minimisation, identifiers, quasi, diagnosis,
)  # fmt: skip


def decide(x: Context) -> Decision:
    for rule in RULES:
        if (d := rule(x)) is not None:
            return d
    return keep(x)


# ---------------------------------------------------------------- planner
class RulePolicy:
    """Implements PolicyEngine."""

    def plan(self, detections: DetectionReport, scenario: Scenario) -> Plan:
        actions: list[ColumnAction] = []
        qis: dict[str, list[tuple[int, str]]] = {}
        record_keys: dict[str, str] = {}
        requested = frozenset(c.table for c in detections.columns if _find_need(scenario, c)[0] is not None)
        joins = _join_keys(detections, requested)
        for c in detections.columns:
            need, rank = _find_need(scenario, c)
            d = decide(Context(c, need, scenario, detections, requested, joins))
            if c.privacy_role is R.RECORD_KEY:
                record_keys[c.table] = c.column
            actions.append(
                ColumnAction(table=c.table, column=c.column, technique=d.technique, params=d.params, reason=d.reason)
            )
            if d.quasi_identifier and d.technique is not T.DROP:
                qis.setdefault(c.table, []).append((rank, str(d.params.get("rename_to", c.column))))
        released = {a.table for a in actions if a.technique is not T.DROP}
        return Plan(
            dataset=detections.dataset,
            scenario_id=scenario.id,
            created_at=datetime.now(UTC),
            k_target=scenario.targets.k or DEFAULT_K,
            quasi_identifiers={t: [name for _, name in sorted(cols)] for t, cols in qis.items()},
            record_keys={t: k for t, k in record_keys.items() if t in released},
            actions=[a for a in actions if a.table in released],
            approved=False,
        )


def _find_need(sc: Scenario, c: ColumnDetection) -> tuple[Need | None, int]:
    for i, n in enumerate(sc.needs):
        if n.column == c.column and n.table in (None, c.table):
            return n, i
    return None, len(sc.needs)


def _join_keys(det: DetectionReport, tables: frozenset[str]) -> frozenset[tuple[str, str]]:
    """Links whose column name is another (requested) table's row key, e.g. lab_results.visit_id."""
    row_keys = {c.table: c.column for c in det.columns if c.privacy_role is R.RECORD_KEY}
    return frozenset(
        (c.table, c.column)
        for c in det.columns
        if c.privacy_role is not R.RECORD_KEY
        and any(col == c.column and t != c.table and (not tables or t in tables) for t, col in row_keys.items())
    )


def _reference_time(x: Context) -> str | None:
    """Age at the event: the first requested timestamp of the same table, else its first timestamp."""
    table = x.column.table
    stamps = [c.column for c in x.detections.columns if c.table == table and c.subtype is S.TIMESTAMP]
    requested = [n.column for n in x.scenario.needs if n.column in stamps and n.table in (None, table)]
    candidates = requested or stamps
    return candidates[0] if candidates else None
