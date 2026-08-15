# DeusCFO
[![CI](https://github.com/MetzeVanDeus/deus-cfo/actions/workflows/ci.yml/badge.svg)](https://github.com/MetzeVanDeus/deus-cfo/actions/workflows/ci.yml)

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

The Windows service controller starts the API, independent historical collector, and frontend:

```powershell
python deuscfo.py start
python deuscfo.py status
python deuscfo.py stop
```

Open <http://127.0.0.1:3000>. The backend listens on port 8000 and the Vite development server proxies `/api` requests to it. Scheduled historical collection runs in `backend\collector.py`, independently of the API process.

To run the collector separately:

```powershell
cd backend
python -m collector --league Allflame
```

To run the API and frontend separately:

```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

## CI

GitHub Actions runs the same checks used locally on pushes and pull requests:

- Python 3.12 backend test suite.
- Node.js 20 frontend dependency install and production build.

The workflow does not need repository secrets; runtime market APIs are accessed only by local/manual collection runs.

## Divination-card routes

The profit-route API includes the versioned `backend/div_card_recipes.json` registry. `version`/`verified_version` identify the DeusCFO registry contract; the separate `poe_patch` metadata identifies the Path of Exile game patch used to verify the recipe. The current curated deterministic recipe (`The Doctor` -> `Headhunter`) is verified for PoE `3.29.0`; this is an explicit coverage limit, not a claim that every divination card is modeled. Random, corrupted, influenced, and otherwise unverified rewards are rejected. `GET /api/profit-routes` resolves the patch automatically for leagues listed in the checked-in `verified_leagues` metadata. `DEUSCFO_ACTIVE_POE_PATCH` remains an optional scalar or JSON league-map override for unusual deployments. Query-string values cannot override verification, and unknown or mismatched leagues remain fail-closed.

Routes remain visible as `theoretical`, `non_executable`, or `insufficient_evidence` when exact prices exist without executable depth (or when required prices are missing). The API reports missing evidence and keeps theoretical and executable ROI separate. Executable capacity and ROI stay zero/unknown when reward sell bids are absent; aggregate volume is never treated as fillable inventory, and Headhunter sell depth is never inferred from seller asks.

`UniqueAccessory` is collected through the normal bounded collector so deterministic reward prices can be persisted alongside exchange snapshots. Optional trade depth (`DEUSCFO_TRADE_DEPTH=1`) queries exact recipe card names through the public PoE trade search/fetch API and stores only buy-side card levels as `pathofexile_trade_api` quotes. That API path does not provide reward sell bids; liquidation remains unavailable unless an actual supported adapter supplies `sell_levels`. `DEUSCFO_TRADE_DEPTH_LIMIT` (default 20) bounds listings per card; set `DEUSCFO_TRADE_USER_AGENT` to identify a deployment.

## Verify locally

```powershell
python -m pytest backend
npm ci --prefix frontend
npm run build --prefix frontend
```

Runtime SQLite data, generated frontend output, dependency directories, local process state, and raw market captures are intentionally ignored by Git. Market data is fetched from public Path of Exile economy endpoints at runtime.
