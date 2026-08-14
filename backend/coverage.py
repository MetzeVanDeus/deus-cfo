"""Data Coverage service.

Exposes per source/category coverage metrics and a trust-gate function
that rejects inadequate coverage or estimated/synthetic data for backtesting.
"""

from __future__ import annotations

import datetime

import database

_EMPIRICAL_TYPES = ("DIRECT_OBSERVATION", "OFFICIAL_HISTORICAL", "IMPORTED_TRUSTED")
_EMPIRICAL_FILTER = (
    "observation_type NOT IN ('ESTIMATED', 'SYNTHETIC')"
    " AND lower(source) NOT LIKE '%synthetic%'"
    " AND lower(source) NOT LIKE '%reconstructed%'"
)


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _hours_between(first: str, last: str) -> int:
    """Whole hours between two ISO timestamps, inclusive."""
    try:
        a = datetime.datetime.fromisoformat(first)
        b = datetime.datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return 0
    if a.tzinfo is None:
        a = a.replace(tzinfo=datetime.timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=datetime.timezone.utc)
    return max(0, int((b - a).total_seconds() // 3600) + 1)


async def snapshot_coverage(league: str, category: str) -> dict:
    """Coverage for poe.ninja snapshots in a category."""
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts,
                       COUNT(DISTINCT timestamp) AS hours_present,
                       observation_type, confidence_grade
                FROM snapshots
                WHERE league = ? AND category = ? AND {_EMPIRICAL_FILTER}
                GROUP BY observation_type, confidence_grade
                ORDER BY hours_present DESC""",
            (league, category),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    if not rows:
        return {
            "source": "poe.ninja",
            "category": category,
            "league": league,
            "first_timestamp": None,
            "last_timestamp": None,
            "hours_present": 0,
            "hours_missing": 0,
            "coverage_percentage": 0.0,
            "observation_type": None,
            "confidence_grade": None,
        }

    first_ts = min(r["first_ts"] for r in rows if r["first_ts"])
    last_ts = max(r["last_ts"] for r in rows if r["last_ts"])
    hours_present = max(r["hours_present"] for r in rows)
    total_hours = _hours_between(first_ts, last_ts)
    hours_missing = max(0, total_hours - hours_present)
    best = max(rows, key=lambda r: r["hours_present"])
    pct = round(hours_present / total_hours * 100, 1) if total_hours else 0.0
    return {
        "source": "poe.ninja",
        "category": category,
        "league": league,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "hours_present": hours_present,
        "hours_missing": hours_missing,
        "coverage_percentage": pct,
        "observation_type": best["observation_type"],
        "confidence_grade": best["confidence_grade"],
    }


async def cx_coverage(league: str) -> dict:
    """Coverage for GGG currency-exchange history."""
    db = await database.get_db()
    try:
        cur = await db.execute(
            f"""SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts,
                       COUNT(DISTINCT timestamp) AS hours_present,
                       observation_type, confidence_grade
                FROM cx_history
                WHERE league = ? AND {_EMPIRICAL_FILTER}
                GROUP BY observation_type, confidence_grade
                ORDER BY hours_present DESC""",
            (league,),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    if not rows:
        return {
            "source": "ggg_currency_exchange",
            "category": "Currency Exchange",
            "league": league,
            "first_timestamp": None,
            "last_timestamp": None,
            "hours_present": 0,
            "hours_missing": 0,
            "coverage_percentage": 0.0,
            "observation_type": None,
            "confidence_grade": None,
        }

    first_ts = min(r["first_ts"] for r in rows if r["first_ts"])
    last_ts = max(r["last_ts"] for r in rows if r["last_ts"])
    hours_present = max(r["hours_present"] for r in rows)
    total_hours = _hours_between(first_ts, last_ts)
    hours_missing = max(0, total_hours - hours_present)
    best = max(rows, key=lambda r: r["hours_present"])
    pct = round(hours_present / total_hours * 100, 1) if total_hours else 0.0
    return {
        "source": "ggg_currency_exchange",
        "category": "Currency Exchange",
        "league": league,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "hours_present": hours_present,
        "hours_missing": hours_missing,
        "coverage_percentage": pct,
        "observation_type": best["observation_type"],
        "confidence_grade": best["confidence_grade"],
    }


async def all_coverage(league: str) -> list[dict]:
    """Coverage for all data sources for a league."""
    import collector
    results = []
    for category in sorted(collector.PERSISTED_CATEGORIES):
        results.append(await snapshot_coverage(league, category))
    results.append(await cx_coverage(league))
    return results


async def can_trust_window(
    league: str,
    category: str,
    hours: float,
    min_coverage: float = 0.6,
    source: str = "snapshot",
) -> dict:
    """Trust gate for backtesting.

    Returns {"trusted": bool, "reason": str, "coverage": dict}.
    Rejects if coverage is inadequate or data is estimated/synthetic.
    """
    if source == "cx":
        cov = await cx_coverage(league)
    else:
        cov = await snapshot_coverage(league, category)

    obs_type = cov.get("observation_type")
    if obs_type and obs_type not in _EMPIRICAL_TYPES:
        return {"trusted": False, "reason": f"observation_type is {obs_type}, not empirical", "coverage": cov}

    if cov["hours_present"] == 0:
        return {"trusted": False, "reason": "no empirical data present", "coverage": cov}

    needed_hours = int(hours)
    if cov["hours_present"] < needed_hours:
        return {"trusted": False, "reason": f"only {cov['hours_present']} hours present, need {needed_hours}", "coverage": cov}

    if cov["coverage_percentage"] < min_coverage * 100:
        return {"trusted": False, "reason": f"coverage {cov['coverage_percentage']}% below threshold {min_coverage * 100:.0f}%", "coverage": cov}

    return {"trusted": True, "reason": "ok", "coverage": cov}
