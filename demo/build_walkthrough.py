"""Build demo/walkthrough.html: the product walkthrough with every number taken from our own outputs.

Sources (re-create them with the Makefile targets before building):
    demo/mosaic_trace.json                      the attack chains        (python demo/mosaic_attack.py)
    out/health/detection.json                   column detection         (pets-transformer detect)
    plans/health-s1.auto.yaml, plans/health-s2.yaml   approved plans
    out/health-auto/run/release/manifest.json, out/health-s2/release/manifest.json   releases
    results/runs/<run>/metrics.json, results/history.csv                             scored runs
    results/text_redaction.csv                  text scores              (make text-score)

    python demo/build_walkthrough.py

The data is synthetic (TrustED Proving Ground). The page never contains row maps or keys.
"""

import csv
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from evaluation import detection as detection_scores  # noqa: E402
from evaluation.cli import DEV_DATASETS, HELD_OUT  # noqa: E402
from pets_transformer.detect.rules import detect_source  # noqa: E402
from pets_transformer.sources import open_source  # noqa: E402
from pets_transformer.text.redactor import build_redactor  # noqa: E402

PKG = ROOT / "TRUSTED_PETS_PROVING_GROUND_2026"
TEMPLATE = ROOT / "demo" / "walkthrough.template.html"
OUT = ROOT / "demo" / "walkthrough.html"
SHOWN_PARAMS = ("to", "unit", "width", "length", "rename_to")
RUNS = {"before": "quickstart-baseline", "s1": "health-s1-auto", "s2": "health-s2-v1"}
TEXT_SAMPLES = [  # (dataset, table, id column, text column, record id): one per kind of identifier
    ("customer_service", "turns", "turn_id", "text", "T0000004"),  # Swedish speech: ID code read aloud
    ("customer_service", "turns", "turn_id", "text", "T0000273"),  # Finnish speech: e-mail spelled out
    ("customer_service", "turns", "turn_id", "text", "T0000061"),  # property ID and lowercase address
    ("customer_service", "turns", "turn_id", "text", "T0064432"),  # chat: card number, name, customer number
    ("customer_service", "turns", "turn_id", "text", "T0002310"),  # e-mail signature: IBAN, name, phone
    ("education", "counsellor_notes", "note_id", "note_text", "CN00001"),  # held-out column: student name
    ("public_admin", "service_requests", "request_id", "description", "SR-2024-000001"),  # held-out: neighbour
]


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def attack() -> dict[str, Any]:
    trace = _json(ROOT / "demo" / "mosaic_trace.json")
    cases = []
    for p in trace["people"]:
        steps = [
            {k: s.get(k) for k in ("dataset", "title", "kind", "rows_total", "funnel", "known", "revealed", "how")}
            for s in p["steps"]
        ]
        cases.append({"source": p["source_id"], "steps": steps, "names_removed": p["after"]})
    return {"cases": cases}


def detection() -> dict[str, Any]:
    report = _json(ROOT / "out" / "health" / "detection.json")
    cols = [
        {
            "table": c["table"], "column": c["column"], "role": c["privacy_role"], "subtype": c["subtype"],
            "confidence": c["confidence"], "evidence": [e["detail"] for e in c["evidence"]][:2],
        }
        for c in report["columns"]
        if c["table"] in ("ed_visits", "lab_results")
    ]  # fmt: skip
    scores = {}
    for split, datasets in (("dev", DEV_DATASETS), ("held_out", HELD_OUT)):
        overall, _ = detection_scores.score_datasets(PKG, datasets)
        scores[split] = {"macro_f1": round(overall["macro_f1"], 3), "datasets": datasets}
    return {"columns": cols, "dataset": report["dataset"], "scores": scores}


def plans() -> dict[str, Any]:
    s1 = _yaml(ROOT / "plans" / "health-s1.auto.yaml")
    s2 = _yaml(ROOT / "plans" / "health-s2.yaml")
    actions = [
        {"table": a["table"], "column": a["column"], "technique": a["technique"], "reason": a["reason"],
         "params": {k: v for k, v in a.get("params", {}).items() if k in SHOWN_PARAMS}}
        for a in s1["actions"]
    ]  # fmt: skip
    aggregates = [
        {"name": a["name"], "by": [d.get("name") or d["column"] for d in a["dimensions"]],
         "from": [d["column"] for d in a["dimensions"]], "measure": a["measure"], "epsilon": a["epsilon"],
         "reason": a["reason"]}
        for a in s2["aggregates"]
    ]  # fmt: skip
    return {
        "s1": {"actions": actions, "k": s1["k_target"], "quasi": s1["quasi_identifiers"], "by": s1["approved_by"]},
        "s2": {"aggregates": aggregates, "epsilon": s2["epsilon"], "dp": s2["differential_privacy"],
               "by": s2["approved_by"]},
        "scenarios": {k: _yaml(ROOT / "scenarios" / f"HEALTH-{k.upper()}.yaml") for k in ("s1", "s2")},
    }  # fmt: skip


def _names(dataset: str) -> list[str]:
    source = open_source(f"csv:{PKG / 'data' / dataset}")
    report = detect_source(source, dataset)
    return [v for c in report.columns if c.subtype.value == "PERSON_NAME" for v in source.read(c.table)[c.column] if v]


def text() -> dict[str, Any]:
    samples, redactors = [], {}
    for dataset, table, id_col, text_col, rid in TEXT_SAMPLES:
        if dataset not in redactors:
            redactors[dataset] = build_redactor(_names(dataset))
        frame = pd.read_csv(PKG / "data" / dataset / f"{table}.csv", dtype=str, keep_default_na=False)
        value = frame.loc[frame[id_col] == rid, text_col].iloc[0]
        parts, cursor = [], 0
        for s in redactors[dataset].spans(value):
            parts += [{"t": value[cursor : s.start]}, {"t": value[s.start : s.end], "label": s.label.value}]
            cursor = s.end
        parts.append({"t": value[cursor:]})
        samples.append({"where": f"{dataset}.{table}", "id": rid, "parts": [p for p in parts if p["t"]]})
    with (ROOT / "results" / "text_redaction.csv").open(encoding="utf-8") as f:
        scores = list(csv.DictReader(f))
    return {"samples": samples, "scores": scores}


def prove() -> dict[str, Any]:
    runs = {k: _json(ROOT / "results" / "runs" / r / "metrics.json") for k, r in RUNS.items()}
    stats = pd.read_csv(PKG / "data" / "health" / "published_weekly_stats.csv")
    bad = {"cells": len(stats), "single": int((stats["visits"] == 1).sum()), "below5": int((stats["visits"] < 5).sum())}
    with (ROOT / "results" / "history.csv").open(encoding="utf-8") as f:
        history = [r for r in csv.DictReader(f) if r["run_id"] in RUNS.values()]
    return {"runs": runs, "published_stats": bad, "history": history}


def report() -> dict[str, Any]:
    out = {}
    for key, path in (("s1", "out/health-auto/run/release"), ("s2", "out/health-s2/release")):
        m = _json(ROOT / path / "manifest.json")
        out[key] = {
            "release_id": m["release_id"], "key_domain": m["key_domain"], "files": m["files"],
            "residual_risks": m["residual_risks"], "limitations": m["limitations"],
            "input_fingerprint": m["input_fingerprint"], "tool_version": m["tool_version"],
        }  # fmt: skip
    return out


def main() -> None:
    data = {
        "attack": attack(), "detect": detection(), "plan": plans(), "text": text(), "prove": prove(),
        "report": report(),
    }  # fmt: skip
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/{}", payload)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
