"""Cross-platform controller for the local DeusCFO services."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
APP_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
PID_FILE = APP_ROOT / ".deuscfo.pids.json"
LOG_DIR = APP_ROOT / "logs"
DATA_DIR = APP_ROOT / "data"
CONFIG_FILE = APP_ROOT / "deuscfo.config.json"
BACKEND_URL = "http://127.0.0.1:8000"
DEV_FRONTEND_URL = "http://127.0.0.1:3000"
PROJECT_LIMIT_BYTES = 1024 * 1024 * 1024
SQLITE_LIMIT_BYTES = 632 * 1024 * 1024


def _bundle_version():
    path = BUNDLE_ROOT / "VERSION"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Bundled VERSION is unavailable: {path}") from exc
    if not VERSION_RE.fullmatch(value):
        raise RuntimeError(f"Bundled VERSION is invalid: {path}")
    return value


def _production_available():
    return (BUNDLE_ROOT / "frontend" / "dist" / "index.html").is_file()


def _services(mode="prod"):
    if os.name == "nt":
        npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    else:
        npm = shutil.which("npm") or "npm"
    backend_cwd = BUNDLE_ROOT / "backend" if (BUNDLE_ROOT / "backend").is_dir() else BUNDLE_ROOT
    if FROZEN:
        backend_command = [sys.executable, "--service", "backend"]
        collector_command = [sys.executable, "--service", "collector"]
    else:
        backend_command = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"]
        collector_command = [sys.executable, "-m", "collector"]
    services = {
        "backend": {"cwd": backend_cwd, "command": backend_command, "url": f"{BACKEND_URL}/api/session"},
        "collector": {"cwd": backend_cwd, "command": collector_command, "url": None},
    }
    if mode == "dev":
        services["frontend"] = {
            "cwd": BUNDLE_ROOT / "frontend",
            "command": [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"],
            "url": DEV_FRONTEND_URL,
        }
    return services


def _load_state():
    try:
        value = json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mode": "prod", "pids": {}}
    if isinstance(value, dict) and isinstance(value.get("pids"), dict):
        return value
    if isinstance(value, dict):
        return {"mode": "prod", "pids": value}
    return {"mode": "prod", "pids": {}}


def _save_state(mode, pids, backend_token=None):
    if pids:
        payload = {"mode": mode, "pids": pids}
        if isinstance(backend_token, str) and backend_token:
            payload["backend_token"] = backend_token
        PID_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    elif PID_FILE.exists():
        PID_FILE.unlink()


def _process_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return any(f" {pid} " in line for line in result.stdout.splitlines())
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError):
        return False


def _terminate_process(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return
    try:
        os.killpg(int(pid), 15)
    except (OSError, TypeError, ValueError):
        pass


def _project_footprint():
    total = sqlite = 0
    database_root = DATA_DIR if FROZEN else BUNDLE_ROOT / "backend"
    for path in APP_ROOT.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        if path.parent == database_root and path.name.startswith("deuscfo.db"):
            sqlite += size
    return total, sqlite


def _runtime_env():
    env = os.environ.copy()
    if FROZEN:
        env["DEUSCFO_DATA_DIR"] = str(DATA_DIR)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    env["DEUSCFO_FRONTEND_DIST"] = str(BUNDLE_ROOT / "frontend" / "dist")
    env["DEUSCFO_CONFIG_PATH"] = str(CONFIG_FILE)
    return env


def _backend_probe(url, timeout=1):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return False, None
            try:
                payload = json.load(response)
            except (TypeError, ValueError):
                return False, None
    except urllib.error.HTTPError:
        return False, None
    except OSError as exc:
        if isinstance(exc, ConnectionRefusedError):
            return None, None
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, ConnectionRefusedError):
            return None, None
        return False, None
    return True, payload if isinstance(payload, dict) else None


def _backend_identity(url, expected_version, expected_token=None, timeout=1):
    ready, payload = _backend_probe(url, timeout)
    if ready is not True or not isinstance(payload, dict):
        return ready
    return bool(expected_token) and payload.get("version") == expected_version and payload.get("token") == expected_token


def _backend_runtime_token(url, expected_version, timeout=1):
    ready, payload = _backend_probe(url, timeout)
    if ready is True and isinstance(payload, dict) and payload.get("version") == expected_version:
        token = payload.get("token")
        if isinstance(token, str) and token:
            return token
    return None


def _listener_occupied(url, timeout=1):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return True
    except urllib.error.HTTPError:
        return True
    except OSError as exc:
        if isinstance(exc, ConnectionRefusedError):
            return False
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, ConnectionRefusedError):
            return False
        return True


def _ready(url, pid=None, timeout=1, expected_version=None, expected_token=None):
    if expected_version is not None:
        return _backend_identity(url, expected_version, expected_token, timeout) is True
    if url is None:
        return _process_alive(pid)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except OSError:
        return False


def status():
    state = _load_state()
    pids = state["pids"]
    version = _bundle_version()
    backend_token = state.get("backend_token")
    services = _services(state["mode"])
    for name, service in services.items():
        expected = version if name == "backend" else None
        token = backend_token if name == "backend" else None
        ready = _ready(service["url"], pids.get(name), expected_version=expected, expected_token=token)
        owner = f"PID {pids[name]}" if name in pids else "external/unowned"
        print(f"{name:8} {'RUNNING' if ready else 'STOPPED':7}  {owner if ready else ''}")
    total, sqlite = _project_footprint()
    print(f"project  {total / 1024**2:,.1f} MiB / 1,024 MiB hard limit")
    print(f"market   {sqlite / 1024**2:,.1f} MiB / 632 MiB SQLite+WAL cap")
    return all(_ready(service["url"], pids.get(name), expected_version=(version if name == "backend" else None), expected_token=(backend_token if name == "backend" else None)) for name, service in services.items())


def start(mode="prod"):
    version = _bundle_version()
    if mode == "prod" and not _production_available():
        print(
            "Production frontend is missing. Run: npm ci --prefix frontend && "
            "npm run build --prefix frontend; or use: python deuscfo.py dev"
        )
        return False
    total, sqlite = _project_footprint()
    if total - sqlite + SQLITE_LIMIT_BYTES >= PROJECT_LIMIT_BYTES:
        print("Refusing to start: installed files leave insufficient room under the 1 GiB limit.")
        return False
    state = _load_state()
    pids = state["pids"]
    services = _services(mode)
    stored_token = state.get("backend_token")
    if not isinstance(stored_token, str) or not stored_token:
        stored_token = None
    backend_identity = _backend_identity(services["backend"]["url"], version, stored_token)
    if backend_identity is True and (not pids.get("backend") or not _process_alive(pids["backend"])):
        backend_identity = False
    if backend_identity is False:
        print(f"Refusing to start: port 8000 is occupied by an unidentified or different DeusCFO version (expected v{version}). Stop the existing service manually.")
        return False
    if mode == "dev":
        frontend_pid = pids.get("frontend")
        if _listener_occupied(services["frontend"]["url"]) and not (frontend_pid and _process_alive(frontend_pid)):
            print("Refusing to start: port 3000 is occupied by an unowned frontend. Stop the existing service manually.")
            return False
    flags = 0
    kwargs = {}
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    LOG_DIR.mkdir(exist_ok=True)
    spawned = {}
    reused_backend = backend_identity is True
    backend_token = stored_token if reused_backend else None

    def cleanup():
        for name, pid in spawned.items():
            _terminate_process(pid)
            if pids.get(name) == pid:
                pids.pop(name, None)
        _save_state(mode, pids, backend_token if "backend" not in spawned else None)

    for name, service in services.items():
        if name == "backend":
            ready = reused_backend and _ready(service["url"], pids.get(name), expected_version=version, expected_token=backend_token)
            if reused_backend and not ready:
                cleanup()
                print("Refusing to continue: owned backend identity was lost during startup.")
                return False
        elif name == "frontend" and mode == "dev":
            frontend_pid = pids.get(name)
            frontend_alive = frontend_pid and _process_alive(frontend_pid)
            ready = bool(frontend_alive and _ready(service["url"], frontend_pid))
            if not ready and frontend_alive:
                continue
        else:
            ready = _ready(service["url"], pids.get(name))
        if ready:
            print(f"{name}: already running")
            continue
        log = None
        try:
            log = (LOG_DIR / f"{name}.log").open("ab")
            process = subprocess.Popen(service["command"], cwd=service["cwd"], stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags, env=_runtime_env(), **kwargs)
        except OSError:
            cleanup()
            raise
        finally:
            if log is not None:
                log.close()
        pids[name] = process.pid
        spawned[name] = process.pid
        print(f"{name}: starting PID {process.pid} (logs/{name}.log)")
    deadline = time.time() + 45
    while time.time() < deadline:
        if "backend" in spawned and backend_token is None:
            backend_token = _backend_runtime_token(services["backend"]["url"], version)
            if backend_token:
                _save_state(mode, pids, backend_token)
        ready = True
        for name, service in services.items():
            expected = version if name == "backend" else None
            token = backend_token if name == "backend" else None
            if not _ready(service["url"], pids.get(name), expected_version=expected, expected_token=token):
                if name == "backend" and reused_backend:
                    cleanup()
                    print("Refusing to continue: owned backend identity was lost during startup.")
                    return False
                ready = False
                break
        if ready:
            url = BACKEND_URL if mode == "prod" else DEV_FRONTEND_URL
            _save_state(mode, pids, backend_token)
            print(f"Ready: {url}")
            return True
        time.sleep(1)
    cleanup()
    print("Startup timed out. Run status and inspect logs.")
    return False




def stop():
    state = _load_state()
    if not state["pids"]:
        print("No DeusCFO-owned processes. External services were not killed.")
        return True
    for name, pid in list(state["pids"].items()):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            try:
                os.killpg(pid, 15)
            except ProcessLookupError:
                pass
        print(f"{name}: stopped PID {pid}")
    _save_state(state["mode"], {})
    return True


def _service_main(name):
    sys.path.insert(0, str(BUNDLE_ROOT / "backend"))
    if name == "backend":
        import uvicorn
        uvicorn.run("main:app", host="127.0.0.1", port=8000, access_log=False)
        return
    if name == "collector":
        import collector
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        interval = int(os.environ.get("DEUSCFO_COLLECTOR_INTERVAL", "1800"))
        asyncio.run(collector.run_collector(None, interval, False))
        return
    raise SystemExit(f"Unknown service: {name}")


def run(command):
    if command == "start":
        return start("prod")
    if command == "dev":
        return start("dev")
    if command == "stop":
        return stop()
    if command == "restart":
        stop()
        return start("prod")
    if command == "status":
        return status()
    if command == "version":
        print(f"DeusCFO v{_bundle_version()}")
        return True
    if command == "open":
        state = _load_state()
        if not start(state["mode"]):
            return False
        webbrowser.open(BACKEND_URL if state["mode"] == "prod" else DEV_FRONTEND_URL)
        return True
    print("Usage: python deuscfo.py [start|dev|stop|restart|status|open|version]")
    return False


def menu():
    actions = {"1": "start", "2": "stop", "3": "restart", "4": "status", "5": "open", "6": "dev"}
    while True:
        print("\nDeusCFO  [1] Start  [2] Stop  [3] Restart  [4] Status  [5] Open  [6] Dev  [0] Exit")
        choice = input("> ").strip()
        if choice == "0":
            return
        run(actions.get(choice, choice.lower()))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--service":
        _service_main(sys.argv[2] if len(sys.argv) > 2 else "")
    elif len(sys.argv) > 1:
        raise SystemExit(0 if run(sys.argv[1].lower()) else 1)
    elif FROZEN:
        raise SystemExit(0 if run("open") else 1)
    else:
        menu()
