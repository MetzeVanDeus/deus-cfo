"""Periodic snapshot collection from poe.ninja into SQLite."""

import logging
from datetime import datetime, timedelta, timezone

import httpx

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
    """Map a poe.ninja line into a snapshot record."""
    if is_exchange:
        item_id = line.get("id", "")
        spark = line.get("sparkline", {}) or {}
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
    }
def _sparkline_history(line: dict, record: dict, collected_at: str) -> list[tuple[str, dict]]:
    """Reconstruct poe.ninja's seven-day relative sparkline as daily prices."""
    points = (line.get("sparkline") or {}).get("data") or []
    current = float(record["price_chaos"])
    if len(points) < 2 or current <= 0 or points[-1] is None or points[-1] <= -100:
        return []
    baseline = current / (1 + float(points[-1]) / 100)
    collected = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=timezone.utc)
    today = collected.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    history = []
    for index, change in enumerate(points[:-1]):
        if change is None:
            continue
        price = baseline * (1 + float(change) / 100)
        if price <= 0:
            continue
        day = today - timedelta(days=len(points) - 1 - index)
        historical = dict(
            record,
            price_chaos=price,
            volume=0,
            listing_count=0,
            source="poe.ninja_sparkline_reconstructed",
        )
        history.append((day.isoformat(timespec="seconds"), historical))
    return history




async def collect_snapshot(league: str, category: str, exchange_types=None,
                           stash_types=None, timestamp: str | None = None) -> int:
    """Fetch one persisted category for a league and store it."""
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
    normalized = [(_normalize(line, league, category, is_exchange), line) for line in data.get("lines", [])]
    normalized = [(record, line) for record, line in normalized if record["price_chaos"] > 0]
    stored = await database.insert_snapshots([record for record, _ in normalized], timestamp)
    if is_exchange:
        by_timestamp: dict[str, list[dict]] = {}
        for record, line in normalized:
            for history_timestamp, historical in _sparkline_history(line, record, timestamp):
                by_timestamp.setdefault(history_timestamp, []).append(historical)
        for history_timestamp, records in by_timestamp.items():
            stored += await database.insert_snapshots(records, history_timestamp)
    log.info("Stored %d snapshots for %s / %s", stored, league, category)
    return stored


async def collect_all_categories(league: str) -> dict[str, int]:
    """Prune retained history, then collect bounded exchange categories."""
    await database.prune_market_data(PERSISTED_CATEGORIES)
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
    await database.prune_market_data(PERSISTED_CATEGORIES)
    return results
