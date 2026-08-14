"""Market-wide events and non-predictive lagged relationship investigation.

All calculations are derived from historical snapshot rows.  A relationship is
reported as a *potential* leader/laggard only after chronological train and
out-of-sample checks meet the evidence thresholds; this module never labels a
relationship predictive.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Iterable

import database


DEFAULT_LAGS = (1.0, 3.0, 6.0)
MIN_RELATIONSHIP_SAMPLES = 12
MIN_TRAIN_SAMPLES = 6
MIN_OUT_OF_SAMPLE_SAMPLES = 4


@dataclass
class MarketEvent:
    """A synchronized movement spanning one or more market categories."""

    type: str
    affected_items: list[str]
    affected_categories: list[str]
    start_time: str
    magnitude: float
    confidence: float
    sample_size: int

    def as_dict(self) -> dict:
        return asdict(self)

    to_dict = as_dict


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _normalise_snapshots(rows: Iterable[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group duplicate snapshots and return chronologically ordered series."""
    grouped: dict[tuple[str, str, datetime], list[dict]] = defaultdict(list)
    for row in rows:
        try:
            timestamp = _dt(row["timestamp"])
            price = float(row["price_chaos"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        category, item = str(row.get("category", "")), str(row.get("item_id", ""))
        if not category or not item:
            continue
        grouped[(category, item, timestamp)].append(row)

    series: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for (category, item, timestamp), values in grouped.items():
        prices = [float(value["price_chaos"]) for value in values]
        volumes = [float(value.get("volume", 0) or 0) for value in values]
        series[(category, item)].append(
            {
                "timestamp": timestamp,
                "timestamp_text": str(values[0]["timestamp"]),
                "price": statistics.median(prices),
                "volume": statistics.fmean(volumes) if volumes else 0.0,
            }
        )
    for values in series.values():
        values.sort(key=lambda value: value["timestamp"])
    return series


def _pct(new: float, old: float) -> float | None:
    if old <= 0:
        return None
    return (new / old - 1.0) * 100.0


def _event_confidence(coverage: float, sample_size: int, categories: int = 1) -> float:
    return round(min(0.99, 0.35 + 0.45 * coverage + 0.1 * min(1.0, sample_size / 10) + 0.05 * min(1, categories - 1)), 6)


def detect_market_events(
    rows: Iterable[dict],
    *,
    price_threshold_pct: float = 5.0,
    volume_threshold_pct: float = 100.0,
    min_items: int = 3,
    min_coverage: float = 0.6,
) -> list[MarketEvent]:
    """Detect synchronized category and cross-category movements.

    ``rows`` are snapshot dictionaries with ``timestamp``, ``category``,
    ``item_id``, ``price_chaos`` and optional ``volume`` fields.  Returns one
    event per timestamp and movement type.  A category must have at least
    ``min_items`` movers and the dominant direction must cover
    ``min_coverage`` of its observed items, preventing isolated item signals
    from becoming market events.
    """
    series = _normalise_snapshots(rows)
    by_timestamp: dict[datetime, list[dict]] = defaultdict(list)
    for (category, item), values in series.items():
        for index in range(1, len(values)):
            previous, current = values[index - 1], values[index]
            price_return = _pct(current["price"], previous["price"])
            volume_return = _pct(current["volume"], previous["volume"]) if previous["volume"] > 0 else None
            if price_return is None:
                continue
            by_timestamp[current["timestamp"]].append(
                {
                    "category": category,
                    "item": item,
                    "price_return": price_return,
                    "volume_return": volume_return,
                }
            )

    events: list[MarketEvent] = []
    for timestamp, movements in sorted(by_timestamp.items()):
        by_category: dict[str, list[dict]] = defaultdict(list)
        for movement in movements:
            by_category[movement["category"]].append(movement)

        category_price: dict[str, MarketEvent] = {}
        category_volume: dict[str, MarketEvent] = {}
        for category, values in by_category.items():
            price_movers = [value for value in values if abs(value["price_return"]) >= price_threshold_pct]
            if price_movers:
                positive = sum(value["price_return"] > 0 for value in price_movers)
                negative = len(price_movers) - positive
                direction = 1 if positive >= negative else -1
                directed = [value for value in price_movers if value["price_return"] * direction > 0]
                coverage = len(directed) / len(values)
                if len(directed) >= min_items and coverage >= min_coverage:
                    category_price[category] = MarketEvent(
                        type="category_price_move",
                        affected_items=[value["item"] for value in directed],
                        affected_categories=[category],
                        start_time=timestamp.isoformat(),
                        magnitude=round(statistics.fmean(abs(value["price_return"]) for value in directed), 6),
                        confidence=_event_confidence(coverage, len(values)),
                        sample_size=len(values),
                    )

            volume_movers = [
                value for value in values
                if value["volume_return"] is not None and value["volume_return"] >= volume_threshold_pct
            ]
            coverage = len(volume_movers) / len(values) if values else 0.0
            if len(volume_movers) >= min_items and coverage >= min_coverage:
                category_volume[category] = MarketEvent(
                    type="category_volume_spike",
                    affected_items=[value["item"] for value in volume_movers],
                    affected_categories=[category],
                    start_time=timestamp.isoformat(),
                    magnitude=round(statistics.fmean(value["volume_return"] for value in volume_movers), 6),
                    confidence=_event_confidence(coverage, len(values)),
                    sample_size=len(values),
                )

        events.extend(category_price.values())
        events.extend(category_volume.values())
        for candidates, event_type in ((category_price, "cross_category_price_move"), (category_volume, "cross_category_volume_spike")):
            if len(candidates) < 2:
                continue
            categories = sorted(candidates)
            selected = [candidates[category] for category in categories]
            items = sorted({item for event in selected for item in event.affected_items})
            if len(items) < max(min_items, 2 * min_items):
                continue
            magnitude = statistics.fmean(event.magnitude for event in selected)
            coverage = statistics.fmean(event.confidence for event in selected)
            events.append(
                MarketEvent(
                    type=event_type,
                    affected_items=items,
                    affected_categories=categories,
                    start_time=timestamp.isoformat(),
                    magnitude=round(magnitude, 6),
                    confidence=round(min(0.99, coverage + 0.1), 6),
                    sample_size=sum(event.sample_size for event in selected),
                )
            )

    return sorted(events, key=lambda event: (event.start_time, event.type))


async def _load_snapshot_rows(league: str, category: str | None = None) -> list[dict]:
    db = await database.get_db()
    try:
        if category:
            cursor = await db.execute(
                "SELECT * FROM snapshots WHERE league = ? AND category = ? ORDER BY timestamp, item_id",
                (league, category),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM snapshots WHERE league = ? ORDER BY timestamp, category, item_id",
                (league,),
            )
        return [dict(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def detect_market_events_from_db(
    league: str,
    category: str | None = None,
    **kwargs,
) -> list[MarketEvent]:
    """Load historical snapshots for ``league`` and detect market events."""
    return detect_market_events(await _load_snapshot_rows(league, category), **kwargs)


def _selector_matches(key: tuple[str, str], selector: str | tuple[str, str] | dict) -> bool:
    category, item = key
    if isinstance(selector, dict):
        return (selector.get("category") is None or str(selector["category"]) == category) and (
            selector.get("item_id") is None or str(selector["item_id"]) == item
        )
    if isinstance(selector, (tuple, list)) and len(selector) == 2:
        return category == str(selector[0]) and item == str(selector[1])
    value = str(selector)
    return item == value or category == value or f"{category}:{item}" == value


def _label(selector: str | tuple[str, str] | dict) -> str:
    if isinstance(selector, dict):
        if selector.get("category") is not None and selector.get("item_id") is not None:
            return f"{selector['category']}:{selector['item_id']}"
        return str(selector.get("item_id") or selector.get("category"))
    if isinstance(selector, (tuple, list)):
        return f"{selector[0]}:{selector[1]}"
    return str(selector)


def _rank(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + end - 1) / 2 + 1
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    left, right = _rank(left), _rank(right)
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_ss = sum((a - left_mean) ** 2 for a in left)
    right_ss = sum((b - right_mean) ** 2 for b in right)
    return numerator / math.sqrt(left_ss * right_ss) if left_ss and right_ss else 0.0


def _sign_test_pvalue(successes: int, sample_size: int) -> float | None:
    if sample_size <= 0:
        return None
    failures = sample_size - successes
    tail = min(successes, failures)
    probability = sum(math.comb(sample_size, i) for i in range(tail + 1)) / (2 ** sample_size)
    return min(1.0, 2.0 * probability)


def _directional_stats(samples: list[tuple[float, float]]) -> dict:
    active = [(left, right) for left, right in samples if left != 0 and right != 0]
    successes = sum(left * right > 0 for left, right in active)
    consistency = successes / len(active) if active else None
    correlation = _correlation([a for a, _ in active], [b for _, b in active]) if active else None
    return {
        "sample_size": len(samples),
        "directional_sample_size": len(active),
        "directional_consistency": round(consistency, 6) if consistency is not None else None,
        "follow_through_rate": round(consistency, 6) if consistency is not None else None,
        "significance_p_value": round(_sign_test_pvalue(successes, len(active)), 6) if active else None,
        "lagged_rank_correlation": round(correlation, 6) if correlation is not None else None,
    }


def _selected_series(
    series: dict[tuple[str, str], list[dict]],
    selector: str | tuple[str, str] | dict,
) -> list[dict]:
    """Select an item, or aggregate all items when ``selector`` is a category."""
    matches = [(key, values) for key, values in series.items() if _selector_matches(key, selector)]
    if not matches:
        return []
    if isinstance(selector, (tuple, list)) or isinstance(selector, dict) and selector.get("item_id") is not None:
        return matches[0][1]
    value = str(selector) if not isinstance(selector, dict) else str(selector.get("category"))
    item_matches = [(key, values) for key, values in matches if key[1] == value]
    if item_matches:
        return item_matches[0][1]
    grouped: dict[datetime, list[dict]] = defaultdict(list)
    for _, values in matches:
        for point in values:
            grouped[point["timestamp"]].append(point)
    return [
        {
            "timestamp": timestamp,
            "timestamp_text": timestamp.isoformat(),
            "price": statistics.median([point["price"] for point in points]),
            "volume": statistics.fmean([point["volume"] for point in points]),
        }
        for timestamp, points in sorted(grouped.items())
    ]


def _aligned_samples(
    rows: Iterable[dict],
    leader: str | tuple[str, str] | dict,
    laggard: str | tuple[str, str] | dict,
    lag_hours: float,
) -> list[tuple[float, float, datetime]]:
    series = _normalise_snapshots(rows)
    leaders = next((values for key, values in series.items() if _selector_matches(key, leader)), [])
    laggards = next((values for key, values in series.items() if _selector_matches(key, laggard)), [])
    if not leaders or not laggards or lag_hours <= 0:
        return []
    lag_times = [value["timestamp"] for value in laggards]
    lag_delta = timedelta(hours=lag_hours)
    samples: list[tuple[float, float, datetime]] = []
    for leader_index in range(1, len(leaders)):
        start, current = leaders[leader_index - 1], leaders[leader_index]
        target = current["timestamp"] + lag_delta
        lag_index = bisect_left(lag_times, target)
        if lag_index >= len(laggards) or lag_times[lag_index] != target or lag_index == 0:
            continue
        lag_start, lag_current = laggards[lag_index - 1], laggards[lag_index]
        leader_return = _pct(current["price"], start["price"])
        laggard_return = _pct(lag_current["price"], lag_start["price"])
        if leader_return is not None and laggard_return is not None:
            samples.append((leader_return, laggard_return, current["timestamp"]))
    return samples


def investigate_lagged_relationship(
    rows: Iterable[dict],
    leader: str | tuple[str, str] | dict,
    laggard: str | tuple[str, str] | dict,
    lag_hours: float = 1.0,
    *,
    min_samples: int = MIN_RELATIONSHIP_SAMPLES,
    min_train_samples: int = MIN_TRAIN_SAMPLES,
    min_out_of_sample_samples: int = MIN_OUT_OF_SAMPLE_SAMPLES,
) -> dict:
    """Measure directional lagged association with chronological holdout data."""
    samples = _aligned_samples(rows, leader, laggard, float(lag_hours))
    sample_pairs = [(left, right) for left, right, _ in samples]
    sample_size = len(sample_pairs)
    split = int(sample_size * 0.7)
    train_pairs, out_pairs = sample_pairs[:split], sample_pairs[split:]
    result = {
        "status": "insufficient_data",
        "leader": _label(leader),
        "laggard": _label(laggard),
        "lag_hours": float(lag_hours),
        "sample_size": sample_size,
        "minimum_sample_size": min_samples,
        "train_sample_size": len(train_pairs),
        "out_of_sample_sample_size": len(out_pairs),
        "train": _directional_stats(train_pairs),
        "out_of_sample": _directional_stats(out_pairs),
        "full_sample": _directional_stats(sample_pairs),
        "potential_leader": None,
        "potential_laggard": None,
    }
    if sample_size < min_samples or len(train_pairs) < min_train_samples or len(out_pairs) < min_out_of_sample_samples:
        result["reason"] = "insufficient_aligned_samples"
        return result

    train_stats, out_stats, full_stats = result["train"], result["out_of_sample"], result["full_sample"]
    significant = (
        full_stats["significance_p_value"] is not None
        and full_stats["significance_p_value"] <= 0.05
        and train_stats["directional_consistency"] is not None
        and out_stats["directional_consistency"] is not None
        and train_stats["directional_consistency"] >= 0.6
        and out_stats["directional_consistency"] >= 0.6
    )
    if not significant:
        result["status"] = "insufficient_evidence"
        result["reason"] = "directional_consistency_or_significance_below_threshold"
        return result
    result.update(
        status="potential_relationship",
        potential_leader=_label(leader),
        potential_laggard=_label(laggard),
        evidence_thresholds={
            "minimum_sample_size": min_samples,
            "minimum_train_samples": min_train_samples,
            "minimum_out_of_sample_samples": min_out_of_sample_samples,
            "minimum_directional_consistency": 0.6,
            "maximum_significance_p_value": 0.05,
        },
    )
    return result


# Short alias for callers that prefer American spelling.
analyze_lagged_relationship = investigate_lagged_relationship


def investigate_lagged_relationships(
    rows: Iterable[dict],
    pairs: Iterable[tuple[object, object]] | None = None,
    lag_hours: Iterable[float] = DEFAULT_LAGS,
    **kwargs,
) -> list[dict]:
    """Investigate supplied pairs, or every distinct item pair, at each lag."""
    series = _normalise_snapshots(rows)
    selectors = list(series)
    selected_pairs = list(pairs) if pairs is not None else list(combinations(selectors, 2))
    return [
        investigate_lagged_relationship(rows, leader, laggard, lag, **kwargs)
        for leader, laggard in selected_pairs
        for lag in lag_hours
    ]


async def investigate_lagged_relationship_from_db(
    league: str,
    leader: str | tuple[str, str] | dict,
    laggard: str | tuple[str, str] | dict,
    lag_hours: float = 1.0,
    **kwargs,
) -> dict:
    """Investigate one item/category pair using stored league snapshots."""
    return investigate_lagged_relationship(
        await _load_snapshot_rows(league), leader, laggard, lag_hours, **kwargs
    )
