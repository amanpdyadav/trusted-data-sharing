import csv
from pathlib import Path

import pytest

from evaluation.attacks import ReplayResult
from evaluation.history import FIELDS, append_history, history_row
from evaluation.scorecard import Run, rowmaps_in, to_metrics
from evaluation.targets import attack_defeated, detection_gates, load_targets, release_gates

RUN = Run("r1", "health", "HEALTH-S1", Path("pkg"), Path("rel"), None, Path("out"))


@pytest.mark.parametrize(
    ("left", "target", "defeated"), [(1, True, False), (5, True, True), (0, False, True), (1, False, True)]
)
def test_attack_defeated(left: int, target: bool, defeated: bool) -> None:
    assert attack_defeated(ReplayResult("c", [], left, target), 5) is defeated


REPORT = {
    "summary": {"privacy": 0.37, "utility": 0.79, "composite": 0.49},
    "risk_components": {"ed_visits: records with k<5": 0.99, "ed_visits: unknown": None},
    "tables": {
        "ed_visits": {
            "k_anonymity": {"min_k": 1, "share_below": {"k<5": 0.99}},
            "linkage": {
                "social_posts_health": {
                    "evaluated": True,
                    "reidentification_rate": 0.02,
                    "baseline_reidentification_rate_original": 0.54,
                },
                "not_run": {"evaluated": False},
                "note": "text, not an attack",
            },
        },
        "lab_results": {"k_anonymity": {"min_k": 3, "share_below": {"k<5": 0.10}}},
        "withheld": {"status": "withheld"},
    },
    "utility": [{"id": "H-U2", "description": "LOS by triage", "score": 1.0}, {"id": "H-U7", "description": "x"}],
}


def test_report_maps_to_valid_metrics() -> None:
    before, after = ReplayResult("POST", [], 1, True), ReplayResult("POST", [], 7, True)
    m = to_metrics(REPORT, RUN, [(before, after)])
    assert (m.privacy, m.utility, m.composite) == (0.37, 0.79, 0.49)
    assert (m.k_min, m.share_below_k) == (1, 0.99)  # worst table wins
    assert [r.name for r in m.risks] == ["ed_visits: records with k<5"]  # None risks dropped
    assert [(a.name, a.before, a.after) for a in m.attacks] == [
        ("ed_visits: social_posts_health", 0.54, 0.02),
        ("demo chain POST", 1, 7),
    ]
    assert [u.score for u in m.utility_tasks] == [1.0, None]


def test_rowmaps_are_found_in_a_private_folder(tmp_path: Path) -> None:
    (tmp_path / "rowmap_ed_visits.csv").write_text("protected_row,original_record_id\n")
    (tmp_path / "ed_visits.csv").write_text("x\n")
    assert rowmaps_in(tmp_path) == {"ed_visits": tmp_path / "rowmap_ed_visits.csv"}
    assert rowmaps_in(None) == {}


def test_targets_load_with_scenario_override(tmp_path: Path) -> None:
    f = tmp_path / "t.yaml"
    f.write_text(
        "default: {composite_min: 0.7, share_below_k_max: 0.05, attack_candidates_min: 5,"
        " detection_macro_f1_min: 0.85, sensitive_attribute_recall_min: 0.7,"
        " text_leakage_max: 0.05, text_recall_min: 0.95}\n"
        "scenarios: {HEALTH-S2: {composite_min: 0.6}}\n"
    )
    assert load_targets("HEALTH-S2", f).composite_min == 0.6
    assert load_targets("HEALTH-S1", f).composite_min == 0.7
    assert load_targets().attack_candidates_min == 5  # the real file parses


def test_release_gates_pass_fail_and_not_measured() -> None:
    t = load_targets()
    m = to_metrics(REPORT, RUN)
    gates = release_gates(m, [ReplayResult("POST", [], 1, True), ReplayResult("NEWS", [], 6, True)], t)
    assert [g.status for g in gates] == ["FAIL", "FAIL", "FAIL", "PASS"]
    empty = to_metrics({}, RUN)
    assert [g.status for g in release_gates(empty, [], t)] == ["N/A", "N/A"]


def test_detection_gates() -> None:
    scores = {"macro_f1": 0.9, "per_role": {"sensitive_attribute": {"recall": 0.5}}}
    assert [g.status for g in detection_gates(scores, load_targets())] == ["PASS", "FAIL"]


def test_history_appends_rows_with_one_header(tmp_path: Path) -> None:
    m = to_metrics(REPORT, RUN, [(ReplayResult("P", [], 1, True), ReplayResult("P", [], 1, True))])
    path = tmp_path / "history.csv"
    row = history_row(m, release_gates(m, [], load_targets()), "abc123")
    append_history(path, row)
    append_history(path, row | {"run_id": "r2"})
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 2
    assert b"\r\n" not in path.read_bytes()  # Unix line endings: clean diffs in git
    assert list(rows[0]) == FIELDS
    assert rows[0]["worst_reidentification"] == "0.02"
    assert rows[0]["fewest_demo_candidates"] == "1"
    assert rows[0]["gates_passed"] == "0"


@pytest.mark.parametrize("missing", ["summary", "tables", "utility", "risk_components"])
def test_partial_reports_do_not_crash(missing: str) -> None:
    report = {k: v for k, v in REPORT.items() if k != missing}
    assert to_metrics(report, RUN).run_id == "r1"


def test_history_refuses_a_repeated_run_id(tmp_path: Path) -> None:
    m = to_metrics(REPORT, RUN)
    path = tmp_path / "history.csv"
    append_history(path, history_row(m, [], "abc123"))
    with pytest.raises(ValueError, match="already in"):
        append_history(path, history_row(m, [], "def456"))
    assert len(list(csv.DictReader(path.open()))) == 1
