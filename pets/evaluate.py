"""Step 4, Measure: wrap the pets-eval scorecard so the app and scripts get one consistent result."""
from pathlib import Path

from pets_eval.scorecard import run_scorecard

from . import DATA, PG_ROOT


def scorecard(dataset: str, protected_dir: Path, scenario: str) -> dict:
    """Run the official self-assessment scorecard. Returns summary, utility tasks and risk components,
    and writes scorecard.json and scorecard.html into protected_dir."""
    return run_scorecard(DATA / dataset, Path(protected_dir), scenario=scenario, root=PG_ROOT)
