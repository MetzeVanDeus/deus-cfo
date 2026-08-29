"""Currency Exchange API collector.

Fetches hourly currency-exchange history from the public CDN endpoint
https://web.poecdn.com/api/currency-exchange/{id} and stores it in
cx_history, tracking pagination progress in cx_progress.
"""

import asyncio
import datetime
import math
import logging

import httpx


import database

log = logging.getLogger("deuscfo.cx")

CX_BASE = "https://web.poecdn.com/api/currency-exchange"
POE_NINJA_LEAGUES = "https://poe.ninja/poe1/api/economy/leagues"
REQUEST_DELAY = 0.5  # seconds between CDN fetches
_BACKFILL_DEFAULT_HOURS = 168
_backfill_task: asyncio.Task[int] | None = None
_backfill_status = "idle"
_backfill_hours_requested = 0
_backfill_hours_processed = 0
_backfill_lock = asyncio.Lock()
_last_backfill_error = False


def _hour_cursor(hours_ago: int = 0) -> int:
    """Return an exact UTC-hour cursor accepted by the CDN."""
    current = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    return current - current % 3600 - hours_ago * 3600


def _resolve_league(league: str, wanted_leagues: set[str]) -> str | None:
    """Map a CX league name onto a poe.ninja league (case-insensitive)."""
    if not isinstance(league, str):
        return None
    for wanted in wanted_leagues:
        if isinstance(wanted, str) and league.casefold() == wanted.casefold():
            return wanted
    return None


def _valid_change_id(data: object) -> int | None:
    if not isinstance(data, dict):
        return None
    value = data.get("next_change_id")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _market_number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def _market_map(value) -> dict:
    return value if isinstance(value, dict) else {}


async def _fetch_leagues() -> set[str]:
    """Return currently published poe.ninja league ids, or none on failure."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(POE_NINJA_LEAGUES)
            if resp.status_code == 200:
                return {
                    league["id"] for league in resp.json()
                    if isinstance(league, dict) and isinstance(league.get("id"), str)
                }
    except Exception:
        log.exception("could not fetch poe.ninja leagues")
    return set()


async def fetch_currency_exchange(change_id: int | None = None) -> dict:
    """Fetch one hour of currency-exchange data."""
    url = CX_BASE if change_id is None else f"{CX_BASE}/{change_id}"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if attempt == 2:
                raise
            log.warning("cx fetch: transient connection failure; retrying %s", url)
            await asyncio.sleep(REQUEST_DELAY)


def _parse_hour(data: dict, wanted_leagues: set[str]) -> tuple[str, list[dict]]:
    """Turn a valid raw API response into (iso_timestamp, filtered markets)."""
    ncid = _valid_change_id(data)
    markets = data.get("markets") if isinstance(data, dict) else None
    if ncid is None or not isinstance(markets, list):
        return "", []
    ts = datetime.datetime.fromtimestamp(ncid, datetime.timezone.utc).isoformat(timespec="seconds")
    records = []
    for market in markets:
        if not isinstance(market, dict):
            continue
        league = _resolve_league(market.get("league"), wanted_leagues)
        if league is None:
            continue
        market_id = market.get("market_id")
        pair = market.get("market_pair")
        if (
            not isinstance(market_id, str)
            or not market_id
            or not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(item, str) and item for item in pair)
        ):
            continue
        a, b = pair
        volume = _market_map(market.get("volume_traded"))
        lowest_stock = _market_map(market.get("lowest_stock"))
        highest_stock = _market_map(market.get("highest_stock"))
        lowest_ratio = _market_map(market.get("lowest_ratio"))
        highest_ratio = _market_map(market.get("highest_ratio"))
        records.append({
            "league": league, "market_id": market_id, "item_a": a, "item_b": b,
            "volume_a": _market_number(volume.get(a)), "volume_b": _market_number(volume.get(b)),
            "lowest_stock_a": _market_number(lowest_stock.get(a)),
            "lowest_stock_b": _market_number(lowest_stock.get(b)),
            "highest_stock_a": _market_number(highest_stock.get(a)),
            "highest_stock_b": _market_number(highest_stock.get(b)),
            "lowest_ratio_a": _market_number(lowest_ratio.get(a)),
            "lowest_ratio_b": _market_number(lowest_ratio.get(b)),
            "highest_ratio_a": _market_number(highest_ratio.get(a)),
            "highest_ratio_b": _market_number(highest_ratio.get(b)),
            "realm": "poe1", "source": "ggg_currency_exchange",
            "observation_type": "OFFICIAL_HISTORICAL", "market_timestamp": ts,
            "confidence_grade": "A",
        })
    return ts, records

def _wanted_league_present(data: dict, wanted_leagues: set[str]) -> bool:
    markets = data.get("markets") if isinstance(data, dict) else None
    return isinstance(markets, list) and any(
        isinstance(market, dict) and _resolve_league(market.get("league"), wanted_leagues) is not None
        for market in markets
    )


async def store_cx_hour(data: dict, wanted_leagues: set[str]) -> int:
    """Parse a response and store its (filtered) markets. Returns entries stored."""
    ts, records = _parse_hour(data, wanted_leagues)
    return await database.insert_cx_hour(records, ts)


async def backfill_currency_exchange(max_hours: int = _BACKFILL_DEFAULT_HOURS) -> int:
    """Fetch the requested window, resuming from the saved cursor when present."""
    global _last_backfill_error
    _last_backfill_error = False
    wanted = await _fetch_leagues()
    if not wanted:
        _last_backfill_error = True
        log.warning("cx backfill: no current leagues available; refusing to advance cursor")
        return 0
    try:
        last = await database.get_cx_progress("default")
    except Exception:
        _last_backfill_error = True
        log.exception("cx backfill: progress read failed")
        return 0
    change_id = last if last is not None else _hour_cursor(max_hours)
    if last is not None and last >= _hour_cursor():
        log.info("cx backfill: already up to date at %s", last)
        return 0
    first_change_id = None
    first_hour = None
    hours = 0
    while hours < max_hours:
        try:
            data = await fetch_currency_exchange(change_id)
        except Exception:
            _last_backfill_error = True
            log.exception("cx backfill: fetch failed at change_id=%s", change_id)
            break
        ncid = _valid_change_id(data)
        if ncid is None:
            _last_backfill_error = True
            log.error("cx backfill: malformed response at change_id=%s", change_id)
            break
        if change_id is not None and ncid == change_id:
            log.info("cx backfill: reached current hour at %s", ncid)
            break
        try:
            ts, records = _parse_hour(data, wanted)
            if not ts:
                _last_backfill_error = True
                log.error("cx backfill: malformed hour at change_id=%s", change_id)
                break
            if not _wanted_league_present(data, wanted) or not records:
                log.warning("cx backfill: wanted league payload had no valid records at %s; retrying later", ncid)
                break
            stored = await database.insert_cx_hour(records, ts) if records else 0
            if last is None and first_change_id is None:
                first_change_id = ncid
                first_hour = ts
            await database.set_cx_progress(
                "default", ncid,
                first_change_id=first_change_id if last is None else None,
                first_available_hour=first_hour if last is None else None,
                last_synced_hour=ts,
            )
        except Exception:
            _last_backfill_error = True
            log.exception("cx backfill: store failed at change_id=%s", ncid)
            break
        log.info("cx backfill: stored %d entries for hour %s (next=%s)", stored, ts, ncid)
        change_id = ncid
        hours += 1
        if change_id >= _hour_cursor():
            log.info("cx backfill: reached current hour at %s", change_id)
            break
        await asyncio.sleep(REQUEST_DELAY)
    log.info("cx backfill: done, %d hours processed", hours)
    return hours

async def _run_backfill(max_hours: int) -> int:
    global _backfill_status, _backfill_hours_processed, _last_backfill_error
    _last_backfill_error = False
    try:
        processed = await backfill_currency_exchange(max_hours=max_hours)
    except asyncio.CancelledError:
        _backfill_status = "idle"
        raise
    except Exception:
        log.exception("cx backfill: worker failed")
        _backfill_status = "failed"
        return 0
    _backfill_hours_processed = processed
    _backfill_status = "failed" if _last_backfill_error else "completed"
    return processed




async def start_backfill(max_hours: int = _BACKFILL_DEFAULT_HOURS) -> dict[str, int | str]:
    """Start one background backfill, or report the existing worker."""
    global _backfill_task, _backfill_status, _backfill_hours_requested, _backfill_hours_processed
    async with _backfill_lock:
        if _backfill_task is not None and not _backfill_task.done():
            return {
                "status": "in_progress",
                "hours_requested": _backfill_hours_requested,
                "hours_processed": _backfill_hours_processed,
            }
        _backfill_status = "running"
        _backfill_hours_requested = max_hours
        _backfill_hours_processed = 0
        _backfill_task = asyncio.create_task(_run_backfill(max_hours))
        return {"status": "started", "hours_requested": max_hours, "hours_processed": 0}


def backfill_status() -> dict[str, int | str]:
    """Return the process-local background backfill state."""
    return {
        "backfill_status": _backfill_status,
        "backfill_hours_requested": _backfill_hours_requested,
        "backfill_hours_processed": _backfill_hours_processed,
    }


async def poll_latest_cx() -> int:
    """Fetch the latest completed currency-exchange hour."""
    wanted = await _fetch_leagues()
    if not wanted:
        log.warning("cx poll: no current leagues available; refusing to advance cursor")
        return 0
    try:
        last = await database.get_cx_progress("default")
    except Exception:
        log.exception("cx poll: progress read failed")
        return 0
    current_hour = _hour_cursor()
    if last is not None and last >= current_hour:
        log.info("cx poll: already up to date at %s", last)
        return 0
    change_id = last if last is not None else current_hour - 3600
    try:
        data = await fetch_currency_exchange(change_id)
    except Exception:
        log.exception("cx poll: fetch failed")
        return 0
    ncid = _valid_change_id(data)
    if ncid is None:
        log.error("cx poll: malformed response")
        return 0
    if ncid == change_id:
        log.info("cx poll: already up to date at %s", ncid)
        return 0
    try:
        ts, records = _parse_hour(data, wanted)
        if not ts:
            log.error("cx poll: malformed hour")
            return 0
        if not _wanted_league_present(data, wanted) or not records:
            log.warning("cx poll: wanted league payload had no valid records at %s; retrying later", ncid)
            return 0
        stored = await database.insert_cx_hour(records, ts) if records else 0
        await database.set_cx_progress("default", ncid, last_synced_hour=ts)
    except Exception:
        log.exception("cx poll: store failed at change_id=%s", ncid)
        return 0
    log.info("cx poll: stored %d entries for hour %s", stored, ts)
    return stored
