"""Benchmark every receiver: plan automatically, release, score with the organisers' toolkit, write one CSV.

    python -m evaluation receivers                  # all receivers in scenarios/
    python -m evaluation receivers --only FIN-S1 CS-S3

For each receiver: detect its dataset, let the rule-based planner write the plan, approve it for the benchmark only
(the approval names the benchmark, never a person), release it under out/receivers/<ID>/ and score it with pets-eval.
Public dashboards outside health release but are not scored: the toolkit's dashboard scorer is for the hospital data.

results/receivers.csv is committed (like history.csv) and shown on the web app's Release audit page. Scoring runs are
not added to history.csv: this is a benchmark of the automatic planner, not a release.
"""

import csv
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from evaluation import dashboard
from evaluation.runner import RESULTS, git_commit, write_csv
from evaluation.scenarios_from_pack import HAND_WRITTEN
from evaluation.scorecard import Run, run_pets_eval, to_metrics
from pets_transformer.contracts import Plan
from pets_transformer.detect.source import detect_source
from pets_transformer.keys import KeyScope
from pets_transformer.pipeline import OutputLayout, run_release
from pets_transformer.plan.policy import RulePolicy
from pets_transformer.plan.scenario import Scenario
from pets_transformer.plan.statistics import load_codelists
from pets_transformer.sources import open_source

CSV = RESULTS / "receivers.csv"
READY = 0.70  # combined score from which a receiver's automatic plan counts as ready
BENCHMARK = "benchmark (automatic plan, not for sharing)"

# Why a receiver's automatic plan loses usefulness, read from its scorecard (docs/RECEIVERS.md). Kept here so the CSV
# and the app say the same thing; update both when a plan is tuned.
WHY = {
    "CITY-S2": "Time too coarse for parking occupancy and dwell time; hourly time drops privacy to about 0.4.",
    "CITY-S3": "Time too coarse for parking occupancy and dwell time; needs a different protection (shift dates).",
    "MOB-S2": "Time too coarse for journey chains; hourly time drops privacy to about 0.4.",
    "CYBER-S1": "Indicators and exact times the analyses need are pseudonymised or coarsened.",
    "CYBER-S2": "Threat-intelligence sharing needs attacker IPs and domains verbatim; the planner hides them.",
    "CS-S1": "The analyses read the conversation text, which needs the text redactor in the plan.",
    "CS-S2": "The analyses read the conversation text, which needs the text redactor in the plan.",
    "PUB-S2": "The analyses read request texts, which need the text redactor in the plan.",
    "PUB-S3": "The analyses read request texts, which need the text redactor in the plan.",
    "FIN-S1": "Models trained on the release lose signal from generalised amounts and times.",
    "FIN-S2": "Models trained on the release lose signal from generalised amounts and times.",
    "EDU-S2": "Models trained on the release lose signal from generalised values.",
}

# Said of a receiver whatever its status (the benchmark scores the automatic plan; some need more than that).
NOTE = {
    "HEALTH-S1": "The automatic plan fails the post and news sweep (7 of 1,050 public scraps); the tuned "
    "plans/health-s1.yaml passes all 5 gates.",
}

FIELDS = [
    "id", "dataset", "recipient", "trust_level", "gets", "source", "privacy", "utility", "composite",
    "released_tables", "epsilon", "status", "why", "measured_at", "commit",
]  # fmt: skip


@dataclass
class ReceiverResult:
    id: str
    dataset: str
    recipient: str
    trust_level: str
    gets: str  # rows | statistics
    source: str  # hand-written | generated
    privacy: float | None
    utility: float | None
    composite: float | None
    released_tables: int
    epsilon: float | None
    status: str  # ready | needs tuning | unscored | failed
    why: str
    measured_at: str
    commit: str


def status_of(composite: float | None, scored: bool) -> str:
    if not scored:
        return "unscored"
    return "ready" if composite is not None and composite >= READY else "needs tuning"


def benchmark(
    scenario: Scenario,
    package_root: Path,
    scope: Callable[[Plan], KeyScope],
    out_root: Path = Path("out") / "receivers",
    results: Path = RESULTS,
) -> ReceiverResult:
    """Plan, release and score one receiver with the automatic planner."""
    gets = "statistics" if scenario.statistics and not scenario.needs else "rows"
    base = {
        "id": scenario.id, "dataset": scenario.dataset, "recipient": scenario.recipient,
        "trust_level": scenario.trust_level.value, "gets": gets,
        "source": "hand-written" if scenario.id in HAND_WRITTEN else "generated",
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"), "commit": git_commit(),
    }  # fmt: skip
    try:
        source = open_source(f"csv:{package_root / 'data' / scenario.dataset}")
        plan = RulePolicy(load_codelists(Path("codelists"))).plan(detect_source(source, scenario.dataset), scenario)
        plan = plan.model_copy(update={"approved": True, "approved_by": BENCHMARK})
        layout = OutputLayout(out_root / scenario.id)
        outcome = run_release(source, plan, scope(plan), layout)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        return ReceiverResult(**base, privacy=None, utility=None, composite=None, released_tables=0, epsilon=None,
                              status="failed", why=f"did not release: {exc}"[:300])  # fmt: skip
    released = len(outcome.manifest.files)
    eps = plan.epsilon_spent if plan.aggregates else None
    release: Path = layout.release
    rowmaps: Path | None = layout.private
    run_dir = results / "runs" / f"receivers-{scenario.id}"
    if dashboard.is_dashboard(layout.release):
        if scenario.dataset != "health":
            why = "Published statistics release; the toolkit scores dashboards for health only."
            return ReceiverResult(**base, privacy=None, utility=None, composite=None, released_tables=released,
                                  epsilon=eps, status="unscored", why=why)  # fmt: skip
        release, rowmaps = dashboard.scoring_view(layout.release, package_root, run_dir / "scoring"), None
    run = Run(f"receivers-{scenario.id}", scenario.dataset, scenario.id, package_root, release, rowmaps, run_dir)
    try:
        m = to_metrics(run_pets_eval(run), run)
    except (subprocess.CalledProcessError, ValueError, KeyError, FileNotFoundError) as exc:
        return ReceiverResult(**base, privacy=None, utility=None, composite=None, released_tables=released,
                              epsilon=eps, status="failed", why=f"scoring failed: {exc}"[:300])  # fmt: skip
    status = status_of(m.composite, scored=True)
    why = NOTE.get(scenario.id) or (WHY.get(scenario.id, "") if status == "needs tuning" else "")
    return ReceiverResult(**base, privacy=m.privacy, utility=m.utility, composite=m.composite,
                          released_tables=released, epsilon=eps, status=status, why=why)  # fmt: skip


def read(path: Path = CSV) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write(rows: Iterable[ReceiverResult], path: Path = CSV) -> Path:
    """Replace the rows of the receivers measured now; keep the others (a partial run updates only its rows)."""
    new = {r.id: {k: ("" if v is None else v) for k, v in asdict(r).items()} for r in rows}
    kept = [r for r in read(path) if r["id"] not in new]
    merged = sorted([*kept, *new.values()], key=lambda r: (str(r["dataset"]), str(r["id"])))
    return write_csv(path, FIELDS, merged)
