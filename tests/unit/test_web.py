"""The local web app end to end on a small synthetic dataset: upload, scan, plan, review, approve, run, download."""

import io
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


def test_tradeoff_and_override(client: TestClient, sid: str) -> None:
    _ok(client.post(f"/api/sessions/{sid}/scan"))
    _ok(client.post(f"/api/sessions/{sid}/plan", json={"custom": RECEIVER}))
    points = _ok(client.get(f"/api/sessions/{sid}/tradeoff"))["k"]
    assert [p["k"] for p in points][:3] == [2, 3, 5]
    assert points[0]["guess_chance"] >= points[-1]["guess_chance"]
    col = _ok(client.post(f"/api/sessions/{sid}/detections", json={
        "table": "visits", "column": "triage", "privacy_role": "sensitive_attribute", "subtype": "OTHER", "by": "Ann",
    }))  # fmt: skip
    assert col["evidence"][0]["kind"] == "manual"
    assert client.get(f"/api/sessions/{sid}/plan").status_code == 400  # a changed detection needs a new plan


def test_user_errors_are_explained(client: TestClient) -> None:
    bad = client.post("/api/sessions/upload", files=[("files", ("notes.txt", b"x", "text/plain"))])
    assert bad.status_code == 400
    assert "CSV" in bad.json()["error"]
    assert client.get("/api/sessions/nope").json()["error"].startswith("unknown session")


def test_the_page_and_its_assets_are_served(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/app.js" in page.text
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-cache"  # an updated app is never served stale
    assert client.get("/static/app.css").status_code == 200
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
