"""Query helpers over cx_history for the API endpoints."""

import datetime
import math
import statistics

import database

_EMPIRICAL_FILTER = (
    "observation_type NOT IN ('ESTIMATED', 'SYNTHETIC')"
    " AND lower(source) NOT LIKE '%synthetic%'"
    " AND lower(source) NOT LIKE '%reconstructed%'"
)


def _iso_ago(hours: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat(timespec="seconds")


_CHAOS_ID = "Metadata/Items/Currency/CurrencyRerollRare"


def _price_in_chaos(row: dict) -> tuple[str, float, float] | None:
    """Return (item id, chaos price, item volume) for an exact chaos pair."""
    chaos_is_a = row["item_a"] == _CHAOS_ID
    if not chaos_is_a and row["item_b"] != _CHAOS_ID:
        return None
    item = row["item_b"] if chaos_is_a else row["item_a"]
    chaos_ratio = row["lowest_ratio_a"] if chaos_is_a else row["lowest_ratio_b"]
    item_ratio = row["lowest_ratio_b"] if chaos_is_a else row["lowest_ratio_a"]
    volume = row["volume_b"] if chaos_is_a else row["volume_a"]
    if not all(isinstance(value, (int, float)) and value > 0 and math.isfinite(value)
               for value in (chaos_ratio, item_ratio, volume)):
        return None
    return item, chaos_ratio / item_ratio, volume


async def cx_paper_ideas(league: str, hours: int = 24, limit: int = 5) -> list[dict]:
    """Rank observed currencies trading below their prior hourly median.

    These are exploratory PAPER watch ideas, not validated expected-value claims.
    """
    if hours <= 0 or limit <= 0:
        return []
    db = await database.get_db()
    try:
        latest_cursor = await db.execute(
            f"SELECT MAX(timestamp) FROM cx_history WHERE league = ? AND {_EMPIRICAL_FILTER}",
            (league,),
        )
        latest_row = await latest_cursor.fetchone()
        latest_timestamp = latest_row[0] if latest_row else None
        if not latest_timestamp:
            return []
        latest_dt = datetime.datetime.fromisoformat(latest_timestamp.replace("Z", "+00:00"))
        if latest_dt.tzinfo is None:
            latest_dt = latest_dt.replace(tzinfo=datetime.timezone.utc)
        cutoff = (latest_dt - datetime.timedelta(hours=hours)).isoformat()
        cursor = await db.execute(
            f"""SELECT timestamp, item_a, item_b, volume_a, volume_b,
                       lowest_ratio_a, lowest_ratio_b
                FROM cx_history
                WHERE league = ? AND timestamp >= ?
                  AND (item_a = ? OR item_b = ?) AND {_EMPIRICAL_FILTER}
                ORDER BY timestamp ASC""",
            (league, cutoff, _CHAOS_ID, _CHAOS_ID),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    histories: dict[str, dict[str, tuple[float, float]]] = {}
    for raw in rows:
        row = dict(raw)
        priced = _price_in_chaos(row)
        if priced is None:
            continue
        item, price, volume = priced
        histories.setdefault(item, {})[row["timestamp"]] = (price, volume)

    ideas = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for item, by_hour in histories.items():
        timestamps = list(by_hour)
        observations = list(by_hour.values())
        if len(observations) < 3:
            continue
        current_timestamp = timestamps[-1]
        current_dt = datetime.datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
        if current_dt.tzinfo is None:
            current_dt = current_dt.replace(tzinfo=datetime.timezone.utc)
        current, volume = observations[-1]
        reference = statistics.median(price for price, _ in observations[:-1])
        gap = (reference / current - 1) * 100
        if volume < 50 or not 1 <= gap <= 100:
            continue
        ideas.append({
            "item_id": item,
            "action": "PAPER BUY WATCH",
            "current_price_chaos": round(current, 6),
            "reference_price_chaos": round(reference, 6),
            "mean_reversion_gap_percent": round(gap, 2),
            "hourly_samples": len(observations),
            "latest_volume": round(volume, 2),
            "liquidity": "high" if volume >= 500 else "medium",
            "confidence": "low",
            "snapshot_timestamp": current_timestamp,
            "data_age_hours": round(max(0, (now - current_dt).total_seconds() / 3600), 1),
            "evidence_source": "DIRECT_OBSERVATION",
            "reason": (
                f"A return to the median of {len(observations) - 1} prior hourly "
                f"observations implies {gap:.1f}% gross price upside before spread and slippage."
            ),
        })
    ideas.sort(key=lambda idea: idea["mean_reversion_gap_percent"], reverse=True)
    return ideas[:limit]


async def cx_status() -> dict:
    db = await database.get_db()
    try:
        rows = await db.execute("SELECT COUNT(*) FROM cx_history")
        total_row = await rows.fetchone()
        total = total_row[0] if total_row else 0
        cur = await db.execute("SELECT MIN(timestamp), MAX(timestamp) FROM cx_history")
        row = await cur.fetchone()
        min_ts, max_ts = (row[0], row[1]) if row else (None, None)
    finally:
        await db.close()
    cursor = await database.get_cx_cursor("default")
    return {
        "last_change_id": cursor.get("last_change_id"),
        "first_change_id": cursor.get("first_change_id"),
        "first_available_hour": cursor.get("first_available_hour"),
        "last_synced_hour": cursor.get("last_synced_hour"),
        "total_rows": total,
        "db_file_size": await database.db_file_size(),
        "oldest_timestamp": min_ts,
        "newest_timestamp": max_ts,
    }


async def cx_history_for(league: str, item_ids: list[str], hours: int = 24) -> list[dict]:
    """Rows for a league where either side is one of item_ids."""
    db = await database.get_db()
    try:
        ph = ",".join("?" * len(item_ids))
        cur = await db.execute(
            f"""SELECT * FROM cx_history
                WHERE league = ? AND timestamp >= ?
                  AND (item_a IN ({ph}) OR item_b IN ({ph}))
                  AND {_EMPIRICAL_FILTER}
                ORDER BY timestamp ASC""",
            (league, _iso_ago(hours), *item_ids, *item_ids),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def cx_item_ids(league: str) -> set[str]:
    """Distinct metadata IDs actually present for a league."""
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT item_a AS item_id FROM cx_history WHERE league = ? AND {_EMPIRICAL_FILTER}
               UNION SELECT item_b FROM cx_history WHERE league = ? AND {_EMPIRICAL_FILTER}""",
            (league, league),
        )
        return {row["item_id"] for row in await cur.fetchall()}
    finally:
        await db.close()
