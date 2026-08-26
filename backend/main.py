from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
import httpx
import math
import json
import logging
import os
import secrets
import hmac
import tempfile
import sys
from pathlib import Path
from urllib.parse import urlsplit
import database
import collector
import market_data
import regimes
import anomalies
import signals
import opportunity
import validation
import capital
import portfolio
import strategies
import cx_collector
import cx_metadata
import cx_queries
import market_relationships
import coverage

log = logging.getLogger("deuscfo.main")

app = FastAPI(title="DeusCFO")

ALLOWED_ORIGINS = frozenset({"http://127.0.0.1:3000", "http://localhost:3000"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SESSION_TOKEN = secrets.token_urlsafe(32)
CONFIG_PATH = Path(os.environ["DEUSCFO_CONFIG_PATH"]) if os.environ.get("DEUSCFO_CONFIG_PATH") else Path(__file__).resolve().parent.parent / "deuscfo.config.json"
FRONTEND_DIST = Path(os.environ["DEUSCFO_FRONTEND_DIST"]) if os.environ.get("DEUSCFO_FRONTEND_DIST") else Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "frontend" / "dist"


def _host_parts(request: Request) -> tuple[str, int | None] | None:
    """Parse Host without trusting arbitrary forwarded-host headers."""
    raw = request.headers.get("host", "")
    try:
        parsed = urlsplit(f"//{raw}")
        hostname = (parsed.hostname or "").casefold()
        port = parsed.port
    except ValueError:
        return None
    if hostname not in LOOPBACK_HOSTS:
        return None
    return hostname, port


def _origin_allowed(request: Request) -> bool:
    host = _host_parts(request)
    if host is None:
        return False
    origin = request.headers.get("origin")
    if not origin:
        return True
    if origin in ALLOWED_ORIGINS:
        return True
    try:
        parsed = urlsplit(origin)
        origin_hostname = (parsed.hostname or "").casefold()
        origin_port = parsed.port or 80
    except ValueError:
        return False
    if parsed.scheme != "http" or origin_hostname not in LOOPBACK_HOSTS:
        return False
    host_port = host[1] or 80
    return origin_hostname == host[0] and origin_port == host_port


@app.middleware("http")
async def restrict_local_requests(request: Request, call_next):
    if not _origin_allowed(request):
        return JSONResponse(status_code=403, content={"detail": "unapproved local origin or host"})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-DeusCFO-Token"],
)


def _configured_league() -> str:
    try:
        with CONFIG_PATH.open(encoding="utf-8") as handle:
            value = json.load(handle).get("league")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return os.environ.get("DEUSCFO_LEAGUE", "").strip()


def _persist_config(league: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="deuscfo.config.", suffix=".tmp", dir=CONFIG_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"league": league}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, CONFIG_PATH)
    except Exception:
        # Preserve atomic replacement semantics while cleaning up any temp file.
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


async def _available_leagues() -> list[str] | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{POE_NINJA_BASE}/poe1/api/economy/leagues")
            if response.status_code != 200:
                return None
            payload = response.json()
    except Exception:
        # Network/shape failures fail closed for configuration writes.
        log.exception("could not fetch current poe.ninja leagues")
        return None
    if not isinstance(payload, list):
        return None
    return sorted({item["id"] for item in payload if isinstance(item, dict) and isinstance(item.get("id"), str)})


async def require_local_session(request: Request) -> None:
    token = request.headers.get("X-DeusCFO-Token", "")
    if not token or not hmac.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(status_code=403, detail="valid local session token required")

POE_NINJA_BASE = "https://poe.ninja"

# Shared category ids and poe.ninja API type values.
EXCHANGE_TYPES = market_data.EXCHANGE_TYPES
STASH_TYPES = market_data.STASH_TYPES
ALL_CATEGORIES = market_data.ALL_CATEGORIES


class LeagueResponse(BaseModel):
    id: str
    name: str


class FlipRequest(BaseModel):
    budgetCurrency: str   # "chaos" or "divine"
    budgetAmount: float = Field(gt=0, allow_inf_nan=False)
    leagueId: str = Field(min_length=1)
    category: str         # e.g. "Currency", "Scarab", "SkillGem"


class FlipResult(BaseModel):
    itemId: str
    name: str
    icon: str
    variant: str
    priceChaos: float
    priceInBudget: float
    flipScore: float       # 0-100 composite
    dipFromPeak: float     # 0 (at peak) to 1 (at bottom) — buy signal
    swingDepth: float      # % swing of recent trajectory
    monotonicDecline: bool # True if price only ever fell (death-trap flag)
    volume: float
    totalChange: float
    sparkline: list[float | None]


@app.get("/api/leagues")
async def get_leagues():
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{POE_NINJA_BASE}/poe1/api/economy/leagues")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch leagues")
        return resp.json()

class ConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    league: str = Field(min_length=1)


@app.get("/api/session")
async def get_session(request: Request):
    """Return the process-local token only after local host/origin middleware approval."""
    return {"token": SESSION_TOKEN}


@app.get("/api/config")
async def get_config():
    league = _configured_league()
    available = await _available_leagues()
    known = available is not None
    values = available or []
    return {
        "league": league,
        "available": values,
        "migration_required": known and bool(league) and league not in values,
    }


@app.put("/api/config", dependencies=[Depends(require_local_session)])
async def update_config(request: ConfigRequest):
    available = await _available_leagues()
    if available is None:
        raise HTTPException(status_code=503, detail="current league list unavailable")
    if request.league not in available:
        raise HTTPException(status_code=400, detail="selected league is not currently available")
    _persist_config(request.league)
    return {
        "league": request.league,
        "available": available,
        "migration_required": False,
    }


@app.get("/api/categories")
async def get_categories():
    return [
        {"id": k, "name": v, "source": "exchange" if k in EXCHANGE_TYPES else "stash"}
        for k, v in ALL_CATEGORIES.items()
    ]




def _compute_flip_signals(spark_data, volume):
    """
    Extract raw component signals for a flip candidate.

    Trajectory samples are cumulative percent-change (oldest -> newest);
    `totalChange` is the latest sample. Signals returned:

      dipFromPeak   : 0..1 position of the current price within its recent range
                     (1 = at the bottom = deepest dip). Buy-the-dip signal.
      swingPct      : the trajectory's total swing as a percent, for display.
      monotonicDecline : True if price only ever fell (dying item, not a dip to
                     buy). Such items get no reversal credit.
      liquidity     : 0..1 log-scaled volume with a hard floor.

    Returns (dipFromPeak, swingPct, monotonicDecline, liquidity) or
    (0, 0, False, 0) for items with no usable signal.
    """
    samples = [x for x in spark_data if x is not None]
    if len(samples) < 2:
        return 0.0, 0.0, False, 0.0

    lo, hi = min(samples), max(samples)
    span = hi - lo
    if span < 1.0:  # <1% total move — nothing to flip
        return 0.0, 0.0, False, 0.0

    current = samples[-1]
    dip_from_peak = max(0.0, min(1.0, (hi - current) / span))  # 1 = at bottom

    mid = (lo + hi) / 2.0
    swing_pct = abs(span) / abs(mid) * 100.0 if mid != 0 else 0.0

    peak_idx = max(range(len(samples)), key=lambda i: samples[i])
    monotonic_decline = peak_idx == 0

    if volume < 50:  # ponytail: hard liquidity floor; raise if illiquid flips show up
        return 0.0, 0.0, False, 0.0
    liquidity = min(math.log10(volume + 1) / 4.0, 1.0)  # ~1.0 at vol=1000

    return round(dip_from_peak, 4), round(swing_pct, 2), monotonic_decline, round(liquidity, 4)


async def _fetch_exchange(client, league, category_type):
    """Fetch from exchange overview endpoint."""
    resp = await client.get(
        f"{POE_NINJA_BASE}/poe1/api/economy/exchange/current/overview",
        params={"league": league, "type": category_type},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Failed to fetch {category_type} from poe.ninja")
    data = resp.json()
    return data.get("lines", [])


async def _fetch_stash(client, league, category_type):
    """Fetch from stash item overview endpoint."""
    resp = await client.get(
        f"{POE_NINJA_BASE}/poe1/api/economy/stash/current/item/overview",
        params={"league": league, "type": category_type},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Failed to fetch {category_type} from poe.ninja")
    data = resp.json()
    return data.get("lines", [])


@app.post("/api/flips", response_model=list[FlipResult], dependencies=[Depends(require_local_session)])
async def find_flips(request: FlipRequest):
    category = request.category
    if category not in ALL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")

    async with httpx.AsyncClient(timeout=20.0) as client:
        if category in EXCHANGE_TYPES:
            lines = await _fetch_exchange(client, request.leagueId, category)
        else:
            lines = await _fetch_stash(client, request.leagueId, category)

        # Resolve the budget currency's price in chaos using this request's client.
        budget_price = None
        if category in EXCHANGE_TYPES:
            for line in lines:
                if isinstance(line, dict) and line.get("id") == request.budgetCurrency:
                    budget_price = collector._finite_number(line.get("primaryValue"))
                    if budget_price is not None:
                        break
        if budget_price is None:
            curr_lines = await _fetch_exchange(client, request.leagueId, "Currency")
            for line in curr_lines:
                if isinstance(line, dict) and line.get("id") == request.budgetCurrency:
                    budget_price = collector._finite_number(line.get("primaryValue"))
                    if budget_price is not None:
                        break

    if budget_price is None or budget_price <= 0:
        raise HTTPException(status_code=400, detail=f"Cannot resolve budget currency '{request.budgetCurrency}'")

    budget_total_chaos = request.budgetAmount * budget_price
    results = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        if category in EXCHANGE_TYPES:
            item_id = line.get("id")
            if not isinstance(item_id, str) or not item_id:
                continue
            name = market_data.format_slug(item_id)
            icon = ""
            variant = ""
            price_chaos = collector._finite_number(line.get("primaryValue"), 0)
            volume = collector._finite_number(line.get("volumePrimaryValue"), 0)
            spark = line.get("sparkline")
        else:
            item_id = collector.stash_item_id(line)
            name = line.get("name") if isinstance(line.get("name"), str) else "Unknown"
            icon = line.get("icon") if isinstance(line.get("icon"), str) else ""
            variant = line.get("variant") if isinstance(line.get("variant"), str) else ""
            price_chaos = collector._finite_number(line.get("chaosValue"), 0)
            volume = collector._finite_number(line.get("listingCount") or line.get("count"), 0)
            spark = line.get("sparkLine")
        if price_chaos is None or volume is None:
            continue
        spark = spark if isinstance(spark, dict) else {}
        raw_sparkline = spark.get("data") if isinstance(spark.get("data"), list) else []
        sparkline = [
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
            else None
            for value in raw_sparkline
        ]
        spark_data = [value for value in sparkline if value is not None]
        total_change = collector._finite_number(spark.get("totalChange"), 0)
        if total_change is None:
            total_change = 0

        if price_chaos <= 0 or price_chaos > budget_total_chaos:
            continue
        dip, swing_pct, mono, liq = _compute_flip_signals(spark_data, volume)
        if dip <= 0 and liq <= 0:
            continue  # no usable signal

        swing_log = math.log1p(swing_pct / 20.0)  # log-compress swing for scoring
        results.append({
            "itemId": item_id,
            "name": name,
            "icon": icon,
            "variant": variant,
            "priceChaos": round(price_chaos, 2),
            "priceInBudget": round(price_chaos / budget_price, 4),
            "_dip": dip,
            "_swing": swing_log,
            "_liq": liq,
            "_mono": mono,
            "dipFromPeak": dip,
            "swingDepth": round(swing_pct, 1),
            "monotonicDecline": mono,
            "volume": round(volume, 0),
            "totalChange": round(total_change, 2),
            "sparkline": sparkline,
        })
    # swing and liquidity are min-max normalized within the cohort so the
    # ranking is discriminative instead of saturating at the top of the scale.
    if results:
        def mn(key):
            vals = [r["_" + key] for r in results]
            lo, hi = min(vals), max(vals)
            def f(v):
                return (v - lo) / (hi - lo) if hi > lo else 1.0
            return f

        swing_norm = mn("swing")
        liq_norm = mn("liq")

        for r in results:
            dip_credit = r["_dip"] * (0.4 if r["_mono"] else 1.0)
            raw = 0.45 * dip_credit + 0.35 * swing_norm(r["_swing"]) + 0.20 * liq_norm(r["_liq"])
            r["flipScore"] = round(raw * 100, 1)
        results.sort(key=lambda x: x["flipScore"], reverse=True)

    for r in results:
        r.pop("_dip", None)
        r.pop("_swing", None)
        r.pop("_liq", None)
        r.pop("_mono", None)
        r["dipFromPeak"] = round(r["dipFromPeak"], 3)
        r["swingDepth"] = round(r["swingDepth"], 1)  # already a percent value

    return results[:50]


class SnapshotRequest(BaseModel):
    league: str
    category: str | None = None


@app.post("/api/snapshot", dependencies=[Depends(require_local_session)])
async def trigger_snapshot(request: SnapshotRequest):
    """Manually trigger snapshot collection for a league (optionally one category)."""
    if request.category and request.category not in ALL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{request.category}'")
    if request.category and request.category not in collector.PERSISTED_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Historical storage is disabled for high-cardinality category '{request.category}'",
        )
    if request.category:
        stored = await collector.collect_snapshot(request.league, request.category)
        await database.prune_market_data(collector.PERSISTED_CATEGORIES, league=request.league)
    else:
        stored = sum((await collector.collect_all_categories(request.league)).values())
    return {"league": request.league, "items_stored": stored}


@app.get("/api/snapshot/status")
async def snapshot_status():
    db = await database.get_db()
    try:
        cur = await db.execute(
            """SELECT league, MAX(timestamp) AS last_snapshot FROM snapshots GROUP BY league"""
        )
        leagues = {r["league"]: r["last_snapshot"] for r in await cur.fetchall()}
    finally:
        await db.close()
    footprint = database.storage_footprint()
    return {
        "last_snapshot_per_league": leagues,
        "total_rows": await database.count_rows(),
        "storage_bytes": footprint,
        "storage_limit_bytes": database.MAX_DATABASE_BYTES + database.MAX_WAL_BYTES,
        "snapshot_retention_days": database.SNAPSHOT_RETENTION_DAYS,
        "project_size_bytes": database.project_footprint(),
        "collection_stop_bytes": database.COLLECTION_STOP_BYTES,
        "cx_retention_days": database.CX_RETENTION_DAYS,
        "persisted_categories": sorted(collector.PERSISTED_CATEGORIES),
    }


@app.get("/api/history")
async def price_history(league: str, category: str, item_id: str, hours: float = 24):
    return [
        {"timestamp": ts, "price": price, "volume": vol}
        for ts, price, vol in await market_data.get_price_history(league, category, item_id, hours)
    ]


@app.get("/api/stats")
async def rolling_stats(league: str, category: str, item_id: str, hours: float = 24):
    return await market_data.get_rolling_stats(league, category, item_id, hours)


@app.get("/api/market/overview")
async def market_overview(league: str):
    grouped = await market_data.get_all_latest(league)
    return {"league": league, "categories": grouped}


@app.get("/api/regimes")
async def get_regimes(league: str, category: str, hours: float = 24):
    """All regimes for a category, sorted by confidence."""
    return await regimes.detect_all_regimes(league, category, hours)


@app.get("/api/regime")
async def get_single_regime(league: str, category: str, item_id: str, hours: float = 24):
    """Single item regime classification."""
    return await regimes.detect_regime(league, category, item_id, hours)


@app.get("/api/anomalies")
async def get_anomalies(league: str, category: str, hours: float = 24):
    """Anomalies for a category."""
    return await anomalies.detect_anomalies(league, category, hours)


@app.get("/api/signals")
async def get_signals(league: str, hours: float = 24):
    """Market signals feed — combined regimes + anomalies."""
    return await signals.get_market_signals(league, hours)


@app.get("/api/opportunities")
async def get_opportunities(
    league: str,
    hours: float = 24,
    min_historical_ev: float = opportunity.MIN_HISTORICAL_EV,
    min_historical_confidence: float = opportunity.MIN_HISTORICAL_CONFIDENCE,
    min_liquidity: str = opportunity.MIN_LIQUIDITY_TIER,
    min_expected_return: float = opportunity.MIN_EXPECTED_RETURN,
):
    """Return only actionable, empirically supported opportunities."""
    try:
        opps = await opportunity.get_all_opportunities(league, hours)
        eligible, rejected = opportunity.filter_opportunities(
            opps, min_historical_ev, min_historical_confidence,
            min_liquidity, min_expected_return,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    thresholds = {
        "min_historical_ev": min_historical_ev,
        "min_historical_confidence": min_historical_confidence,
        "min_liquidity": min_liquidity,
        "min_expected_return": min_expected_return,
    }
    return {
        "opportunities": [opp.model_dump() for opp in eligible],
        "eligible_count": len(eligible),
        "rejected_count": sum(rejected.values()),
        "rejections": rejected,
        "thresholds": thresholds,
        "reason": None if eligible else (
            "No compelling opportunities met historical EV, Wilson confidence, "
            "liquidity, and execution thresholds."
        ),
    }

async def _resolve_chaos_per_divine(league: str) -> float | None:
    """Resolve the Divine rate through the shared market-data contract."""
    return await market_data.resolve_chaos_per_divine(league)
class CapitalPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    league: str
    bankroll: capital.Bankroll
    portfolio_id: int | None = None
    preferences: capital.InvestmentPreferences = Field(default_factory=capital.InvestmentPreferences)
    mode: capital.Mode = "PAPER"
    hours: float = 24
    seed: int = 0
    simulations: int = 2000


@app.post("/api/capital/plan", dependencies=[Depends(require_local_session)])
async def create_capital_plan(request: CapitalPlanRequest):
    """Return a conservative DEPLOY/WAIT plan from V1.1-filtered opportunities."""
    if request.hours <= 0 or request.simulations <= 0:
        raise HTTPException(status_code=400, detail="hours and simulations must be positive")
    try:
        calibration_records = [
            record for record in await portfolio.trade_records()
            if record.get("position_id", "__legacy__") is not None
            and record.get("confidence") is not None
            and record.get("profitable") is not None
            and ("realized_profit" not in record or record.get("realized_profit") is not None)
        ]
        if request.portfolio_id is not None:
            portfolio_id = _require_id(request.portfolio_id, "portfolio_id")
            status = await portfolio.paper_portfolio_status(portfolio_id)
            chaos_per_divine = await _resolve_chaos_per_divine(request.league)
            if chaos_per_divine is None:
                raise HTTPException(
                    status_code=400,
                    detail="current chaos-per-divine rate unavailable; cannot source bankroll from paper portfolio",
                )
            request.bankroll = capital.Bankroll(
                total_net_worth=status["equity"] / chaos_per_divine,
                liquid_currency=status["liquid"] / chaos_per_divine,
                currently_invested=status["deployed"] / chaos_per_divine,
                reserved_capital=0,
            )
        else:
            chaos_per_divine = await _resolve_chaos_per_divine(request.league)
        current = []
        if chaos_per_divine is None:
            candidates = []
        else:
            current = await opportunity.get_all_opportunities(
                request.league, request.hours, include_feedback=request.mode in {"PAPER", "AGGRESSIVE-PAPER"}
            )
            # Fixed V1.1 gates still decide allocatability. Rejected candidates
            # remain visible so an empty tier table cannot masquerade as no data.
            opportunity.filter_opportunities(
                current,
                opportunity.MIN_HISTORICAL_EV,
                opportunity.MIN_HISTORICAL_CONFIDENCE,
                opportunity.MIN_LIQUIDITY_TIER,
                opportunity.MIN_EXPECTED_RETURN,
            )
            candidates = [
                opportunity.normalize_opportunity(
                    item,
                    chaos_per_divine=chaos_per_divine,
                    paper_only=request.mode in {"PAPER", "AGGRESSIVE-PAPER"},
                )
                for item in current
            ]
            market = _latest_market_context(await market_data.get_all_latest(request.league))
            active_poe_patch = await resolve_active_poe_patch(request.league)
            provider = strategies.TransformationStrategyProvider(
                strategies.default_transformation_registry()
            )
            provider_context = {
                "league": request.league,
                "bankroll": request.bankroll.total_net_worth,
                **market,
                "chaos_per_divine": chaos_per_divine,
                "active_poe_patch": active_poe_patch,
                "budget_chaos": request.bankroll.total_net_worth * chaos_per_divine,
                "capacity_horizon_hours": float(request.hours),
            }
            candidates.extend(provider.discover(provider_context))
            candidates.extend(strategies.default_deferred_strategy_provider().discover(provider_context))
            div_registry = strategies.default_div_card_registry()
            if active_poe_patch == div_registry.poe_patch:
                candidates.extend(strategies.DivinationCardStrategyProvider(
                    div_registry
                ).discover(provider_context))
        plan = capital.build_capital_plan(
            request.bankroll,
            request.preferences,
            candidates,
            mode=request.mode,
            chaos_per_divine=chaos_per_divine,
            calibration_records=calibration_records,
        )
        if chaos_per_divine is None:
            plan.reason = "WAIT: current chaos-per-divine rate unavailable from Currency data; no capital was allocated."
        simulation = plan.simulation
        recommendation_id = await portfolio.append_recommendation({
            "bankroll": plan.bankroll.model_dump(),
            "positions": [position.model_dump() for position in plan.positions],
            "reserve": plan.reserve,
            "expected_profit": simulation.expected_profit,
            "expected_duration_hours": simulation.median_completion_hours,
            "expected_distribution": simulation.model_dump(),
            "league": request.league,
            "mode": plan.mode,
            "recommendation": plan.recommendation,
            "reason": plan.reason,
            "capital_currency": plan.capital_currency,
            "chaos_per_divine": plan.chaos_per_divine,
        })
        result = plan.model_dump()
        result["recommendation_id"] = recommendation_id
        result["requested_mode"] = request.mode
        result["mode_downgraded"] = plan.mode != request.mode
        paper_ideas = []
        if request.mode in {"PAPER", "AGGRESSIVE-PAPER"}:
            paper_ideas = await cx_queries.cx_paper_ideas(
                request.league, hours=max(3, int(request.hours)), limit=5,
            )
            if paper_ideas:
                mapping = await cx_metadata.ensure_currency_mapping()
                for idea in paper_ideas:
                    idea["item_name"] = cx_metadata.resolve_name(mapping, idea["item_id"])
        result["paper_ideas"] = paper_ideas
        result["evidence_warning"] = (
            f"Latest direct Currency Exchange snapshot: "
            f"{max(idea['snapshot_timestamp'] for idea in paper_ideas)} "
            f"({min(idea['data_age_hours'] for idea in paper_ideas):.1f}h old). "
            "Mean-reversion gap is not validated EV; confidence remains low until "
            "direct snapshot backtests clear the normal deployment gates."
            if paper_ideas else None
        )
        result["evidence_summary"] = {
            "reconstructed_opportunities": sum(
                int(item.historical_context.get("reconstructed_sample_size") or 0) > 0
                for item in current
            ),
            "observed_opportunities": sum(
                int((item.historical_context.get("evidence_sources") or {}).get("observed", 0)) > 0
                for item in current
            ),
            "paper_only_reconstructed_candidates": sum(
                bool(item.metadata and item.metadata.get("paper_only_reconstructed"))
                for item in candidates
            ),
            "source": (
                "poe.ninja sparkline prices are reconstructed from rounded relative "
                "changes at inferred daily timestamps; they are not direct observations"
            ),
        }
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/api/journal/recommendations")
async def journal_recommendations():
    return await portfolio.list_recommendations()


class PaperPortfolioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_bankroll: float = Field(ge=0, description="Divine bankroll supplied by the CFO")
    chaos_per_divine: float = Field(gt=0, description="Current plan conversion rate")
    name: str = Field(default="default", min_length=1)


@app.post("/api/paper/portfolios", dependencies=[Depends(require_local_session)])
async def create_paper_portfolio(request: PaperPortfolioRequest):
    try:
        portfolio_id = await portfolio.create_paper_portfolio(
            request.initial_bankroll, request.chaos_per_divine, request.name
        )
        return {"portfolio_id": portfolio_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_id(value: int, label: str) -> int:
    if value <= 0:
        raise HTTPException(status_code=400, detail=f"{label} must be positive")
    return value


@app.get("/api/paper/portfolios/{portfolio_id}/status")
async def paper_status(portfolio_id: int):
    try:
        return await portfolio.paper_portfolio_status(_require_id(portfolio_id, "portfolio_id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/paper/portfolios/{portfolio_id}/equity")
async def paper_equity(portfolio_id: int):
    try:
        return await portfolio.paper_equity_curve(_require_id(portfolio_id, "portfolio_id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/paper/portfolios/{portfolio_id}/trades")
async def paper_trades(portfolio_id: int):
    try:
        return await portfolio.trade_records(_require_id(portfolio_id, "portfolio_id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/paper/portfolios/{portfolio_id}/positions")
async def paper_positions(portfolio_id: int, status: str | None = None):
    try:
        return await portfolio.paper_positions(_require_id(portfolio_id, "portfolio_id"), status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/paper/portfolios/{portfolio_id}/performance")
async def paper_performance(portfolio_id: int):
    try:
        return await portfolio.paper_performance(_require_id(portfolio_id, "portfolio_id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PaperPositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    predicted_exit_price: float | None = Field(default=None, gt=0)
    predicted_duration_hours: float | None = Field(default=None, gt=0)
    predicted_profit: float | None = None
    recommendation_id: int | None = Field(default=None, gt=0)
    opened_at: str | None = None


@app.post("/api/paper/portfolios/{portfolio_id}/positions", dependencies=[Depends(require_local_session)])
async def open_paper_position(portfolio_id: int, request: PaperPositionRequest):
    try:
        position_id = await portfolio.open_paper_position(
            _require_id(portfolio_id, "portfolio_id"),
            request.opportunity_id,
            request.quantity,
            request.entry_price,
            request.predicted_exit_price,
            request.predicted_duration_hours,
            request.predicted_profit,
            request.recommendation_id,
            request.opened_at,
        )
        return {"position_id": position_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PaperRealizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_price: float = Field(gt=0)
    realized_at: str | None = None
    actual_entry_at: str | None = None
    actual_duration_hours: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    actual_entry_price: float | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, gt=0)


@app.post("/api/paper/positions/{position_id}/realize", dependencies=[Depends(require_local_session)])
async def realize_paper_position(position_id: int, request: PaperRealizeRequest):
    try:
        return await portfolio.realize_paper_position(
            _require_id(position_id, "position_id"),
            request.exit_price,
            request.realized_at,
            request.confidence,
            request.actual_entry_at,
            request.actual_duration_hours,
            request.actual_entry_price,
            request.quantity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

class LinkedTradeCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: float = Field(gt=0)
    actual_entry_price: float = Field(gt=0)
    actual_exit_price: float = Field(gt=0)
    actual_duration_hours: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


@app.patch("/api/paper/trades/{trade_id}", dependencies=[Depends(require_local_session)])
async def correct_linked_trade(trade_id: int, request: LinkedTradeCorrectionRequest):
    try:
        return await portfolio.correct_linked_trade(
            _require_id(trade_id, "trade_id"), **request.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/api/paper/trades/real")
async def manual_real_trades(opportunity_id: str | None = None):
    try:
        return await portfolio.manual_trade_records(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
class RealTradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    predicted_entry_price: float = Field(gt=0)
    actual_entry_price: float = Field(gt=0)
    predicted_exit_price: float = Field(gt=0)
    actual_exit_price: float = Field(gt=0)
    predicted_duration_hours: float = Field(ge=0)
    actual_duration_hours: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    recorded_at: str | None = None
    chaos_per_divine: float = Field(gt=0)


@app.post("/api/paper/trades/real", dependencies=[Depends(require_local_session)])
async def record_real_trade(request: RealTradeRequest):
    try:
        return await portfolio.record_real_trade(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.get("/api/strategies/transformations")
async def list_transformations():
    registry = strategies.default_transformation_registry()
    return {
        "transformations": list(registry.records()),
        "lifecycle": [lifecycle.value for lifecycle in strategies.StrategyLifecycle],
    }

@app.get("/api/strategies/divination-cards")
async def list_divination_cards():
    registry = strategies.default_div_card_registry()
    return {
        "version": registry.version,
        "source": registry.source,
        "poe_patch": registry.poe_patch,
        "verified_leagues": sorted(registry.verified_leagues),
        "recipes": list(registry.records()),
    }

def _latest_market_context(latest: dict) -> dict:
    prices: dict[str, dict] = {}
    price_records: dict[str, dict] = {}
    execution_prices: dict[str, dict] = {}
    for market_category, rows in latest.items():
        for row in rows:
            item_id = str(row.get("item_id") or "")
            item_name = str(row.get("item_name") or item_id)
            for item in {item_id, item_name} - {""}:
                key = f"{market_category}:{item}"
                prices[key] = row
                price_records[key] = row
                prices.setdefault(item, row)
                price_records.setdefault(item, row)
            quote = row.get("execution_quote")
            if isinstance(quote, str):
                try:
                    quote = json.loads(quote)
                except (TypeError, ValueError):
                    quote = None
            if not isinstance(quote, dict) and (row.get("buy_levels") is not None or row.get("sell_levels") is not None):
                quote = {
                    "buy_levels": row.get("buy_levels"),
                    "sell_levels": row.get("sell_levels"),
                    "buy_fee_rate": row.get("buy_fee_rate", row.get("fee_rate", 0)),
                    "sell_fee_rate": row.get("sell_fee_rate", row.get("fee_rate", 0)),
                    "observed_at": row.get("observed_at"),
                    "stale": bool(row.get("stale", False)),
                    "confidence": row.get("confidence"),
                    "source": row.get("source"),
                }
            if isinstance(quote, dict):
                for item in {item_id, item_name} - {""}:
                    execution_prices[f"{market_category}:{item}"] = quote
    divine = prices.get("Currency:Divine")
    chaos = prices.get("Currency:Chaos")
    chaos_per_divine = 0.0
    if divine and chaos:
        divine_price = divine.get("price_chaos")
        chaos_price = chaos.get("price_chaos")
        if divine_price and chaos_price and chaos_price > 0:
            chaos_per_divine = divine_price / chaos_price
    return {
        "prices": prices,
        "price_records": price_records,
        "execution_prices": execution_prices,
        "chaos_per_divine": chaos_per_divine,
    }


async def resolve_active_poe_patch(league: str) -> str | None:
    """Resolve an operator override or the checked-in patch for a verified league."""
    raw = os.getenv("DEUSCFO_ACTIVE_POE_PATCH", "").strip()
    if raw:
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(mapping, dict):
            value = mapping.get(league) or mapping.get("*")
            return str(value).strip() if value else None
        return str(mapping).strip() if mapping else None
    registry = strategies.default_div_card_registry()
    return registry.poe_patch if league in registry.verified_leagues else None


@app.get("/api/profit-routes")
async def get_profit_routes(
    league: str,
    category: str | None = None,
    poe_patch: str | None = None,
):
    """Evaluate routes using explicit active PoE patch metadata.

    ``poe_patch`` is retained only for response compatibility; callers cannot
    override the active metadata used for verification.
    """
    if category and category not in ALL_CATEGORIES and category not in {"Transformation", "Assembly", "VendorTransformation", "ArbitrageGraph", "SixLink"}:
        raise HTTPException(status_code=400, detail=f"unknown category: {category}")
    active_poe_patch = await resolve_active_poe_patch(league)
    market = _latest_market_context(await market_data.get_all_latest(league))
    context = {"league": league, "category": category, "active_poe_patch": active_poe_patch, **market}
    routes = list(strategies.TransformationStrategyProvider(
        strategies.default_transformation_registry()
    ).evaluate(context))
    routes.extend(strategies.default_deferred_strategy_provider().evaluate(context))
    div_registry = strategies.default_div_card_registry() if category in (None, "DivinationCard") else None
    if not active_poe_patch:
        patch_reasons = ["active PoE patch metadata is unknown; divination-card recipes are withheld"]
    elif div_registry is not None and active_poe_patch != div_registry.poe_patch:
        patch_reasons = [
            f"active PoE patch {active_poe_patch} does not match recipe patch {div_registry.poe_patch}; "
            "divination-card recipes are withheld"
        ]
    else:
        patch_reasons = ["active PoE patch metadata resolved"]
    if not active_poe_patch:
        patch_status = "unknown"
    elif div_registry is not None and active_poe_patch != div_registry.poe_patch:
        patch_status = "mismatch"
    else:
        patch_status = "resolved"
    if div_registry is not None and active_poe_patch == div_registry.poe_patch:
        routes.extend(strategies.DivinationCardStrategyProvider(
            div_registry
        ).evaluate(context))
    return {
        "league": league,
        "category": category,
        "poe_patch": active_poe_patch,
        "patch_status": patch_status,
        "patch_reasons": patch_reasons,
        "routes": [route.model_dump() for route in sorted(
            routes,
            key=lambda route: (
                route.status != "executable",
                -(route.expected_net_profit if route.expected_net_profit > 0 else 0),
                route.name,
            ),
        )],
    }


class TransformationEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prices: dict[str, float] = Field(min_length=1)
    bankroll: float = Field(ge=0)

    @field_validator("prices")
    @classmethod
    def positive_prices(cls, value):
        if any(price <= 0 for price in value.values()):
            raise ValueError("prices must be positive")
        return value


@app.post("/api/strategies/transformations/evaluate", dependencies=[Depends(require_local_session)])
async def evaluate_transformations(request: TransformationEvaluateRequest):
    try:
        provider = strategies.TransformationStrategyProvider(
            strategies.default_transformation_registry()
        )
        opportunities = provider.discover({
            "prices": request.prices,
            "bankroll": request.bankroll,
        })
        return {
            "mode": "OBSERVE",
            "auto_execution": False,
            "opportunities": [item.model_dump() for item in opportunities],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ReallocationCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_remaining_return: float
    new_return: float
    exit_cost: float = Field(default=0, ge=0)
    entry_cost: float = Field(default=0, ge=0)
    minimum_advantage: float = Field(default=0, ge=0)


@app.post("/api/reallocation/check", dependencies=[Depends(require_local_session)])
async def check_reallocation(request: ReallocationCheckRequest):
    try:
        decision = portfolio.should_reallocate(
            request.current_remaining_return,
            request.new_return,
            request.exit_cost,
            request.entry_cost,
            request.minimum_advantage,
        )
        return {
            "should_reallocate": decision.should_reallocate,
            "net_advantage": decision.net_advantage,
            "reason": decision.reason,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/opportunity/types")
async def get_opportunity_types():
    """Available opportunity types and their detector IDs."""
    return opportunity.OPPORTUNITY_TYPES


@app.get("/api/market/events")
async def get_market_events(
    league: str,
    category: str | None = None,
    price_threshold_pct: float = 5.0,
    volume_threshold_pct: float = 100.0,
    min_items: int = 3,
    min_coverage: float = 0.6,
):
    """Detect synchronized category/cross-category events from stored history."""
    if category and category not in ALL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")
    if price_threshold_pct <= 0 or volume_threshold_pct <= 0 or min_items <= 0:
        raise HTTPException(status_code=400, detail="detector thresholds must be positive")
    if not 0 < min_coverage <= 1:
        raise HTTPException(status_code=400, detail="min_coverage must be in (0, 1]")
    events = await market_relationships.detect_market_events_from_db(
        league,
        category,
        price_threshold_pct=price_threshold_pct,
        volume_threshold_pct=volume_threshold_pct,
        min_items=min_items,
        min_coverage=min_coverage,
    )
    return {
        "league": league,
        "category": category,
        "thresholds": {
            "price_threshold_pct": price_threshold_pct,
            "volume_threshold_pct": volume_threshold_pct,
            "min_items": min_items,
            "min_coverage": min_coverage,
        },
        "status": "ok" if events else "no_events",
        "events": [event.as_dict() for event in events],
        "reason": None if events else "No synchronized market movements met the configured thresholds.",
    }


@app.get("/api/market/relationship")
async def get_market_relationship(
    league: str,
    leader: str,
    laggard: str,
    lag_hours: float = 1.0,
    min_samples: int = market_relationships.MIN_RELATIONSHIP_SAMPLES,
    min_train_samples: int = market_relationships.MIN_TRAIN_SAMPLES,
    min_out_of_sample_samples: int = market_relationships.MIN_OUT_OF_SAMPLE_SAMPLES,
):
    """Investigate one explicitly supplied leader/laggard pair only."""
    if not leader.strip() or not laggard.strip():
        raise HTTPException(status_code=400, detail="leader and laggard are required")
    if leader == laggard:
        raise HTTPException(status_code=400, detail="leader and laggard must differ")
    if lag_hours <= 0 or min_samples <= 0 or min_train_samples <= 0 or min_out_of_sample_samples <= 0:
        raise HTTPException(status_code=400, detail="relationship thresholds must be positive")
    result = await market_relationships.investigate_lagged_relationship_from_db(
        league,
        leader,
        laggard,
        lag_hours,
        min_samples=min_samples,
        min_train_samples=min_train_samples,
        min_out_of_sample_samples=min_out_of_sample_samples,
    )
    result["league"] = league
    result.setdefault(
        "evidence_thresholds",
        {
            "minimum_sample_size": min_samples,
            "minimum_train_samples": min_train_samples,
            "minimum_out_of_sample_samples": min_out_of_sample_samples,
        },
    )
    return result


@app.get("/api/backtest")
async def historical_backtest(
    league: str,
    category: str | None = None,
    horizons: str = "1,3,6,12,24",
    horizon: float | None = None,
    signal_window_hours: float = 24,
):
    """Look-ahead-safe performance grouped by detector and market context."""
    if category and category not in ALL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")
    try:
        return await validation.backtest(
            league, category, horizons=(horizon,) if horizon is not None else horizons,
            signal_window_hours=signal_window_hours
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




class NumericCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lt: float | None = None
    lte: float | None = None
    gt: float | None = None
    gte: float | None = None
    eq: float | None = None


class StrategyConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_percentile: NumericCondition | None = None
    volume_ratio: NumericCondition | None = None
    regime: str | None = None


class StrategyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    league: str
    category: str | None = None
    conditions: StrategyConditions
    horizons: list[float] = [6]
    signal_window_hours: float = 24


@app.post("/api/strategy/backtest", dependencies=[Depends(require_local_session)])
async def strategy_backtest(request: StrategyRequest):
    """Evaluate only the supported declarative strategy condition fields."""
    if request.category and request.category not in ALL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{request.category}'")
    try:
        return await validation.strategy_backtest(
            request.league,
            request.conditions.model_dump(exclude_none=True),
            request.category,
            request.horizons,
            request.signal_window_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
@app.get("/api/performance")
async def historical_performance(
    league: str,
    category: str | None = None,
    signal_type: str | None = None,
    anomaly_type: str | None = None,
    regime: str | None = None,
    liquidity_tier: str | None = None,
    opportunity_type: str | None = None,
    horizons: str = "1,3,6,12,24",
    horizon: float | None = None,
    signal_window_hours: float = 24,
):
    """Concise filtered view over historical backtest groups."""
    if category and category not in ALL_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'")
    try:
        return await validation.performance(
            league,
            category=category,
            signal_type=signal_type,
            anomaly_type=anomaly_type,
            regime=regime,
            liquidity_tier=liquidity_tier,
            opportunity_type=opportunity_type,
            horizons=(horizon,) if horizon is not None else horizons,
            signal_window_hours=signal_window_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CxBackfillRequest(BaseModel):
    max_hours: int | None = None


@app.post("/api/cx/backfill", dependencies=[Depends(require_local_session)])
async def cx_backfill(request: CxBackfillRequest):
    """Backfill currency-exchange history from saved progress (or oldest)."""
    max_hours = request.max_hours or 168
    hours = await cx_collector.backfill_currency_exchange(max_hours=max_hours)
    return {"hours_processed": hours}


@app.post("/api/cx/poll", dependencies=[Depends(require_local_session)])
async def cx_poll():
    """Poll for the latest currency-exchange hour."""
    stored = await cx_collector.poll_latest_cx()
    return {"entries_stored": stored}


@app.get("/api/cx/status")
async def cx_status():
    return await cx_queries.cx_status()


@app.get("/api/cx/history")
async def cx_history(league: str, item_id: str, hours: int = 24, ref: str = "auto"):
    """Exchange history for a currency (metadata ID or short ID).

    Returns one row per hour: the item's ratio vs a reference currency
    (chaos by default, divine for chaos itself, or explicit: ref=chaos|divine).
    """
    mapping = await cx_metadata.ensure_currency_mapping()
    stored_ids = await cx_queries.cx_item_ids(league)
    candidates = cx_metadata.resolve_query_ids(mapping, stored_ids, item_id)

    CHAOS = "Metadata/Items/Currency/CurrencyRerollRare"
    DIVINE = "Metadata/Items/Currency/CurrencyModValues"
    if ref == "chaos":
        ref_meta = CHAOS
    elif ref == "divine":
        ref_meta = DIVINE
    else:  # auto: divine for chaos, chaos for everything else
        ref_meta = DIVINE if item_id.lower() == "chaos" else CHAOS

    rows = await cx_queries.cx_history_for(league, list(candidates), hours)
    by_hour = {}
    for r in rows:
        if r["item_a"] in candidates:
            mine, other = r["item_a"], r["item_b"]
            side = "a"
        else:
            mine, other = r["item_b"], r["item_a"]
            side = "b"
        can_be_ref = other == ref_meta  # this row prices the item vs the ref
        price = r[f"lowest_ratio_{side}"]
        ref_name = "chaos" if other == CHAOS else ("divine" if other == DIVINE else "other")
        # prefer explicit ref rows; otherwise keep the highest-volume pair for the hour
        hour = r["timestamp"]
        cur = by_hour.get(hour)
        if cur is None or can_be_ref or (not cur["was_ref"] and cur["volume"] < r[f"volume_{side}"]):
            by_hour[hour] = {
                "timestamp": hour, "league": r["league"], "item_id": mine,
                "item_name": cx_metadata.resolve_name(mapping, mine),
                "price": price, "ratio_low": price, "ratio_high": r[f"highest_ratio_{side}"],
                "volume": r[f"volume_{side}"], "ref": ref_name, "was_ref": can_be_ref,
            }
    result = [
        {k: v for k, v in entry.items() if k != "was_ref"}
        for entry in sorted(by_hour.values(), key=lambda x: x["timestamp"])
    ]
    return result


@app.get("/api/coverage")
async def data_coverage(league: str):
    """Data coverage for all sources/categories for a league."""
    return await coverage.all_coverage(league)


@app.get("/api/coverage/trust")
async def coverage_trust(
    league: str,
    category: str,
    hours: float = 24,
    min_coverage: float = 0.6,
    source: str = "snapshot",
):
    """Trust gate: can we backtest this window?"""
    return await coverage.can_trust_window(league, category, hours, min_coverage, source)


@app.get("/api/coverage/{category}")
async def data_coverage_category(league: str, category: str):
    """Data coverage for a single snapshot category (use 'Currency%20Exchange' for CX)."""
    if category == "Currency Exchange":
        return await coverage.cx_coverage(league)
    return await coverage.snapshot_coverage(league, category)

FRONTEND_ASSETS = StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False)
app.mount("/assets", FRONTEND_ASSETS, name="frontend-assets")


@app.get("/{path:path}", include_in_schema=False)
async def frontend_app(path: str):
    """Serve the packaged app shell; StaticFiles handles built assets safely."""
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="frontend build is unavailable")
