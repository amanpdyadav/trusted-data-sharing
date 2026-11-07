"""Names shared by the planners."""

from pets_transformer.contracts import Plan, Subtype

REVIEW = "REVIEW"  # reasons starting with this need a person's decision before approval
# identifiers of a person (as opposed to a visit or a row): codes keep revisits, DP bounds contributions by them
PERSON_KEYS = frozenset({Subtype.NATIONAL_ID, Subtype.PATIENT_ID, Subtype.STUDENT_ID, Subtype.CUSTOMER_ID})


def open_reviews(plan: Plan) -> list[str]:
    """The plan's decisions still marked REVIEW: columns as table.column, statistics by name."""
    columns = [f"{a.table}.{a.column}" for a in plan.actions if a.reason.startswith(REVIEW)]
    return columns + [f"statistic {a.name}" for a in plan.aggregates if a.reason.startswith(REVIEW)]
