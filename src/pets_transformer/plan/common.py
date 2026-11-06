"""Names shared by the planners."""

from pets_transformer.contracts import Subtype

REVIEW = "REVIEW"  # reasons starting with this need a person's decision before approval
# identifiers of a person (as opposed to a visit or a row): codes keep revisits, DP bounds contributions by them
PERSON_KEYS = frozenset({Subtype.NATIONAL_ID, Subtype.PATIENT_ID, Subtype.STUDENT_ID, Subtype.CUSTOMER_ID})
