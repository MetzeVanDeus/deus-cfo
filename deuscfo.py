"""Cross-platform controller for the local DeusCFO services."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
APP_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
PID_FILE = APP_ROOT / ".deuscfo.pids.json"
LOG_DIR = APP_ROOT / "logs"
DATA_DIR = APP_ROOT / "data"
CONFIG_FILE = APP_ROOT / "deuscfo.config.json"
BACKEND_URL = "http://127.0.0.1:8000"
DEV_FRONTEND_URL = "http://127.0.0.1:3000"
PROJECT_LIMIT_BYTES = 1024 * 1024 * 1024
SQLITE_LIMIT_BYTES = 632 * 1024 * 1024


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
    if "pids" in value:
        return value
    return {"mode": "prod", "pids": value}


def _save_state(mode, pids):
    if pids:
        PID_FILE.write_text(json.dumps({"mode": mode, "pids": pids}, indent=2), encoding="utf-8")
    elif PID_FILE.exists():
        PID_FILE.unlink()


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


def _ready(url, pid=None, timeout=1):
    if url is None:
        if pid is None:
            return False
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
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except OSError:
        return False


def status():
    state = _load_state()
    pids = state["pids"]
    for name, service in _services(state["mode"]).items():
        ready = _ready(service["url"], pids.get(name))
        owner = f"PID {pids[name]}" if name in pids else "external/unowned"
        print(f"{name:8} {'RUNNING' if ready else 'STOPPED':7}  {owner if ready else ''}")
    total, sqlite = _project_footprint()
    print(f"project  {total / 1024**2:,.1f} MiB / 1,024 MiB hard limit")
    print(f"market   {sqlite / 1024**2:,.1f} MiB / 632 MiB SQLite+WAL cap")
    return all(_ready(service["url"], pids.get(name)) for name, service in _services(state["mode"]).items())


def start(mode="prod"):
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
    flags = 0
    kwargs = {}
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    LOG_DIR.mkdir(exist_ok=True)
    for name, service in _services(mode).items():
        if _ready(service["url"], pids.get(name)):
            print(f"{name}: already running")
            continue
        log = (LOG_DIR / f"{name}.log").open("ab")
        process = subprocess.Popen(service["command"], cwd=service["cwd"], stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags, env=_runtime_env(), **kwargs)
        log.close()
        pids[name] = process.pid
        print(f"{name}: starting PID {process.pid} (logs/{name}.log)")
    _save_state(mode, pids)
    deadline = time.time() + 45
    while time.time() < deadline:
        if all(_ready(service["url"], pids.get(name)) for name, service in _services(mode).items()):
            url = BACKEND_URL if mode == "prod" else DEV_FRONTEND_URL
            print(f"Ready: {url}")
            return True
        time.sleep(1)
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
    if command == "open":
        state = _load_state()
        if not start(state["mode"]):
            return False
        webbrowser.open(BACKEND_URL if state["mode"] == "prod" else DEV_FRONTEND_URL)
        return True
    print("Usage: python deuscfo.py [start|dev|stop|restart|status|open]")
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
