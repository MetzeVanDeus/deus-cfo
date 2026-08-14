"""Periodic snapshot collection from poe.ninja into SQLite."""

import argparse
import asyncio
import logging
import os

import httpx

import cx_collector
import database

log = logging.getLogger("deuscfo.collector")

POE_NINJA_BASE = "https://poe.ninja"
EXCHANGE_URL = f"{POE_NINJA_BASE}/poe1/api/economy/exchange/current/overview"
STASH_URL = f"{POE_NINJA_BASE}/poe1/api/economy/stash/current/item/overview"

# poe.ninja 'type' param per category (same mapping as main.py)
_EXCHANGE_TYPES = {
    category: category
    for category in (
        "Currency", "Fragment", "Scarab", "Essence", "Oil", "Fossil",
        "DeliriumOrb", "DivinationCard",
    )
}
_STASH_TYPES = {
    category: category
    for category in (
        "SkillGem", "UniqueWeapon", "UniqueArmour", "UniqueAccessory",
        "UniqueJewel", "UniqueFlask", "Map", "BlightedMap", "UniqueMap",
    )
}
PERSISTED_CATEGORIES = frozenset(_EXCHANGE_TYPES)


def _format_slug(slug: str) -> str:
    """Turn 'abyss-scarab-of-descending' into 'Abyss Scarab of Descending'."""
    parts = slug.replace("_", "-").split("-")
    small = {"of", "the", "a", "an", "and", "or", "in", "on", "to", "for"}
    return " ".join(
        w.lower() if (w.lower() in small and i > 0) else w.capitalize()
        for i, w in enumerate(parts)
    )


def stash_item_id(line: dict) -> str:
    """Return poe.ninja's stable stash identity, including variant details."""
    return str(line.get("detailsId") or line.get("id", ""))


def _normalize(line: dict, league: str, category: str, is_exchange: bool) -> dict:
    """Map a poe.ninja line into a DIRECT_OBSERVATION snapshot record."""
    if is_exchange:
        item_id = line.get("id", "")
        return {
            "league": league,
            "category": category,
            "item_id": item_id,
            "item_name": _format_slug(item_id),
            "variant": "",
            "price_chaos": line.get("primaryValue", 0) or 0,
            "volume": line.get("volumePrimaryValue", 0) or 0,
            "listing_count": 0,
            "icon": "",
            "source": "poe.ninja",
            "observation_type": "DIRECT_OBSERVATION",
            "confidence_grade": "B",
        }
    return {
        "league": league,
        "category": category,
        "item_id": stash_item_id(line),
        "item_name": line.get("name", "Unknown"),
        "variant": line.get("variant", "") or "",
        "price_chaos": line.get("chaosValue", 0) or 0,
        "volume": line.get("listingCount", 0) or line.get("count", 0) or 0,
        "listing_count": line.get("listingCount", 0) or 0,
        "icon": line.get("icon", "") or "",
        "source": "poe.ninja",
        "observation_type": "DIRECT_OBSERVATION",
        "confidence_grade": "B",
    }



async def _collect_normalized(league: str, category: str) -> list[dict]:
    """Fetch and normalize a category WITHOUT persisting. For current-price providers."""
    exchange_types = _EXCHANGE_TYPES
    stash_types = _STASH_TYPES
    is_exchange = category in exchange_types
    if not is_exchange and category not in stash_types:
        return []
    url = EXCHANGE_URL if is_exchange else STASH_URL
    api_type = exchange_types[category] if is_exchange else stash_types[category]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params={"league": league, "type": api_type})
        if resp.status_code != 200:
            return []
        data = resp.json()
    records = [
        _normalize(line, league, category, is_exchange)
        for line in data.get("lines", [])
    ]
    return [r for r in records if r["price_chaos"] > 0]


async def collect_snapshot(league: str, category: str, exchange_types=None,
                           stash_types=None, timestamp: str | None = None) -> int:
    """Fetch one persisted category for a league and store it as direct observations."""
    if category not in PERSISTED_CATEGORIES:
        raise ValueError(f"Historical snapshots are disabled for high-cardinality category '{category}'")
    exchange_types = exchange_types or _EXCHANGE_TYPES
    stash_types = stash_types or _STASH_TYPES
    is_exchange = category in exchange_types
    url = EXCHANGE_URL if is_exchange else STASH_URL
    api_type = exchange_types[category] if is_exchange else stash_types[category]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params={"league": league, "type": api_type})
        if resp.status_code != 200:
            log.error("collect %s/%s: HTTP %s", league, category, resp.status_code)
            return 0
        data = resp.json()
    timestamp = timestamp or database.now_iso()
    records = [
        _normalize(line, league, category, is_exchange)
        for line in data.get("lines", [])
    ]
    records = [r for r in records if r["price_chaos"] > 0]
    stored = await database.insert_snapshots(records, timestamp)
    log.info("Stored %d snapshots for %s / %s", stored, league, category)
    return stored


async def collect_all_categories(league: str) -> dict[str, int]:
    """Prune retained history, then collect bounded exchange categories."""
    await database.prune_market_data(PERSISTED_CATEGORIES, league=league)
    if not database.collection_allowed():
        log.error("Collection paused: project storage reached the safety threshold")
        return {category: 0 for category in _EXCHANGE_TYPES}
    results = {}
    timestamp = database.now_iso()
    for category in _EXCHANGE_TYPES:
        try:
            results[category] = await collect_snapshot(
                league, category, _EXCHANGE_TYPES, _STASH_TYPES, timestamp
            )
        except Exception:
            log.exception("Failed to collect %s / %s", league, category)
            results[category] = 0
    await database.prune_market_data(PERSISTED_CATEGORIES, league=league)
    return results


async def run_collector(league: str, interval: int = 1800, once: bool = False) -> None:
    """Own the SQLite write path independently from the analytical API."""
    if interval < 1:
        raise ValueError("interval must be positive")
    while True:
        results = await collect_all_categories(league)
        cx_stored = await cx_collector.poll_latest_cx()
        log.info("collection cycle complete for %s: %s; cx=%d", league, results, cx_stored)
        if once:
            return
        await asyncio.sleep(interval)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DeusCFO historical collector.")
    parser.add_argument(
        "--league",
        default=os.environ.get("DEUSCFO_LEAGUE", "Allflame"),
        help="poe.ninja league for market snapshots (default: DEUSCFO_LEAGUE or Allflame)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("DEUSCFO_COLLECTOR_INTERVAL", "1800")),
        help="seconds between collection cycles",
    )
    parser.add_argument("--once", action="store_true", help="collect one cycle and exit")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    asyncio.run(run_collector(args.league, args.interval, args.once))
