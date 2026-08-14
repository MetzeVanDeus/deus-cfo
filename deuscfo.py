"""Dependency-free DeusCFO service controller for Windows CMD."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / ".deuscfo.pids.json"
FRONTEND_URL = "http://127.0.0.1:3000"
BACKEND_URL = "http://127.0.0.1:8000"

PROJECT_LIMIT_BYTES = 1024 * 1024 * 1024
SQLITE_LIMIT_BYTES = 632 * 1024 * 1024

def _services():
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return {
        "backend": {
            "cwd": ROOT / "backend",
            "command": [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"],
            "url": f"{BACKEND_URL}/api/snapshot/status",
        },
        "collector": {
            "cwd": ROOT / "backend",
            "command": [sys.executable, "-m", "collector"],
            "url": None,
        },
        "frontend": {
            "cwd": ROOT / "frontend",
            "command": [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"],
            "url": FRONTEND_URL,
        },
    }


def _load_pids():
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_pids(pids):
    if pids:
        PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")
    elif PID_FILE.exists():
        PID_FILE.unlink()


def _project_footprint():
    total = 0
    sqlite = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        if path.parent == ROOT / "backend" and path.name.startswith("deuscfo.db"):
            sqlite += size
    return total, sqlite


def _ready(url, pid=None, timeout=1):
    if url is None:
        if pid is None:
            return False
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
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
    pids = _load_pids()
    states = {}
    for name, service in _services().items():
        ready = _ready(service["url"], pids.get(name))
        owner = f"PID {pids[name]}" if name in pids else "external/unowned"
        states[name] = ready
        print(f"{name:8} {'RUNNING' if ready else 'STOPPED':7}  {owner if ready else ''}")
    total, sqlite = _project_footprint()
    print(f"project  {total / 1024**2:,.1f} MiB / 1,024 MiB hard limit")
    print(f"market   {sqlite / 1024**2:,.1f} MiB / 632 MiB SQLite+WAL cap")
    return all(states.values())


def start():
    total, sqlite = _project_footprint()
    if total - sqlite + SQLITE_LIMIT_BYTES >= PROJECT_LIMIT_BYTES:
        print("Refusing to start: installed files leave insufficient room under the 1 GiB limit.")
        return False
    pids = _load_pids()
    flags = 0
    kwargs = {}
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    with open(os.devnull, "wb") as null:
        for name, service in _services().items():
            if _ready(service["url"], pids.get(name)):
                print(f"{name}: already running")
                continue
            process = subprocess.Popen(
                service["command"], cwd=service["cwd"], stdin=null,
                stdout=null, stderr=null, creationflags=flags, **kwargs,
            )
            pids[name] = process.pid
            print(f"{name}: starting PID {process.pid}")
    _save_pids(pids)
    deadline = time.time() + 45
    while time.time() < deadline:
        if all(_ready(service["url"], pids.get(name)) for name, service in _services().items()):
            print(f"Ready: {FRONTEND_URL}")
            return True
        time.sleep(1)
    print("Startup timed out. Run status after checking dependencies.")
    return False


def stop():
    pids = _load_pids()
    if not pids:
        print("No DeusCFO-owned processes. External services were not killed.")
        return True
    for name, pid in list(pids.items()):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        else:
            try:
                os.killpg(pid, 15)
            except ProcessLookupError:
                pass
        print(f"{name}: stopped PID {pid}")
    _save_pids({})
    return True


def run(command):
    if command == "start":
        return start()
    if command == "stop":
        return stop()
    if command == "restart":
        stop()
        return start()
    if command == "status":
        return status()
    if command == "open":
        start()
        webbrowser.open(FRONTEND_URL)
        return True
    print("Usage: python deuscfo.py [start|stop|restart|status|open]")
    return False


def menu():
    actions = {"1": "start", "2": "stop", "3": "restart", "4": "status", "5": "open"}
    while True:
        print("\nDeusCFO  [1] Start  [2] Stop  [3] Restart  [4] Status  [5] Open  [0] Exit")
        choice = input("> ").strip()
        if choice == "0":
            return
        run(actions.get(choice, choice.lower()))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(0 if run(sys.argv[1].lower()) else 1)
    menu()
