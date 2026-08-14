# DeusCFO

DeusCFO is a local Path of Exile market-intelligence dashboard. It collects public market data, derives signals and opportunities, and presents them in a React UI. It does not execute trades.

## Requirements

- Python 3.12+
- Node.js 20+

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
cd frontend
npm ci
cd ..
```

## Run

The Windows service controller starts both services:

```powershell
python deuscfo.py start
python deuscfo.py status
python deuscfo.py stop
```

Open <http://127.0.0.1:3000>. The backend listens on port 8000 and the Vite development server proxies `/api` requests to it.

To run services separately:

```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

## Verify

```powershell
python -m pytest backend
cd frontend
npm run build
```

Runtime SQLite data, generated frontend output, dependency directories, local process state, and raw market captures are intentionally ignored by Git. Market data is fetched from public Path of Exile economy endpoints at runtime.
