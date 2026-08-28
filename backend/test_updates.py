import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
import updates

ROOT = Path(__file__).resolve().parent.parent


def run(coro):
    return asyncio.run(coro)


def local_headers(origin="http://127.0.0.1:3000"):
    headers = {"host": "127.0.0.1:8000"}
    if origin is not None:
        headers["origin"] = origin
    return headers


@pytest.fixture
def client():
    return TestClient(main.app)


def write_version(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def stable_release(tag="v0.6.0", html_url="https://github.com/MetzeVanDeus/deus-cfo/releases/tag/v0.6.0"):
    return {
        "tag_name": tag,
        "html_url": html_url,
        "published_at": "2026-08-28T00:00:00Z",
        "draft": False,
        "prerelease": False,
    }


def patch_fetch(monkeypatch, payload=None, error=None):
    async def fetch():
        if error is not None:
            raise error
        return updates._parse_release_payload(payload)

    monkeypatch.setattr(updates, "_fetch_latest_release", fetch)


def test_current_version_equals_latest(monkeypatch, tmp_path):
    version_file = tmp_path / "VERSION"
    write_version(version_file, "0.5.0\n")
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(version_file))
    patch_fetch(monkeypatch, stable_release("v0.5.0"))
    status = run(updates.refresh(force=True))
    assert status["current_version"] == "0.5.0"
    assert status["latest_version"] == "0.5.0"
    assert status["update_available"] is False
    assert status["error"] is None


def test_newer_release_is_detected(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, stable_release("v0.6.0"))
    status = run(updates.refresh(force=True))
    assert status["update_available"] is True
    assert status["latest_version"] == "0.6.0"
    assert status["release_url"] == "https://github.com/MetzeVanDeus/deus-cfo/releases/tag/v0.6.0"
    assert status["published_at"] == "2026-08-28T00:00:00Z"
    assert status["error"] is None


def test_older_github_release_does_not_trigger_update(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, stable_release("v0.4.0"))
    status = run(updates.refresh(force=True))
    assert status["latest_version"] == "0.4.0"
    assert status["update_available"] is False


def test_prerelease_payload_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, {**stable_release("v0.6.0-rc.1"), "prerelease": True})
    status = run(updates.refresh(force=True))
    assert status["update_available"] is False
    assert status["latest_version"] is None
    assert status["error"] is None


def test_draft_payload_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, {**stable_release("v0.6.0"), "draft": True})
    status = run(updates.refresh(force=True))
    assert status["update_available"] is False
    assert status["latest_version"] is None
    assert status["error"] is None


def test_github_unavailable_is_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, error=updates.UpdateCheckError("unavailable"))
    status = run(updates.refresh(force=True))
    assert status["current_version"] == "0.5.0"
    assert status["update_available"] is False
    assert status["latest_version"] is None
    assert status["error"] == "unavailable"


def test_malformed_github_payload_is_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")

    async def fetch():
        return updates._parse_release_payload(["not", "a", "release"])

    monkeypatch.setattr(updates, "_fetch_latest_release", fetch)
    status = run(updates.refresh(force=True))
    assert status["update_available"] is False
    assert status["error"] == "malformed"


def test_unparseable_tag_is_malformed(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")

    async def fetch():
        return updates._parse_release_payload({**stable_release(), "tag_name": "nightly"})

    monkeypatch.setattr(updates, "_fetch_latest_release", fetch)
    status = run(updates.refresh(force=True))
    assert status["update_available"] is False
    assert status["error"] == "malformed"


def test_numeric_version_comparison_treats_ten_as_newer_than_nine():
    assert updates.is_newer("0.10.0", "0.9.9") is True
    assert updates.is_newer("0.9.9", "0.10.0") is False
    assert updates.parse_stable_version("v0.10.0") == (0, 10, 0)


def test_source_development_build_does_not_report_nonsense(monkeypatch, tmp_path):
    monkeypatch.setattr(updates.sys, "frozen", False, raising=False)
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, stable_release("v0.4.0"))
    status = run(updates.refresh(force=True))
    assert updates.is_packaged() is False
    assert status["current_version"] == "0.5.0"
    assert status["latest_version"] == "0.4.0"
    assert status["update_available"] is False

    missing = tmp_path / "missing-VERSION"
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(missing))
    patch_fetch(monkeypatch, stable_release("v1.0.0"))
    missing_status = run(updates.refresh(force=True))
    assert missing_status["current_version"] == ""
    assert missing_status["update_available"] is False

    write_version(tmp_path / "VERSION", "dev")
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    dev_status = run(updates.refresh(force=True))
    assert dev_status["current_version"] == "dev"
    assert dev_status["update_available"] is False


def test_cached_result_is_reused_until_forced(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    monkeypatch.setenv("DEUSCFO_UPDATE_CACHE_SECONDS", "3600")
    write_version(tmp_path / "VERSION", "0.5.0")
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return updates._parse_release_payload(stable_release("v0.6.0"))

    monkeypatch.setattr(updates, "_fetch_latest_release", fetch)
    first = run(updates.refresh())
    second = run(updates.refresh())
    assert first["update_available"] is True
    assert second == first
    assert calls["n"] == 1
    forced = run(updates.refresh(force=True))
    assert forced["update_available"] is True
    assert calls["n"] == 2


def test_network_failure_preserves_previous_latest(monkeypatch, tmp_path):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, stable_release("v0.6.0"))
    run(updates.refresh(force=True))
    patch_fetch(monkeypatch, error=updates.UpdateCheckError("unavailable"))
    status = run(updates.refresh(force=True))
    assert status["latest_version"] == "0.6.0"
    assert status["update_available"] is True
    assert status["error"] == "unavailable"


def test_status_endpoint_returns_cached_payload(monkeypatch, tmp_path, client):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, stable_release("v0.6.0"))
    run(updates.refresh(force=True))
    response = client.get("/api/update/status", headers=local_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["current_version"] == "0.5.0"
    assert payload["latest_version"] == "0.6.0"
    assert payload["update_available"] is True
    assert payload["error"] is None


def test_manual_check_requires_session_then_refreshes(monkeypatch, tmp_path, client):
    monkeypatch.setenv("DEUSCFO_VERSION_FILE", str(tmp_path / "VERSION"))
    write_version(tmp_path / "VERSION", "0.5.0")
    patch_fetch(monkeypatch, stable_release("v0.6.0"))
    denied = client.post("/api/update/check", headers=local_headers())
    assert denied.status_code == 403
    token = client.get("/api/session", headers=local_headers()).json()["token"]
    response = client.post(
        "/api/update/check",
        headers={**local_headers(), "X-DeusCFO-Token": token},
    )
    assert response.status_code == 200
    assert response.json()["update_available"] is True


def test_fetch_latest_release_maps_http_failures(monkeypatch):
    class Response:
        status_code = 503

        def json(self):
            return {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(updates.UpdateCheckError) as captured:
        run(updates.fetch_latest_release())
    assert captured.value.code == "unavailable"


def test_fetch_latest_release_maps_malformed_json(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            raise ValueError("no json")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(updates.UpdateCheckError) as captured:
        run(updates.fetch_latest_release())
    assert captured.value.code == "malformed"


def test_fetch_latest_release_maps_connect_failure(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, *_args, **_kwargs):
            raise updates.httpx.ConnectError("offline")

    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **_kwargs: Client())
    with pytest.raises(updates.UpdateCheckError) as captured:
        run(updates.fetch_latest_release())
    assert captured.value.code == "unavailable"


def test_verify_release_version_script_accepts_repo_and_rejects_mismatched_tag():
    expected_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    ok = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_release_version.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert expected_version in ok.stdout
    mismatch = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_release_version.py"), "v9.9.9"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert mismatch.returncode != 0
    assert "git tag" in mismatch.stderr
