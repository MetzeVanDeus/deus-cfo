"""Query helpers over cx_history for the API endpoints."""

import datetime

import database

_EMPIRICAL_FILTER = (
    "observation_type NOT IN ('ESTIMATED', 'SYNTHETIC')"
    " AND lower(source) NOT LIKE '%synthetic%'"
    " AND lower(source) NOT LIKE '%reconstructed%'"
)


def _iso_ago(hours: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat(timespec="seconds")


async def cx_status() -> dict:
    db = await database.get_db()
    try:
        rows = await db.execute("SELECT COUNT(*) FROM cx_history")
        total = (await rows.fetchone())[0]
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
