import json
import urllib.error

import pytest

import deuscfo


class _Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class _Process:
    pid = 4321


def _patch_launcher(monkeypatch, tmp_path, state=None, urlopen=None):
    saved = []
    monkeypatch.setattr(deuscfo, "PID_FILE", tmp_path / "state.json")
    monkeypatch.setattr(deuscfo, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(deuscfo, "_bundle_version", lambda: "0.5.3")
    monkeypatch.setattr(deuscfo, "_production_available", lambda: True)
    monkeypatch.setattr(deuscfo, "_project_footprint", lambda: (0, 0))
    monkeypatch.setattr(deuscfo, "_load_state", lambda: state or {"mode": "prod", "pids": {}})
    monkeypatch.setattr(deuscfo, "_save_state", lambda mode, pids, backend_token=None: saved.append((mode, dict(pids), backend_token)))
    def services(mode):
        result = {"backend": {"url": "http://127.0.0.1:8000/api/session", "command": [], "cwd": "."}}
        if mode == "dev":
            result["frontend"] = {"url": "http://127.0.0.1:3000", "command": [], "cwd": "."}
        return result
    monkeypatch.setattr(deuscfo, "_services", services)
    if urlopen is None:
        def default_urlopen(*_args, **_kwargs):
            return _Response({"token": "token", "version": "0.5.3"})
        urlopen = default_urlopen
    monkeypatch.setattr(deuscfo.urllib.request, "urlopen", urlopen)
    return saved


def test_linux_dev_uses_native_npm_command(monkeypatch):
    looked_up = []
    monkeypatch.setattr(deuscfo.os, "name", "posix")
    monkeypatch.setattr(deuscfo.shutil, "which", lambda name: looked_up.append(name))
    command = deuscfo._services("dev")["frontend"]["command"]
    assert looked_up == ["npm"]
    assert command[0] == "npm"


def test_matching_backend_version_and_token_is_reused_without_spawn(monkeypatch, tmp_path, capsys):
    state = {"mode": "prod", "pids": {"backend": 123}, "backend_token": "token"}
    _patch_launcher(monkeypatch, tmp_path, state)
    monkeypatch.setattr(deuscfo, "_process_alive", lambda _pid: True)
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert deuscfo.start() is True
    assert "backend: already running" in capsys.readouterr().out


@pytest.mark.parametrize("payload", [{"token": "token", "version": "0.5.3"}, {"token": "token", "version": "0.5.0"}, {"token": "token"}])
def test_unowned_or_mismatched_backend_refuses_without_spawn_or_browser(monkeypatch, tmp_path, payload):
    _patch_launcher(monkeypatch, tmp_path, {"mode": "prod", "pids": {}}, lambda *_args, **_kwargs: _Response(payload))
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")))
    monkeypatch.setattr(deuscfo.webbrowser, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not open browser")))
    assert deuscfo.run("open") is False


@pytest.mark.parametrize("exc", [urllib.error.HTTPError("http://127.0.0.1:8000", 404, "not found", {}, None), TimeoutError()])
def test_occupied_backend_error_refuses_without_spawn(monkeypatch, tmp_path, exc):
    _patch_launcher(monkeypatch, tmp_path, urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(exc))
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert deuscfo.start() is False


def test_free_backend_port_spawns_and_persists_runtime_token(monkeypatch, tmp_path):
    calls = iter([ConnectionRefusedError(), _Response({"token": "new-token", "version": "0.5.3"}), _Response({"token": "new-token", "version": "0.5.3"})])
    def urlopen(*_args, **_kwargs):
        value = next(calls)
        if isinstance(value, BaseException):
            raise value
        return value
    saved = _patch_launcher(monkeypatch, tmp_path, urlopen=urlopen)
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: _Process())
    assert deuscfo.start() is True
    assert saved[-1] == ("prod", {"backend": 4321}, "new-token")


def test_failed_readiness_cleans_only_new_processes(monkeypatch, tmp_path):
    saved = _patch_launcher(monkeypatch, tmp_path, urlopen=lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))
    killed = []
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: _Process())
    monkeypatch.setattr(deuscfo, "_terminate_process", killed.append)
    clock = iter([0, 46])
    monkeypatch.setattr(deuscfo.time, "time", lambda: next(clock))
    assert deuscfo.start() is False
    assert killed == [4321]
    assert saved[-1] == ("prod", {}, None)


def test_dev_unowned_frontend_listener_refuses_before_spawn(monkeypatch, tmp_path):
    def urlopen(url, **_kwargs):
        if url.endswith(":3000"):
            return _Response({})
        raise ConnectionRefusedError()
    _patch_launcher(monkeypatch, tmp_path, {"mode": "dev", "pids": {}}, urlopen)
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert deuscfo.start("dev") is False




def test_reused_backend_loss_fails_fast_and_cleans_new_services(monkeypatch, tmp_path):
    responses = iter([_Response({"token": "token", "version": "0.5.3"}), _Response({"token": "token", "version": "0.5.3"}), ConnectionRefusedError()])
    def urlopen(*_args, **_kwargs):
        value = next(responses)
        if isinstance(value, BaseException):
            raise value
        return value
    state = {"mode": "prod", "pids": {"backend": 123}, "backend_token": "token"}
    saved = _patch_launcher(monkeypatch, tmp_path, state, urlopen)
    monkeypatch.setattr(deuscfo, "_process_alive", lambda pid: pid == 123)
    monkeypatch.setattr(deuscfo, "_services", lambda _mode: {
        "backend": {"url": "http://127.0.0.1:8000/api/session", "command": [], "cwd": "."},
        "collector": {"url": None, "command": [], "cwd": "."},
    })
    killed = []
    monkeypatch.setattr(deuscfo, "_terminate_process", killed.append)
    monkeypatch.setattr(deuscfo.subprocess, "Popen", lambda *_args, **_kwargs: _Process())
    assert deuscfo.start() is False
    assert killed == [4321]
    assert saved[-1] == ("prod", {"backend": 123}, "token")


def test_version_command_reports_bundle_identity(monkeypatch, capsys):
    monkeypatch.setattr(deuscfo, "_bundle_version", lambda: "0.5.3")
    assert deuscfo.run("version") is True
    assert capsys.readouterr().out.strip() == "DeusCFO v0.5.3"


def test_backend_token_is_persisted_with_pid_state(monkeypatch, tmp_path):
    monkeypatch.setattr(deuscfo, "PID_FILE", tmp_path / "state.json")
    deuscfo._save_state("prod", {"backend": 4321}, "token")
    assert deuscfo._load_state() == {"mode": "prod", "pids": {"backend": 4321}, "backend_token": "token"}
