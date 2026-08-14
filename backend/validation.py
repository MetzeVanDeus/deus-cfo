"""Look-ahead-safe historical validation for existing detectors.

The detector implementations in ``regimes`` and ``anomalies`` query the latest
market state, which is correct for the live feed but unsafe for backtests. This
module reconstructs their calculations from a bounded prefix of each item's
history. It never calls present-time detector functions.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

import database
from anomalies import _modified_zscore, _percentile_of
from regimes import _safe_pct, _trend_acceleration, _trend_direction

DEFAULT_HORIZONS = (1, 3, 6, 12, 24)
_ALLOWED_HORIZONS = set(DEFAULT_HORIZONS)
MAX_EMPIRICAL_SAMPLES = 1000
"""Deterministic cap on raw bootstrap samples returned by validation."""


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _pct(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * percentile
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def wilson_interval(successes: int, sample_size: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Two-sided 95% Wilson interval for a binomial proportion."""
    if sample_size <= 0:
        return (0.0, 0.0)
    p = successes / sample_size
    denominator = 1 + z * z / sample_size
    centre = (p + z * z / (2 * sample_size)) / denominator
    margin = z * math.sqrt(p * (1 - p) / sample_size + z * z / (4 * sample_size * sample_size)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def summarize_returns(returns: list[float], adverse: list[float] | None = None,
                      favorable: list[float] | None = None) -> dict:
    """Summarize percentage returns and expose bounded raw samples."""
    n = len(returns)
    wins = sum(value > 0 for value in returns)
    interval = wilson_interval(wins, n)
    return {
        "sample_size": n,
        # Chronological raw samples are capped for deterministic bootstrap use.
        "return_samples": [round(float(value), 6) for value in returns[:MAX_EMPIRICAL_SAMPLES]],
        "win_rate": round(wins / n, 6) if n else None,
        "win_probability": round(wins / n, 6) if n else None,
        "confidence_interval": [round(interval[0], 6), round(interval[1], 6)] if n else None,
        # Conservative 95% probability estimate; unlike a hand-tuned penalty,
        # this is the lower bound of a standard binomial interval.
        "historical_confidence": round(interval[0], 6) if n else None,
        "mean_return": round(statistics.fmean(returns), 6) if n else None,
        "median_return": round(statistics.median(returns), 6) if n else None,
        "p10_return": round(_pct(returns, 0.10), 6) if n else None,
        "p25_return": round(_pct(returns, 0.25), 6) if n else None,
        "p75_return": round(_pct(returns, 0.75), 6) if n else None,
        "p90_return": round(_pct(returns, 0.90), 6) if n else None,
        "max_adverse_movement": round(min(adverse), 6) if adverse else None,
        "max_favorable_movement": round(max(favorable), 6) if favorable else None,
        "evidence_sources": {},
        "reconstructed_sample_size": 0,
    }


def _regime(history: list[dict]) -> dict:
    """Reproduce the live regime detector from rows ending at the event."""
    item_id = history[-1]["item_id"]
    category = history[-1]["category"]
    prices = [float(row["price_chaos"]) for row in history]
    volumes = [float(row.get("volume", 0) or 0) for row in history]
    n = len(prices)
    base = {"item_id": item_id, "category": category, "regime": "Unknown", "confidence": 0.0,
            "signals": {}, "event_timestamp": history[-1]["timestamp"]}
    if n == 0:
        return base
    if n == 1:
        base.update(regime="Stable", confidence=0.1,
                    signals={"price_change_pct": 0.0, "volatility_pct": 0.0,
                             "volume_change": 1.0, "trend": "flat", "trend_acceleration": "steady"})
        return base

    current, start = prices[-1], prices[0]
    median = statistics.median(prices)
    mad = statistics.median([abs(price - median) for price in prices])
    vol_median = statistics.median(volumes) if volumes else 0.0
    price_change_pct = _safe_pct(current, start)
    price_vs_median_pct = _safe_pct(current, median)
    volatility_pct = mad / median * 100.0 if median else 0.0
    volume_change = volumes[-1] / vol_median if vol_median else 1.0
    trend = _trend_direction(prices)
    acceleration = _trend_acceleration(prices)
    signals = {"price_change_pct": round(price_change_pct, 2),
               "volatility_pct": round(volatility_pct, 2),
               "volume_change": round(volume_change, 2), "trend": trend,
               "trend_acceleration": acceleration}

    sharp_drop, sharp_rise, high_volume, volatile = -10.0, 10.0, 2.0, 8.0
    if price_change_pct < -sharp_drop and volume_change >= high_volume:
        regime, confidence = "Supply Shock", min(0.95, 0.5 + abs(price_change_pct) / 40 + (volume_change - 1) / 5)
    elif price_change_pct > sharp_rise and volume_change >= high_volume:
        regime, confidence = "Demand Shock", min(0.95, 0.5 + price_change_pct / 40 + (volume_change - 1) / 5)
    elif price_change_pct < sharp_drop and volume_change >= 1.3:
        regime, confidence = "Crashing", min(0.9, 0.4 + abs(price_change_pct) / 30)
    elif price_change_pct > sharp_rise and volume_change >= 1.3:
        regime, confidence = "Pumping", min(0.9, 0.4 + price_change_pct / 30)
    elif volume_change >= high_volume and abs(price_change_pct) < sharp_drop:
        regime, confidence = "Volume Spike", min(0.85, 0.3 + (volume_change - 1) / 4)
    elif trend == "rising" and price_change_pct < 0:
        regime, confidence = "Recovering", min(0.8, 0.3 + abs(price_change_pct) / 40)
    elif abs(price_vs_median_pct) > 5.0 and trend in ("rising", "falling") and price_vs_median_pct * price_change_pct < 0:
        regime, confidence = "Mean-Reverting", min(0.8, 0.3 + abs(price_vs_median_pct) / 30)
    elif trend == "rising" and price_change_pct > 3.0:
        regime, confidence = "Trending Up", min(0.85, 0.2 + price_change_pct / 25)
    elif trend == "falling" and price_change_pct < -3.0:
        regime, confidence = "Trending Down", min(0.85, 0.2 + abs(price_change_pct) / 25)
    else:
        regime, confidence = "Stable", max(0.1, 0.5 - volatility_pct / 20)
    base.update(regime=regime, confidence=round(confidence, 2), signals=signals)
    return base


def _anomaly(history: list[dict], window_hours: float) -> dict | None:
    """Reproduce anomaly classification using only the event-prefix history."""
    if not history:
        return None
    prices = [float(row["price_chaos"]) for row in history]
    volumes = [float(row.get("volume", 0) or 0) for row in history]
    n = len(prices)
    current_price, current_volume = prices[-1], volumes[-1]
    median = statistics.median(prices)
    mad = statistics.median([abs(price - median) for price in prices])
    volume_median = statistics.median(volumes) if volumes else 0.0
    z = _modified_zscore(current_price, median, mad)
    pct = _percentile_of(current_price, prices)
    volume_multiplier = current_volume / volume_median if volume_median else 1.0
    anomaly_type, severity = None, 0.0
    if z <= -2.0 and pct <= 0.1:
        anomaly_type, severity = "price_drop", min(1.0, abs(z) / 4.0)
    elif z >= 2.0 and pct >= 0.9:
        anomaly_type, severity = "price_spike", min(1.0, z / 4.0)
    if volume_multiplier >= 3.0 and current_volume > 0:
        value = min(1.0, (volume_multiplier - 1) / 4.0)
        if value > severity:
            anomaly_type, severity = "volume_spike", value
    elif volume_multiplier <= 0.3 and current_volume > 0 and volume_median > 0:
        value = min(1.0, (1 - volume_multiplier) / 0.7)
        if value > severity:
            anomaly_type, severity = "volume_collapse", value
    if n >= 4 and anomaly_type is None:
        mid = n // 2
        first_price, second_price = statistics.fmean(prices[:mid]), statistics.fmean(prices[mid:])
        first_volume, second_volume = statistics.fmean(volumes[:mid]), statistics.fmean(volumes[mid:])
        price_direction = 1 if second_price > first_price else -1
        volume_direction = 1 if second_volume > first_volume else -1
        price_pct = _safe_pct(second_price, first_price)
        volume_pct = _safe_pct(second_volume, first_volume)
        if price_direction != volume_direction and (abs(price_pct) > 5 or abs(volume_pct) > 30):
            anomaly_type = "divergence"
            severity = min(0.8, 0.2 + max(abs(price_pct), abs(volume_pct)) / 50)
    if n >= 4 and anomaly_type is None:
        recent = prices[-min(4, n):]
        recent_z = [_modified_zscore(price, median, mad) for price in recent]
        if len(recent_z) >= 2 and abs(recent_z[0]) > 2.0 and abs(recent_z[-1]) < abs(recent_z[0]) * 0.6:
            anomaly_type = "recovery"
            severity = min(0.7, 0.2 + abs(recent_z[0]) / 5)
    if anomaly_type is None:
        return None
    return {
        "item_id": history[-1]["item_id"], "category": history[-1]["category"],
        "anomaly_type": anomaly_type, "severity": round(severity, 2),
        "z_score": round(z, 2), "percentile": round(pct, 4),
        "price_current": round(current_price, 4), "price_median": round(median, 4),
        "volume_current": round(current_volume, 2), "volume_median": round(volume_median, 2),
        "volume_multiplier": round(volume_multiplier, 2),
        "event_timestamp": history[-1]["timestamp"],
    }


def detect_historical_signals(rows: list[dict], as_of: str | datetime,
                              window_hours: float = 24) -> list[dict]:
    """Reconstruct non-trivial regime/anomaly signals at ``as_of``.

    This function intentionally receives rows rather than querying current
    state. Callers can prove look-ahead safety by passing a truncated dataset.
    """
    event_time = _dt(as_of)
    window_start = event_time - timedelta(hours=window_hours)
    history = [row for row in rows if window_start <= _dt(row["timestamp"]) <= event_time]
    history.sort(key=lambda row: _dt(row["timestamp"]))
    if not history:
        return []
    signals = []
    regime = _regime(history)
    if regime["regime"] not in ("Stable", "Unknown"):
        signals.append({"source": "regime", "signal_type": regime["regime"],
                        "opportunity_type": "regime", **regime})
    anomaly = _anomaly(history, window_hours)
    if anomaly:
        signals.append({"source": "anomaly", "signal_type": anomaly["anomaly_type"],
                        "opportunity_type": "anomaly", **anomaly})
    return signals


def liquidity_tier(volume: float) -> str:
    if volume < 50:
        return "low"
    if volume < 500:
        return "medium"
    return "high"


def _event_outcome(history: list[dict], event: dict, target: datetime) -> dict | None:
    event_time = _dt(event["timestamp"])
    endpoint = next((row for row in history if _dt(row["timestamp"]) >= target), None)
    if endpoint is None:
        return None
    # Measure the complete path through the selected endpoint, including a
    # sparse-cadence observation that falls after the requested target.
    endpoint_time = _dt(endpoint["timestamp"])
    future = [row for row in history if event_time < _dt(row["timestamp"]) <= endpoint_time]
    if not future:
        return None
    initial = float(event["price_chaos"])
    if initial <= 0:
        return None
    path = [(float(row["price_chaos"]) / initial - 1) * 100 for row in future]
    endpoint_return = (float(endpoint["price_chaos"]) / initial - 1) * 100
    peak_index = max(range(len(path)), key=path.__getitem__)
    first_loss = next((index for index, value in enumerate(path) if value < 0), None)
    recovery = None
    if first_loss is not None:
        recovery = next(
            (row for row, value in zip(future[first_loss + 1:], path[first_loss + 1:]) if value >= 0),
            None,
        )
    return {
        "return": endpoint_return,
        "adverse": min(0.0, min(path)),
        "favorable": max(0.0, max(path)),
        "time_to_recovery": (_dt(recovery["timestamp"]) - event_time).total_seconds() / 3600 if recovery else None,
        "time_to_peak": (_dt(future[peak_index]["timestamp"]) - event_time).total_seconds() / 3600,
        "end_timestamp": endpoint["timestamp"],
    }


async def _load_rows(league: str, category: str | None = None) -> list[dict]:
    db = await database.get_db()
    try:
        if category:
            cur = await db.execute(
                "SELECT * FROM snapshots WHERE league = ? AND category = ? ORDER BY timestamp, item_id",
                (league, category),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM snapshots WHERE league = ? ORDER BY timestamp, category, item_id",
                (league,),
            )
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


def _parse_horizons(horizons: Iterable[float] | str | None) -> tuple[float, ...]:
    if horizons is None or horizons == "":
        return DEFAULT_HORIZONS
    if isinstance(horizons, str):
        values = [float(value.strip()) for value in horizons.split(",") if value.strip()]
    else:
        values = [float(value) for value in horizons]
    if not values or any(value <= 0 for value in values):
        raise ValueError("horizons must contain positive hours")
    return tuple(dict.fromkeys(values))


async def backtest(league: str, category: str | None = None,
                   horizons: Iterable[float] | str | None = None,
                   signal_window_hours: float = 24) -> dict:
    """Run all historical detector events and group their forward outcomes."""
    selected_horizons = _parse_horizons(horizons)
    rows = await _load_rows(league, category)
    by_item: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_item[(row["category"], row["item_id"])].append(row)
    groups: dict[tuple, dict[float, dict[str, list]]] = {}

    for item_rows in by_item.values():
        item_rows.sort(key=lambda row: _dt(row["timestamp"]))
        for index, event_row in enumerate(item_rows):
            signals = detect_historical_signals(item_rows[: index + 1], event_row["timestamp"], signal_window_hours)
            for signal in signals:
                key = (signal["source"], signal["signal_type"], event_row["category"],
                       liquidity_tier(float(event_row.get("volume", 0) or 0)), signal["opportunity_type"])
                horizon_data = groups.setdefault(key, {
                    horizon: {
                        "returns": [], "adverse": [], "favorable": [],
                        "recovery": [], "peak": [], "sources": [],
                    }
                    for horizon in selected_horizons
                })
                for horizon in selected_horizons:
                    outcome = _event_outcome(item_rows, event_row, _dt(event_row["timestamp"]) + timedelta(hours=horizon))
                    if outcome is None:
                        continue
                    data = horizon_data[horizon]
                    data["returns"].append(outcome["return"])
                    data["adverse"].append(outcome["adverse"])
                    data["favorable"].append(outcome["favorable"])
                    if outcome["time_to_recovery"] is not None:
                        data["recovery"].append(outcome["time_to_recovery"])
                    data["peak"].append(outcome["time_to_peak"])
                    data["sources"].append(event_row.get("source", "observed"))

    result_groups = []
    for (source, signal_type, group_category, liquidity, opp_type), horizon_data in sorted(groups.items()):
        horizons_result = {}
        for horizon in selected_horizons:
            data = horizon_data[horizon]
            summary = summarize_returns(data["returns"], data["adverse"], data["favorable"])
            source_counts = {
                source: data["sources"].count(source)
                for source in set(data["sources"])
            }
            summary["evidence_sources"] = source_counts
            summary["reconstructed_sample_size"] = sum(
                count for source, count in source_counts.items()
                if source.endswith("_reconstructed")
            )
            duration_values = data["recovery"] or data["peak"]
            summary["duration_samples"] = [
                round(float(value), 6) for value in duration_values[:MAX_EMPIRICAL_SAMPLES]
            ]
            summary["time_to_peak_samples"] = [
                round(float(value), 6) for value in data["peak"][:MAX_EMPIRICAL_SAMPLES]
            ]
            summary["time_to_recovery"] = round(statistics.median(data["recovery"]), 6) if data["recovery"] else None
            summary["time_to_peak"] = round(statistics.median(data["peak"]), 6) if data["peak"] else None
            horizons_result[str(horizon).rstrip("0").rstrip(".")] = summary
        result_groups.append({"signal_type": signal_type, "source": source,
                              "anomaly_type": signal_type if source == "anomaly" else None,
                              "regime": signal_type if source == "regime" else None,
                              "category": group_category, "liquidity_tier": liquidity,
                              "opportunity_type": opp_type, "horizons": horizons_result})
    return {"league": league, "category": category, "signal_window_hours": signal_window_hours,
            "horizons": list(selected_horizons), "groups": result_groups}


async def performance(league: str, **filters) -> dict:
    result = await backtest(league, filters.pop("category", None), filters.pop("horizons", None),
                            filters.pop("signal_window_hours", 24))
    groups = result["groups"]
    for key, value in filters.items():
        if value is not None:
            groups = [group for group in groups if str(group.get(key)) == str(value)]
    result["groups"] = groups
    return result

def _match_condition(value: float | str, condition, field: str) -> bool:
    if condition is None:
        return True
    if isinstance(condition, dict):
        allowed = {"lt", "lte", "gt", "gte", "eq"}
        if set(condition) - allowed:
            raise ValueError(f"unsupported operators for {field}")
        for operator, expected in condition.items():
            if operator == "lt" and not value < expected:
                return False
            if operator == "lte" and not value <= expected:
                return False
            if operator == "gt" and not value > expected:
                return False
            if operator == "gte" and not value >= expected:
                return False
            if operator == "eq" and str(value).casefold() != str(expected).casefold():
                return False
        return True
    return str(value).casefold() == str(condition).casefold()


def _strategy_summary(data: dict) -> dict:
    summary = summarize_returns(data["returns"], data["adverse"], data["favorable"])
    summary["occurrences"] = data["occurrences"]
    summary["drawdown"] = round(min(data["adverse"]), 6) if data["adverse"] else None
    if data["periods"]:
        best = max(data["periods"], key=lambda period: period["return"])
        worst = min(data["periods"], key=lambda period: period["return"])
        summary["best_period"] = best
        summary["worst_period"] = worst
    else:
        summary["best_period"] = None
        summary["worst_period"] = None
    return summary


async def strategy_backtest(league: str, conditions: dict,
                            category: str | None = None,
                            horizons: Iterable[float] | str | None = None,
                            signal_window_hours: float = 24) -> dict:
    """Evaluate a small declarative strategy condition set over history."""
    allowed = {"price_percentile", "volume_ratio", "regime"}
    if not isinstance(conditions, dict) or not conditions:
        raise ValueError("conditions must be a non-empty object")
    unknown = set(conditions) - allowed
    if unknown:
        raise ValueError(f"unsupported strategy condition(s): {sorted(unknown)}")
    selected_horizons = _parse_horizons(horizons)
    rows = await _load_rows(league, category)
    by_item: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_item[(row["category"], row["item_id"])].append(row)
    overall = {
        horizon: {"returns": [], "adverse": [], "favorable": [], "periods": [], "occurrences": 0}
        for horizon in selected_horizons
    }
    by_category = defaultdict(lambda: {
        horizon: {"returns": [], "adverse": [], "favorable": [], "periods": [], "occurrences": 0}
        for horizon in selected_horizons
    })
    occurrences = 0
    for item_rows in by_item.values():
        item_rows.sort(key=lambda row: _dt(row["timestamp"]))
        for index, event_row in enumerate(item_rows):
            history = [row for row in item_rows[:index + 1]
                       if _dt(event_row["timestamp"]) - timedelta(hours=signal_window_hours)
                       <= _dt(row["timestamp"]) <= _dt(event_row["timestamp"])]
            if not history:
                continue
            prices = [float(row["price_chaos"]) for row in history]
            volumes = [float(row.get("volume", 0) or 0) for row in history]
            volume_median = statistics.median(volumes) if volumes else 0
            values = {
                "price_percentile": _percentile_of(prices[-1], prices),
                "volume_ratio": volumes[-1] / volume_median if volume_median else 1.0,
                "regime": _regime(history)["regime"],
            }
            if not all(_match_condition(values[field], condition, field)
                       for field, condition in conditions.items()):
                continue
            occurrences += 1
            category_data = by_category[event_row["category"]]
            for horizon in selected_horizons:
                outcome = _event_outcome(
                    item_rows, event_row,
                    _dt(event_row["timestamp"]) + timedelta(hours=horizon),
                )
                if outcome is None:
                    continue
                for data in (overall[horizon], category_data[horizon]):
                    data["occurrences"] += 1
                    data["returns"].append(outcome["return"])
                    data["adverse"].append(outcome["adverse"])
                    data["favorable"].append(outcome["favorable"])
                    data["periods"].append({
                        "start": event_row["timestamp"],
                        "end": outcome["end_timestamp"],
                        "return": round(outcome["return"], 6),
                    })
    return {
        "league": league,
        "category": category,
        "conditions": conditions,
        "signal_window_hours": signal_window_hours,
        "horizons": list(selected_horizons),
        "occurrences": occurrences,
        "horizon_results": {
            str(horizon).rstrip("0").rstrip("."): _strategy_summary(overall[horizon])
            for horizon in selected_horizons
        },
        "category_performance": {
            group_category: {
                str(horizon).rstrip("0").rstrip("."): _strategy_summary(data[horizon])
                for horizon in selected_horizons
            }
            for group_category, data in by_category.items()
        },
    }


async def opportunity_outcome(league: str, category: str, source: str, signal_type: str,
                              horizon: float = 6) -> dict:
    result = await backtest(league, category, (horizon,))
    for group in result["groups"]:
        if group["source"] == source and group["signal_type"] == signal_type:
            return group["horizons"].get(str(horizon).rstrip("0").rstrip("."), {})
    return summarize_returns([])
