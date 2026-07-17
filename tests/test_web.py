import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from tfrefactor.web.app import FIXTURE_ROOT, app

client = TestClient(app)


def test_index_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "tfrefactor" in r.text


def test_presets_lists_fixture():
    r = client.get("/api/presets")
    assert r.status_code == 200
    paths = [p["path"] for p in r.json()["presets"]]
    assert str(FIXTURE_ROOT) in paths


def test_resources_endpoint(messy_root):
    r = client.get(f"/api/resources?directory={messy_root}")
    assert r.status_code == 200
    data = r.json()
    assert any(res["address"] == "aws_instance.web" for res in data["resources"])


def test_scan_endpoint(messy_root):
    r = client.post("/api/scan", json={"directory": str(messy_root), "god_file_threshold": 500})
    assert r.status_code == 200
    data = r.json()
    assert data["resource_count"] > 0
    assert any(f["category"] == "god-file" for f in data["findings"])


def test_propose_rename_endpoint_never_writes_to_original(messy_root):
    original = (messy_root / "main.tf").read_text()
    r = client.post(
        "/api/propose",
        json={"directory": str(messy_root), "op": "rename", "address": "aws_instance.web", "new_name": "web_server"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["verdict"] == "VERIFIED_WITH_CAVEATS"
    assert "main.tf" in data["file_writes"]
    # the dashboard must never touch the real files on disk
    assert (messy_root / "main.tf").read_text() == original


def test_propose_invalid_address_returns_400(messy_root):
    r = client.post(
        "/api/propose",
        json={"directory": str(messy_root), "op": "rename", "address": "aws_instance.does_not_exist", "new_name": "x"},
    )
    assert r.status_code == 400


def test_propose_dead_code_is_human_review(messy_root):
    r = client.post(
        "/api/propose",
        json={"directory": str(messy_root), "op": "dead-code", "address": "aws_iam_role.orphan_role"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["human_review"] is True
    assert data["result"]["verdict"] == "HUMAN_REVIEW_REQUIRED"


def test_unify_endpoint(messy_root):
    r = client.post(
        "/api/unify",
        json={"common_root": str(messy_root), "env_dirs": ["envs/dev", "envs/prod"]},
    )
    assert r.status_code == 200
    data = r.json()
    names = {(g["resource_type"], g["resource_name"]) for g in data["groups"]}
    assert ("aws_s3_bucket", "logs") in names
    for g in data["groups"]:
        assert g["combined_verdict"] == "HUMAN_REVIEW_REQUIRED"
