import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def local_headers(origin: str | None = "http://127.0.0.1:3000"):
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
    assert client.post("/api/market/history/backfill", json={"league": "Allflame"}, headers=headers).status_code == 403
    assert client.post("/api/update/check", headers=headers).status_code == 403


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

def test_backfill_starts_without_waiting_for_worker(monkeypatch, client):
    calls = []

    async def start(max_hours):
        calls.append(max_hours)
        return {"status": "started", "hours_requested": max_hours, "hours_processed": 0}

    monkeypatch.setattr(main.cx_collector, "start_backfill", start)
    session = client.get("/api/session", headers=local_headers()).json()["token"]
    response = client.post(
        "/api/cx/backfill",
        json={"max_hours": 2},
        headers={**local_headers(), "X-DeusCFO-Token": session},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "started", "hours_requested": 2, "hours_processed": 0}
    assert calls == [2]


def test_market_history_backfill_starts_without_waiting(monkeypatch, client):
    async def start(league):
        return {"status": "started", "league": league, "rows_stored": 0}

    monkeypatch.setattr(main.collector, "start_market_history_backfill", start)
    session = client.get("/api/session", headers=local_headers()).json()["token"]
    response = client.post(
        "/api/market/history/backfill",
        json={"league": "Allflame"},
        headers={**local_headers(), "X-DeusCFO-Token": session},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "started", "league": "Allflame", "rows_stored": 0}


def test_backfill_rejects_unbounded_hours(client):
    session = client.get("/api/session", headers=local_headers()).json()["token"]
    response = client.post(
        "/api/cx/backfill",
        json={"max_hours": 0},
        headers={**local_headers(), "X-DeusCFO-Token": session},
    )
    assert response.status_code == 422

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


def test_packaged_frontend_confines_assets(monkeypatch, tmp_path, client):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("safe", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "index.html").write_text("app shell", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path)
    monkeypatch.setattr(main.FRONTEND_ASSETS, "directory", str(assets))
    monkeypatch.setattr(main.FRONTEND_ASSETS, "all_directories", [str(assets)])
    monkeypatch.setattr(main.FRONTEND_ASSETS, "config_checked", False)

    headers = local_headers(None)
    assert client.get("/assets/app.js", headers=headers).text == "safe"
    assert client.get("/assets/%2e%2e/secret.txt", headers=headers).status_code == 404
    assert client.get("/dashboard", headers=headers).text == "app shell"

def test_flips_validate_budget_and_normalize_nullable_market_fields(monkeypatch, client):
    headers = local_headers()
    session = client.get("/api/session", headers=headers).json()["token"]
    protected = {**headers, "X-DeusCFO-Token": session}

    invalid = client.post(
        "/api/flips",
        json={"budgetCurrency": "chaos", "budgetAmount": 0, "leagueId": "Allflame", "category": "SkillGem"},
        headers=protected,
    )
    assert invalid.status_code == 422

    async def fetch_stash(_client, _league, _category):
        return [{
            "detailsId": "test-item",
            "name": None,
            "icon": None,
            "variant": None,
            "chaosValue": 5,
            "listingCount": 100,
            "sparkLine": {"totalChange": 2, "data": [0, 2, None]},
        }]

    async def fetch_exchange(_client, _league, _category):
        return [{"id": "chaos", "primaryValue": 1}]

    monkeypatch.setattr(main, "_fetch_stash", fetch_stash)
    monkeypatch.setattr(main, "_fetch_exchange", fetch_exchange)
    response = client.post(
        "/api/flips",
        json={"budgetCurrency": "chaos", "budgetAmount": 10, "leagueId": "Allflame", "category": "SkillGem"},
        headers=protected,
    )
    assert response.status_code == 200
    result = response.json()[0]
    assert result["name"] == "Unknown"
    assert result["icon"] == ""
    assert result["variant"] == ""
    assert result["sparkline"] == [0.0, 2.0, None]
