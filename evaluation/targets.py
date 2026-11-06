"""Pass marks as config, and the checks that compare a run against them."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from evaluation.attacks import ReplayResult
from pets_transformer.contracts import Metrics

DEFAULT_FILE = Path(__file__).with_name("targets.yaml")


class Targets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    composite_min: float = Field(ge=0, le=1)
    share_below_k_max: float = Field(ge=0, le=1)
    attack_candidates_min: int = Field(ge=1)
    detection_macro_f1_min: float = Field(ge=0, le=1)
    sensitive_attribute_recall_min: float = Field(ge=0, le=1)


def load_targets(scenario_id: str | None = None, path: Path = DEFAULT_FILE) -> Targets:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    merged = dict(data["default"])
    if scenario_id:
        merged |= (data.get("scenarios") or {}).get(scenario_id) or {}
    return Targets.model_validate(merged)


@dataclass(frozen=True)
class Gate:
    name: str
    value: str
    target: str
    passed: bool | None  # None = could not be measured in this run

    @property
    def status(self) -> str:
        return {True: "PASS", False: "FAIL", None: "N/A"}[self.passed]


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def attack_defeated(r: ReplayResult, minimum: int) -> bool:
    """An attack is defeated if it ends with no candidates, misses the target, or leaves `minimum`+ candidates."""
    return r.candidates_left == 0 or r.target_among_candidates is False or r.candidates_left >= minimum


def release_gates(metrics: Metrics, replays: Sequence[ReplayResult], t: Targets) -> list[Gate]:
    gates = [
        Gate(
            "combined score",
            _fmt(metrics.composite),
            f">= {t.composite_min}",
            None if metrics.composite is None else metrics.composite >= t.composite_min,
        ),
        Gate(
            "rows in groups smaller than 5",
            _fmt(metrics.share_below_k),
            f"<= {t.share_below_k_max}",
            None if metrics.share_below_k is None else metrics.share_below_k <= t.share_below_k_max,
        ),
    ]
    gates += [
        Gate(
            f"demo attack {r.case_id}",
            f"{r.candidates_left} candidates, target {'in' if r.target_among_candidates else 'out'}",
            f">= {t.attack_candidates_min} candidates",
            attack_defeated(r, t.attack_candidates_min),
        )
        for r in replays
    ]
    return gates


def detection_gates(scores: Mapping[str, Any], t: Targets) -> list[Gate]:
    sens = (scores.get("per_role") or {}).get("sensitive_attribute", {}).get("recall")
    f1 = scores.get("macro_f1")
    return [
        Gate(
            "column detection macro-F1",
            _fmt(f1),
            f">= {t.detection_macro_f1_min}",
            None if f1 is None else f1 >= t.detection_macro_f1_min,
        ),
        Gate(
            "sensitive-attribute recall",
            _fmt(sens),
            f">= {t.sensitive_attribute_recall_min}",
            None if sens is None else sens >= t.sensitive_attribute_recall_min,
        ),
    ]
