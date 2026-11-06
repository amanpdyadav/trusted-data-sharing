"""Step 2, Plan: choose a proportionate PET per column for a sharing scenario, with a reason.

Every decision cites the scenario's purpose (data minimisation). The user can override any row in the UI.
Scenarios are in metadata/scenarios.json; techniques in docs/PET_PLAYBOOK.md.
"""
from dataclasses import dataclass


@dataclass
class Decision:
    column: str
    technique: str      # drop | keep | hmac_pseudonym | generalise | date_shift | hour_only | round | redact_text | suppress | dp
    params: dict
    reason: str         # plain language, tied to the scenario's purpose


def plan_table(detections, scenario: dict) -> list[Decision]:
    raise NotImplementedError("Plan: scenario-aware PET selection")
