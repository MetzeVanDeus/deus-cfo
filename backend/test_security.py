import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def local_headers(origin="http://127.0.0.1:3000"):
    headers = {"host": "127.0.0.1:8000"}
    if origin is not None:
        headers["origin"] = origin
    return headers


def test_unrelated_origin_cannot_read_api(client):
    response = client.get("/api/categories", headers=local_headers("https://evil.example"))
    assert response.status_code == 403


def test_allowed_local_origin_can_read_api(client):
    response = client.get("/api/categories", headers=local_headers())
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_unrelated_host_is_rejected_even_without_origin(client):
    response = client.get("/api/categories", headers={"host": "evil.example"})
    assert response.status_code == 403


def test_no_origin_loopback_client_can_read_api(client):
    response = client.get("/api/categories", headers=local_headers(None))
    assert response.status_code == 200


def test_session_is_available_to_approved_local_client(client):
    response = client.get("/api/session", headers=local_headers("http://localhost:3000"))
    assert response.status_code == 200
    assert len(response.json()["token"]) >= 32


def test_mutation_and_collection_require_session_token(client):
    headers = local_headers()
    assert client.post("/api/cx/poll", headers=headers).status_code == 403
    assert client.post("/api/cx/backfill", json={"max_hours": 1}, headers=headers).status_code == 403
    assert client.post("/api/snapshot", json={"league": "Allflame"}, headers=headers).status_code == 403


def test_valid_session_allows_protected_collection(monkeypatch, client):
    async def poll():
        return 0

    monkeypatch.setattr(main.cx_collector, "poll_latest_cx", poll)
    session = client.get("/api/session", headers=local_headers()).json()["token"]
    response = client.post(
        "/api/cx/poll",
        headers={**local_headers(), "X-DeusCFO-Token": session},
    )
    assert response.status_code == 200
    assert response.json() == {"entries_stored": 0}

def test_config_reports_migration_and_persists_valid_league(monkeypatch, tmp_path, client):
    monkeypatch.setattr(main, "CONFIG_PATH", tmp_path / "deuscfo.config.json")

    async def leagues():
        return ["NewLeague", "Standard"]

    monkeypatch.setattr(main, "_available_leagues", leagues)
    session = client.get("/api/session", headers=local_headers()).json()["token"]
    initial = client.get("/api/config", headers=local_headers()).json()
    assert initial["migration_required"] is False
    response = client.put(
        "/api/config",
        json={"league": "NewLeague"},
        headers={**local_headers(), "X-DeusCFO-Token": session},
    )
    assert response.status_code == 200
    assert main._configured_league() == "NewLeague"



def test_config_reports_migration_for_stale_configured_league(monkeypatch, tmp_path, client):
    monkeypatch.setattr(main, "CONFIG_PATH", tmp_path / "deuscfo.config.json")
    main._persist_config("RemovedLeague")

    async def leagues():
        return ["Standard"]

    monkeypatch.setattr(main, "_available_leagues", leagues)
    response = client.get("/api/config", headers=local_headers())
    assert response.status_code == 200
    assert response.json()["migration_required"] is True
def test_config_rejects_unknown_league(monkeypatch, tmp_path, client):
    monkeypatch.setattr(main, "CONFIG_PATH", tmp_path / "deuscfo.config.json")

    async def leagues():
        return ["Standard"]

    monkeypatch.setattr(main, "_available_leagues", leagues)
    session = client.get("/api/session", headers=local_headers()).json()["token"]
    response = client.put(
        "/api/config",
        json={"league": "NotARealLeague"},
        headers={**local_headers(), "X-DeusCFO-Token": session},
    )
    assert response.status_code == 400
