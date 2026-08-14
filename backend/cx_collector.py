"""Currency Exchange API collector.

Fetches hourly currency-exchange history from the public CDN endpoint
https://web.poecdn.com/api/currency-exchange/{id} and stores it in
cx_history, tracking pagination progress in cx_progress.
"""

import asyncio
import datetime
import logging

import httpx

import database

log = logging.getLogger("deuscfo.cx")

CX_BASE = "https://web.poecdn.com/api/currency-exchange"
POE_NINJA_LEAGUES = "https://poe.ninja/poe1/api/economy/leagues"
REQUEST_DELAY = 0.5  # seconds between CDN fetches


def _resolve_league(league: str, wanted_leagues: set[str]) -> str | None:
    """Map a CX league name onto a poe.ninja league (case-insensitive).

    CX reports real league display names (e.g. 'Hardcore Allflame'),
    poe.ninja ids are the same strings.  Returns None for private leagues.
    """
    for w in wanted_leagues:
        if league.lower() == w.lower():
            return w
    return None


async def _fetch_leagues() -> set[str]:
    """poe.ninja league ids we care about (cache for the process lifetime)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(POE_NINJA_LEAGUES)
            if resp.status_code == 200:
                return {l["id"] for l in resp.json() if "id" in l}
    except Exception:
        log.exception("could not fetch poe.ninja leagues")
    # Fallback: the perma/void league names we want even if poe.ninja hiccups
    return {"Standard", "Hardcore", "Allflame", "Hardcore Allflame",
            "Ruthless Allflame", "HC Ruthless Allflame", "Ruthless"}


async def fetch_currency_exchange(change_id: int | None = None) -> dict:
    """Fetch one hour of currency-exchange data."""
    url = CX_BASE if change_id is None else f"{CX_BASE}/{change_id}"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _parse_hour(data: dict, wanted_leagues: set[str]) -> tuple[str, list[dict]]:
    """Turn a raw API response into (iso_timestamp, filtered market records)."""
    ncid = data.get("next_change_id")
    ts = datetime.datetime.fromtimestamp(ncid, datetime.timezone.utc).isoformat(timespec="seconds") if ncid else ""
    records = []
    for m in data.get("markets", []):
        league = _resolve_league(m.get("league", ""), wanted_leagues)
        if league is None:
            continue
        market_id = m.get("market_id", "")
        pair = m.get("market_pair", [])
        if len(pair) != 2:
            continue
        a, b = pair
        v = m.get("volume_traded", {})
        lo = m.get("lowest_stock", {})
        hi = m.get("highest_stock", {})
        lr = m.get("lowest_ratio", {})
        hr = m.get("highest_ratio", {})
        records.append({
            "league": league, "market_id": market_id, "item_a": a, "item_b": b,
            "volume_a": v.get(a), "volume_b": v.get(b),
            "lowest_stock_a": lo.get(a), "lowest_stock_b": lo.get(b),
            "highest_stock_a": hi.get(a), "highest_stock_b": hi.get(b),
            "lowest_ratio_a": lr.get(a), "lowest_ratio_b": lr.get(b),
            "highest_ratio_a": hr.get(a), "highest_ratio_b": hr.get(b),
        })
    return ts, records


async def store_cx_hour(data: dict, wanted_leagues: set[str]) -> int:
    """Parse a response and store its (filtered) markets. Returns entries stored."""
    ts, records = _parse_hour(data, wanted_leagues)
    return await database.insert_cx_hour(records, ts)


async def backfill_currency_exchange(max_hours: int = 168) -> int:
    """Follow the change_id chain from saved progress (or the beginning).

    Returns the number of hours processed.
    """
    wanted = await _fetch_leagues()
    last = await database.get_cx_progress("default")
    change_id = last
    hours = 0
    while hours < max_hours:
        try:
            data = await fetch_currency_exchange(change_id)
        except Exception:
            log.exception("cx backfill: fetch failed at change_id=%s", change_id)
            break
        ncid = data.get("next_change_id")
        if ncid is None:
            log.error("cx backfill: no next_change_id in response")
            break
        if change_id is not None and ncid == change_id:
            log.info("cx backfill: reached current hour at %s", ncid)
            break
        ts, records = _parse_hour(data, wanted)
        stored = await database.insert_cx_hour(records, ts) if records else 0
        if stored != len(records):
            log.error(
                "cx backfill: storage paused at %s; retained progress %s for retry",
                ts, change_id,
            )
            break
        await database.set_cx_progress("default", ncid)
        log.info("cx backfill: stored %d entries for hour %s (next=%s)", stored, ts, ncid)
        change_id = ncid
        hours += 1
        await asyncio.sleep(REQUEST_DELAY)
    log.info("cx backfill: done, %d hours processed", hours)
    return hours


async def poll_latest_cx() -> int:
    """Fetch the latest hour and store it. Returns entries stored (0 if up to date)."""
    wanted = await _fetch_leagues()
    last = await database.get_cx_progress("default")
    try:
        data = await fetch_currency_exchange(last)
    except Exception:
        log.exception("cx poll: fetch failed")
        return 0
    ncid = data.get("next_change_id")
    if ncid is None:
        log.error("cx poll: no next_change_id in response")
        return 0
    if last is not None and ncid == last:
        log.info("cx poll: already up to date at %s", ncid)
        return 0
    ts, records = _parse_hour(data, wanted)
    stored = await database.insert_cx_hour(records, ts) if records else 0
    if stored != len(records):
        log.error("cx poll: storage paused at %s; progress retained for retry", ts)
        return 0
    await database.set_cx_progress("default", ncid)
    log.info("cx poll: stored %d entries for hour %s", stored, ts)
    return stored
