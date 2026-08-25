"""Historical market data queries over the snapshots table."""

import logging
import math
import statistics
from datetime import datetime, timedelta, timezone

import httpx

import database

log = logging.getLogger("deuscfo.market_data")

POE_NINJA_BASE = "https://poe.ninja"
EXCHANGE_URL = f"{POE_NINJA_BASE}/poe1/api/economy/exchange/current/overview"

# Category ids and poe.ninja API type values are one contract shared by the API
# and collector.  Keeping the endpoint mapping here prevents drift between them.
EXCHANGE_TYPES = {
    "Currency": "Currency",
    "Fragment": "Fragments",
    "Scarab": "Scarabs",
    "Essence": "Essences",
    "Oil": "Oils",
    "Fossil": "Fossils",
    "DeliriumOrb": "Delirium Orbs",
    "DivinationCard": "Divination Cards",
}
STASH_TYPES = {
    "SkillGem": "Skill Gems",
    "UniqueWeapon": "Unique Weapons",
    "UniqueArmour": "Unique Armours",
    "UniqueAccessory": "Unique Accessories",
    "UniqueJewel": "Unique Jewels",
    "UniqueFlask": "Unique Flasks",
    "Map": "Maps",
    "BlightedMap": "Blighted Maps",
    "UniqueMap": "Unique Maps",
}
ALL_CATEGORIES = {**EXCHANGE_TYPES, **STASH_TYPES}
COLLECTION_TYPES = {**EXCHANGE_TYPES, "UniqueAccessory": STASH_TYPES["UniqueAccessory"]}


def format_slug(slug: str) -> str:
    """Turn 'abyss-scarab-of-descending' into 'Abyss Scarab of Descending'."""
    parts = slug.replace("_", "-").split("-")
    small = {"of", "the", "a", "an", "and", "or", "in", "on", "to", "for"}
    return " ".join(
        word.lower() if word.lower() in small and index > 0 else word.capitalize()
        for index, word in enumerate(parts)
    )


async def _stored_chaos_per_divine(league: str) -> float:
    db = await database.get_db()
    try:
        cursor = await db.execute(
            """SELECT price_chaos FROM snapshots
               WHERE league = ? AND category = 'Currency'
                 AND (item_id = 'divine' OR item_name = 'Divine Orb')
               ORDER BY timestamp DESC LIMIT 1""",
            (league,),
        )
        row = await cursor.fetchone()
        value = row["price_chaos"] if row else 0
        return float(value) if isinstance(value, (int, float)) and value > 0 else 0.0
    finally:
        await db.close()


async def resolve_chaos_per_divine(league: str) -> float | None:
    """Resolve the live Divine rate, falling back to the latest stored snapshot."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(EXCHANGE_URL, params={"league": league, "type": "Currency"})
            if response.status_code == 200:
                payload = response.json()
                for line in payload.get("lines", []) if isinstance(payload, dict) else []:
                    if isinstance(line, dict) and str(line.get("id", "")).casefold() == "divine":
                        value = line.get("primaryValue")
                        if (
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and math.isfinite(value)
                            and value > 0
                        ):
                            return float(value)
    except Exception:
        log.exception("currency resolution failed for %s", league)
    stored = await _stored_chaos_per_divine(league)
    return stored or None


_EMPIRICAL_FILTER = (
    "observation_type NOT IN ('ESTIMATED', 'SYNTHETIC')"
    " AND lower(source) NOT LIKE '%synthetic%'"
    " AND lower(source) NOT LIKE '%reconstructed%'"
)


def _iso_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


async def get_price_history(league: str, category: str, item_id: str, hours: float = 24):
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT timestamp, price_chaos, volume FROM snapshots
               WHERE league = ? AND category = ? AND item_id = ?
                 AND timestamp >= ? AND {_EMPIRICAL_FILTER}
               ORDER BY timestamp ASC""",
            (league, category, item_id, _iso_ago(hours)),
        )
        return [(r["timestamp"], r["price_chaos"], r["volume"]) for r in await cur.fetchall()]
    finally:
        await db.close()


async def get_category_histories(league: str, category: str, hours: float = 24) -> dict:
    """item_id -> ordered history, loaded in one query."""
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT item_id, timestamp, price_chaos, volume FROM snapshots
               WHERE league = ? AND category = ? AND timestamp >= ?
                 AND {_EMPIRICAL_FILTER}
               ORDER BY item_id, timestamp""",
            (league, category, _iso_ago(hours)),
        )
        histories = {}
        for row in await cur.fetchall():
            histories.setdefault(row["item_id"], []).append(
                (row["timestamp"], row["price_chaos"], row["volume"])
            )
        return histories
    finally:
        await db.close()


async def get_latest_prices(league: str, category: str) -> dict:
    """item_id -> latest snapshot row for a category (newest per item only)."""
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT s.* FROM snapshots s
               JOIN (SELECT item_id, MAX(timestamp) AS ts FROM snapshots
                     WHERE league = ? AND category = ? AND {_EMPIRICAL_FILTER}
                     GROUP BY item_id) m
                 ON s.item_id = m.item_id AND s.timestamp = m.ts
               WHERE s.league = ? AND s.category = ? AND {_EMPIRICAL_FILTER}""",
            (league, category, league, category),
        )
        return {r["item_id"]: dict(r) for r in await cur.fetchall()}
    finally:
        await db.close()


async def get_price_at(league: str, category: str, item_id: str, hours_ago: float):
    """Snapshot nearest to (now - hours_ago); None if nothing in range."""
    target = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    db = await database.get_db()
    try:
        # Latest one at-or-before target, else earliest at-or-after.
        for sql, args in (
            (
                f"""SELECT * FROM snapshots WHERE league = ? AND category = ? AND item_id = ?
                   AND timestamp <= ? AND {_EMPIRICAL_FILTER} ORDER BY timestamp DESC LIMIT 1""",
                (league, category, item_id, target),
            ),
            (
                f"""SELECT * FROM snapshots WHERE league = ? AND category = ? AND item_id = ?
                   AND timestamp >= ? AND {_EMPIRICAL_FILTER} ORDER BY timestamp ASC LIMIT 1""",
                (league, category, item_id, target),
            ),
        ):
            cur = await db.execute(sql, args)
            row = await cur.fetchone()
            if row:
                return dict(row)
        return None
    finally:
        await db.close()


def rolling_stats(hist) -> dict:
    """Robust statistics over an already-loaded item history."""
    prices = [p for _, p, _ in hist]
    vols = [v for _, _, v in hist]
    n = len(prices)
    if n == 0:
        return {"count": 0, "mean": None, "median": None, "std": None, "mad": None,
                "min": None, "max": None, "p25": None, "p75": None,
                "percentile_rank": None, "volume_mean": None, "volume_median": None}

    prices_sorted = sorted(prices)
    p25 = prices_sorted[max(0, int(n * 0.25) - 1)]
    p75 = prices_sorted[min(n - 1, int(n * 0.75) - 1)]
    median = statistics.median(prices_sorted)
    mad = statistics.median([abs(p - median) for p in prices_sorted])
    current = prices[-1]
    rank = sum(1 for p in prices if p <= current) / n
    return {
        "count": n,
        "mean": round(statistics.fmean(prices), 4),
        "median": round(median, 4),
        "std": round(statistics.pstdev(prices), 4) if n > 1 else 0.0,
        "mad": round(mad, 4),
        "min": round(prices_sorted[0], 4),
        "max": round(prices_sorted[-1], 4),
        "p25": round(p25, 4),
        "p75": round(p75, 4),
        "percentile_rank": round(rank, 4),
        "volume_mean": round(statistics.fmean(vols), 2) if vols else 0.0,
        "volume_median": round(statistics.median(sorted(vols)), 2) if vols else 0.0,
    }


async def get_rolling_stats(league: str, category: str, item_id: str, hours: float = 24) -> dict:
    return rolling_stats(await get_price_history(league, category, item_id, hours))


async def get_all_latest(league: str) -> dict:
    """All latest snapshots for a league, grouped by category."""
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT s.* FROM snapshots s
               JOIN (SELECT league, category, item_id, MAX(timestamp) AS ts FROM snapshots
                     WHERE league = ? AND {_EMPIRICAL_FILTER} GROUP BY category, item_id) m
                 ON s.league = m.league AND s.category = m.category
                    AND s.item_id = m.item_id AND s.timestamp = m.ts
               WHERE s.league = ? AND {_EMPIRICAL_FILTER}""",
            (league, league),
        )
        grouped = {}
        for r in await cur.fetchall():
            grouped.setdefault(r["category"], []).append(dict(r))
        return grouped
    finally:
        await db.close()
