"""The local web app end to end on a small synthetic dataset: upload, scan, plan, review, approve, run, download."""

import io
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pets_transformer.config import Settings
from pets_transformer.web.app import create_app
from tests.conftest import REPO, TEST_MASTER_KEY

N = 30


def _visits_csv() -> bytes:
    rows = ["visit_id,hetu,patient_name,date_of_birth,sex,municipality,arrival_ts,icd10_primary,triage"]
    for i in range(N):
        rows.append(
            f"V{i:03d},{(i % 20) + 10:02d}0190-9{i:02d}A,Person {i},19{50 + i % 30}-01-0{1 + i % 9},"
            f"{'FM'[i % 2]},{'Turku' if i % 3 else 'Salo'},2025-0{1 + i % 9}-1{i % 9} 1{i % 10}:2{i % 6}:00,"
            f"J10.1,{'ABC'[i % 3]}"
        )
    return ("\n".join(rows) + "\n").encode()


def _labs_csv() -> bytes:
    rows = ["lab_id,visit_id,test_code,value"] + [f"L{i:03d},V{i:03d},CRP,{i * 3}" for i in range(N)]
    return ("\n".join(rows) + "\n").encode()


RECEIVER = {
    "id": "TEST-S1", "title": "Research", "recipient": "University", "purpose": "Flu study",
    "trust_level": "controlled_research", "threat_model": "linkage",
    "needs": [{"table": "visits", "column": "hetu"}, {"table": "visits", "column": "date_of_birth"},
              {"table": "visits", "column": "municipality"}, {"table": "visits", "column": "icd10_primary"}],
    "targets": {"k": 3},
}  # fmt: skip


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("PETS_MASTER_KEY", TEST_MASTER_KEY.decode())
    return Settings(
        package_root=tmp_path / "pkg", out_dir=tmp_path / "out", scenario_dirs=(REPO / "scenarios",),
        codelist_dir=REPO / "codelists",
    )  # fmt: skip


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _ok(r: object) -> dict:  # type: ignore[type-arg]
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    return r.json()  # type: ignore[attr-defined, no-any-return]


@pytest.fixture
def sid(client: TestClient) -> str:
    files = [("files", ("visits.csv", _visits_csv(), "text/csv")), ("files", ("labs.csv", _labs_csv(), "text/csv"))]
    data = _ok(client.post("/api/sessions/upload", files=files, data={"name": "clinic"}))
    assert sorted(t["name"] for t in data["tables"]) == ["labs", "visits"]
    return str(data["id"])


def test_the_attack_shows_a_trail_and_can_pick_another_person(client: TestClient, sid: str) -> None:
    scan = _ok(client.post(f"/api/sessions/{sid}/scan"))
    trail = scan["attack"]["trail"]
    assert [(h["table"], h["via"]) for h in trail] == [("visits", ""), ("labs", "visit_id")]
    assert "patient_name" in trail[0]["learnt"]
    another = f"/api/sessions/{sid}/attack/another"
    people = {_ok(client.post(another, json={"seed": n}))["before"]["known"]["date_of_birth"] for n in range(8)}
    assert len(people) > 1  # a different person on different tries


def test_scan_shows_identifiers_links_and_one_person(client: TestClient, sid: str) -> None:
    scan = _ok(client.post(f"/api/sessions/{sid}/scan"))
    roles = {(c["table"], c["column"]): c["privacy_role"] for c in scan["detections"]["columns"]}
    assert roles[("visits", "patient_name")] == "direct_identifier"
    assert [(link["from_table"], link["to_table"]) for link in scan["risk"]["links"]] == [("labs", "visits")]
    assert set(scan["risk"]["person"]) == {"visits", "labs"}


def test_full_release_flow_and_downloads(client: TestClient, sid: str) -> None:
    _ok(client.post(f"/api/sessions/{sid}/scan"))
    plan = _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    techniques = {a["column"]: a["technique"] for a in plan["plan"]["actions"]}
    assert techniques["patient_name"] == "drop"
    assert techniques["hetu"] == "pseudonymise"
    assert plan["withheld_tables"] == ["labs"]

    refused = client.post(f"/api/sessions/{sid}/run", json={"receiver": "uni"})
    assert refused.status_code == 400
    assert "approve" in refused.json()["error"]

    edited = _ok(client.post(f"/api/sessions/{sid}/plan/action",
                             json={"table": "visits", "column": "municipality", "technique": "drop"}))  # fmt: skip
    assert "municipality" not in edited["plan"]["quasi_identifiers"].get("visits", [])
    _ok(client.post(f"/api/sessions/{sid}/approve", json={"by": "Test Steward", "confirm_review": True}))
    results = _ok(client.post(f"/api/sessions/{sid}/run", json={"receiver": "uni"}))
    assert results["attacker"][0]["after"]["unique_share"] == 0.0
    assert [f["name"] for f in results["files"]] == ["visits.csv"]

    z = client.get(f"/api/sessions/{sid}/download/release.zip")
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert sorted(n.split("/")[1] for n in names) == ["manifest.json", "visits.csv"]
    assert not any("rowmap" in n for n in names)
    assert "approved_by: Test Steward" in client.get(f"/api/sessions/{sid}/download/plan.yaml").text


def test_plan_example_shows_records_before_and_after(client: TestClient, sid: str) -> None:
    _ok(client.post(f"/api/sessions/{sid}/scan"))
    _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    (visits,) = _ok(client.get(f"/api/sessions/{sid}/plan/example"))["tables"]
    first = visits["rows"][0]
    assert visits["renamed"]["date_of_birth"] in first["after"]  # made less exact, under its released name
    assert "patient_name" not in first["after"]  # removed
    assert first["after"]["hetu"] != first["raw"]["hetu"]  # replaced by a code


def test_tradeoff_and_override(settings: Settings, client: TestClient, sid: str) -> None:
    first = _ok(client.post(f"/api/sessions/{sid}/scan"))
    kept = settings.out_dir / "web" / sid / "scan.json"
    assert kept.exists()  # reopening a large dataset does not scan it again
    assert _ok(client.post(f"/api/sessions/{sid}/scan"))["risk"] == first["risk"]
    _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    points = _ok(client.get(f"/api/sessions/{sid}/tradeoff"))["k"]
    assert [p["k"] for p in points][:3] == [2, 3, 5]
    assert points[0]["guess_chance"] >= points[-1]["guess_chance"]
    col = _ok(client.post(f"/api/sessions/{sid}/detections", json={
        "table": "visits", "column": "triage", "privacy_role": "sensitive_attribute", "subtype": "OTHER", "by": "Ann",
    }))  # fmt: skip
    assert col["evidence"][0]["kind"] == "manual"
    assert not kept.exists()  # a corrected detection needs a fresh scan
    assert client.get(f"/api/sessions/{sid}/plan").status_code == 400  # a changed detection needs a new plan


def test_user_errors_are_explained(client: TestClient) -> None:
    bad = client.post("/api/sessions/upload", files=[("files", ("notes.txt", b"x", "text/plain"))])
    assert bad.status_code == 400
    assert "CSV" in bad.json()["error"]
    assert client.get("/api/sessions/nope").json()["error"].startswith("unknown session")


def test_the_page_and_its_assets_are_served(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assets = re.findall(r'(?:src|href)="(/static/assets/[^"]+)"', page.text)  # the built React app (frontend/)
    assert any(a.endswith(".js") for a in assets)
    assert any(a.endswith(".css") for a in assets)
    for asset in assets:
        served = client.get(asset)
        assert served.status_code == 200
        assert served.headers["cache-control"] == "no-cache"  # an updated app is never served stale
    catalogue = client.get("/api/catalogue").json()
    assert "direct_identifier" in catalogue["roles"]
    assert "diagnosis_group" in catalogue["codelists"]


def _release(client: TestClient, sid: str, k: int) -> dict:  # type: ignore[type-arg]
    _ok(client.post(f"/api/sessions/{sid}/plan/k", json={"k": k}))
    _ok(client.post(f"/api/sessions/{sid}/approve", json={"by": "Test Steward", "confirm_review": True}))
    return _ok(client.post(f"/api/sessions/{sid}/run", json={"receiver": f"uni-k{k}"}))


def test_every_release_is_kept_compared_and_survives_a_restart(
    settings: Settings, client: TestClient, sid: str
) -> None:
    scan = _ok(client.post(f"/api/sessions/{sid}/scan"))
    assert scan["attack"]["before"]["table"] == "visits"
    _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    first, second = _release(client, sid, 2), _release(client, sid, 5)
    assert (first["summary"]["k"], second["summary"]["k"]) == (2, 5)
    assert first["release_id"] != second["release_id"]
    assert first["techniques"]["visits.patient_name"] == "drop"
    pair = first["tables"][0]["pairs"][0]  # a released row next to the raw record it came from
    assert pair["raw"]["patient_name"].startswith("Person")
    assert "patient_name" not in pair["released"]
    assert first["attack"]["after"]["outcome"] in {"one_in_n", "identified", "removed"}

    restarted = TestClient(create_app(settings))  # a new app process reads the same folder
    (listed,) = _ok(restarted.get("/api/sessions"))
    assert (listed["id"], listed["name"], listed["releases"]) == (sid, "clinic", 2)
    history = _ok(restarted.get(f"/api/sessions/{sid}/releases"))
    assert [r["k"] for r in history] == [5, 2]  # newest first
    kept = _ok(restarted.get(f"/api/sessions/{sid}/releases/{first['release_id']}"))
    assert kept["summary"] == first["summary"]
    z = restarted.get(f"/api/sessions/{sid}/releases/{first['release_id']}/release.zip")
    assert not any("rowmap" in n for n in zipfile.ZipFile(io.BytesIO(z.content)).namelist())
    assert restarted.get(f"/api/sessions/{sid}/releases/..%2Fplan").status_code in {400, 404}  # no path tricks
    assert restarted.get(f"/api/sessions/{sid}/releases/nope").status_code == 400


def test_tables_can_be_added_and_removed_until_the_dataset_is_released(client: TestClient, sid: str) -> None:
    _ok(client.post(f"/api/sessions/{sid}/scan"))
    extra = [("files", ("notes.csv", b"note_id,visit_id,text\nN1,V001,hello\n", "text/csv"))]
    added = _ok(client.post(f"/api/sessions/{sid}/tables", files=extra))
    assert sorted(t["name"] for t in added["tables"]) == ["labs", "notes", "visits"]
    assert not added["steps"]["scanned"]  # new data needs a new scan
    removed = _ok(client.delete(f"/api/sessions/{sid}/tables/notes"))
    assert sorted(t["name"] for t in removed["tables"]) == ["labs", "visits"]
    assert client.delete(f"/api/sessions/{sid}/tables/..%2Fvisits").status_code >= 400  # no path tricks
    assert client.delete(f"/api/sessions/{sid}/tables/missing").status_code == 400
    assert "visits" in [t["name"] for t in _ok(client.get(f"/api/sessions/{sid}"))["tables"]]

    _ok(client.post(f"/api/sessions/{sid}/scan"))
    _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    _ok(client.post(f"/api/sessions/{sid}/approve", json={"by": "Test Steward", "confirm_review": True}))
    _ok(client.post(f"/api/sessions/{sid}/run", json={"receiver": "uni"}))
    frozen = client.post(f"/api/sessions/{sid}/tables", files=extra)
    assert frozen.status_code == 400
    assert "duplicate" in frozen.json()["error"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 400  # a released dataset stays as the record

    copy = _ok(client.post(f"/api/sessions/{sid}/duplicate", json={"name": "clinic v2"}))
    assert copy["name"] == "clinic_v2"
    assert not copy["released"]
    assert sorted(t["name"] for t in copy["tables"]) == ["labs", "visits"]
    assert _ok(client.post(f"/api/sessions/{copy['id']}/scan"))["detections"]  # corrections came along; scan works
    _ok(client.post(f"/api/sessions/{copy['id']}/rename", json={"name": "clinic final"}))
    assert _ok(client.delete(f"/api/sessions/{copy['id']}")) == {"deleted": copy["id"]}
    assert [x["id"] for x in _ok(client.get("/api/sessions"))] == [sid]


def test_plan_versions_can_be_compared_restored_and_released(client: TestClient, sid: str) -> None:
    _ok(client.post(f"/api/sessions/{sid}/scan"))
    _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    _ok(client.post(f"/api/sessions/{sid}/approve", json={"by": "Test Steward", "confirm_review": True}))
    _ok(
        client.post(
            f"/api/sessions/{sid}/plan/action", json={"table": "visits", "column": "municipality", "technique": "drop"}
        )
    )
    versions = _ok(client.get(f"/api/sessions/{sid}/plan/versions"))
    assert [v["note"] for v in versions["versions"]] == [
        "New plan for University",
        "Approved by Test Steward",
        "visits.municipality: shared as is → removed",
    ]
    assert versions["current"] == 3
    diff = _ok(client.get(f"/api/sessions/{sid}/plan/compare", params={"a": 2, "b": 3}))
    assert {"what": "visits.municipality", "before": "shared as is", "after": "removed"} in diff["changes"]
    assert "municipality" in diff["yaml_a"]
    assert (
        "approved_by: Test Steward" in _ok(client.get(f"/api/sessions/{sid}/plan/yaml", params={"version": 2}))["yaml"]
    )

    restored = _ok(client.post(f"/api/sessions/{sid}/plan/versions/2/restore"))
    assert restored["plan"]["approved"]  # the approved version stays approved: release straight away
    release = _ok(client.post(f"/api/sessions/{sid}/run", json={"receiver": "uni"}))
    assert release["summary"]["plan_version"] == 4
    listed = _ok(client.get(f"/api/sessions/{sid}/plan/versions"))["versions"]
    assert listed[-1]["note"] == "Back to version 2"
    assert listed[-1]["released_as"] == release["release_id"]
