# DeusCFO

[![CI](https://github.com/MetzeVanDeus/deus-cfo/actions/workflows/ci.yml/badge.svg)](https://github.com/MetzeVanDeus/deus-cfo/actions/workflows/ci.yml)

**DeusCFO is a local Path of Exile market-research terminal that tracks historical prices, tests market signals, and identifies evidence-backed opportunities without pretending every theoretical profit is executable.** It is decision support and paper tracking, not an automated trade or gameplay tool.

## Public-beta screenshots

Captured from the packaged Windows service at a 1920×1080 browser viewport; screenshots show repository behavior with no fabricated market data.

![First-run league selection](docs/screenshots/public-beta-first-run.webp)

*First run: no saved league; child panels show “Choose shared league above” and controls remain disabled until the shared context is saved.*

![Configured Standard readiness](docs/screenshots/public-beta-readiness-wait.webp)

*Configured Standard: zero stored rows and zero observed hours, so readiness truthfully remains a WAIT state while collection begins.*

## Paper workflow

The clip below is a local PAPER session using illustrative / non-observed inputs to show the capital-plan and paper-portfolio flow. DeusCFO does not execute trades.

[![CFO PAPER workflow](docs/screenshots/cfo-paper-workflow.webp)](docs/screenshots/cfo-paper-workflow.mp4)

## Download and run

### Windows

#### Packaged release

1. Download `DeusCFO-windows-x64.zip` and `SHA256SUMS.txt` from the [latest GitHub release](https://github.com/MetzeVanDeus/deus-cfo/releases/latest).
2. Verify the ZIP before extracting it:

```powershell
$expected = (Get-Content .\SHA256SUMS.txt).Split()[0]
$actual = (Get-FileHash .\DeusCFO-windows-x64.zip -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw "Checksum mismatch" }
```

3. Extract and launch:

```powershell
Expand-Archive .\DeusCFO-windows-x64.zip -DestinationPath .\DeusCFO-release
cd .\DeusCFO-release\DeusCFO
.\DeusCFO.exe open
```

Use `.\DeusCFO.exe status`, `.\DeusCFO.exe restart`, and `.\DeusCFO.exe stop` to manage it. Releases are checksummed but not signed.

#### Source checkout

Requires Python 3.12 and Node.js 20 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
python deuscfo.py start
```

Open <http://127.0.0.1:8000>. For development with Vite and hot reload, run `python deuscfo.py dev` and open <http://127.0.0.1:3000>.

### Linux

Linux runs natively from source; no Linux binary is published yet. Install Python 3.12, Node.js 20 or newer, npm, and Git. Debian/Ubuntu also requires the `python3.12-venv` package for the virtual environment command below.

```bash
git clone https://github.com/MetzeVanDeus/deus-cfo.git
cd deus-cfo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
python deuscfo.py start
```

Open <http://127.0.0.1:8000>. Use `python deuscfo.py status`, `python deuscfo.py restart`, and `python deuscfo.py stop` to manage it. For development, run `python deuscfo.py dev` and open <http://127.0.0.1:3000>.

The production launcher starts the loopback backend and collector; FastAPI serves the built frontend without Vite. Logs are written to `logs/backend.log` and `logs/collector.log`. `stop` terminates only DeusCFO-owned processes.

## First run and shared league

On first run, choose a live league in **Shared market context** and save it. The UI and collector read the same ignored local `deuscfo.config.json` (`{ "league": "<id>" }`). If a configured league expires, DeusCFO stops silently drifting: it marks migration required and asks you to choose a current league.

The collector first gathers current poe.ninja snapshots. Historical views become useful as observations accumulate. The **Data readiness** panel shows stored rows, observed hours, missing intervals, and the last snapshot; it also starts bounded Currency Exchange backfill. The CFO defaults to **PAPER** and may show clearly labeled, low-confidence Currency Exchange mean-reversion watches from direct hourly quotes; validated capital positions remain behind the existing evidence gates. A first run can therefore show no signals or routes for a while. `WAIT` is a valid result when history, liquidity, patch evidence, or strategy coverage is insufficient. No demo data is inserted.

## What it helps with

- **Research:** inspect price history, regimes, anomalies, and evidence coverage.
- **Decide conservatively:** run capital plans that separate theoretical, non-executable, and executable outcomes.
- **Learn on paper:** record recommendations and paper positions without placing orders.

## Current strategy promise

Production transformation coverage is intentionally narrow: the verified route is **The Doctor → Headhunter** for the patch and leagues declared in `backend/div_card_recipes.json`. Assembly/disassembly, vendor chains, graph routes, six-link routes, and other strategy families have no accepted production records. They remain visibly unsupported rather than being filled with speculative recipes.

A route can remain theoretical or be absent when exact prices, buy-side depth, historical evidence, patch metadata, or liquidation evidence are missing. Headhunter sell depth is never inferred from seller asks. The application never executes trades.

## Data trust and supported upstreams

- `web.poecdn.com/api/currency-exchange` is the documented Currency Exchange CDN API used for hourly historical exchange data.
- poe.ninja supplies current market snapshots and league metadata.
- Project-owner confirmation supports the existing trade-site paths `/api/trade/search`, `/api/trade/fetch`, and `/api/trade/data/static`. They are supported trade-site endpoints, **not** endpoints listed in the official GGG Developer API reference. The collector retains bounded requests and an identifying User-Agent.
The public release does not package a checked-in trade metadata snapshot. Trade metadata is fetched from the supported trade-site endpoint when available; redistribution provenance for any future offline capture must be recorded before it is shipped.

Every result carries evidence and coverage limits where available. Missing history, absent coverage, stale leagues, and unavailable upstreams are surfaced as reasons to wait rather than replaced with estimates.

## Privacy and policy

DeusCFO binds to loopback by default. SQLite market history, journals, paper portfolios, logs, and local configuration remain on your machine. Review logs and free-form notes before sharing diagnostics; see [`docs/privacy.md`](docs/privacy.md).

**This product isn't affiliated with or endorsed by Grinding Gear Games in any way.** Path of Exile and related marks belong to Grinding Gear Games. DeusCFO does not automate gameplay or trade execution. Optional donations are pending GGG guidance and are not linked or feature-gated in this beta.

## Development

Install dependencies:

```powershell
cd frontend
npm ci
cd ..
```

The explicit Vite workflow remains available with `python deuscfo.py dev`, or run the API and frontend separately. Focused backend tests and frontend checks are listed in the project workflow; do not commit runtime databases, `deuscfo.config.json`, raw captures, logs, or `frontend/dist`.

Planning history is under [`docs/design-history`](docs/design-history). Community and release notes are in [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), [`CHANGELOG.md`](CHANGELOG.md), and [`docs/public-beta-release-notes.md`](docs/public-beta-release-notes.md).
