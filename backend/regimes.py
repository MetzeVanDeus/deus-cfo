"""Market regime detection — classifies each item's recent price action."""

import statistics

import market_data


def _safe_pct(new: float, old: float) -> float:
    """Percentage change old→new, safe against zero."""
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0


def _trend_direction(prices: list[float]) -> str:
    """Classify the overall slope of prices as rising/falling/flat."""
    if len(prices) < 2:
        return "flat"
    # Compare first half average vs second half average
    mid = len(prices) // 2
    first_half = statistics.fmean(prices[:mid]) if mid > 0 else prices[0]
    second_half = statistics.fmean(prices[mid:])
    pct = _safe_pct(second_half, first_half)
    if pct > 2.0:
        return "rising"
    if pct < -2.0:
        return "falling"
    return "flat"


def _trend_acceleration(prices: list[float]) -> str:
    """Is the rate of change speeding up or slowing down?"""
    if len(prices) < 4:
        return "steady"
    mid = len(prices) // 2
    # First-half slope vs second-half slope (as % of starting price of each segment)
    first_start, first_end = prices[0], prices[mid - 1] if mid > 1 else prices[0]
    second_start, second_end = prices[mid], prices[-1]
    slope1 = _safe_pct(first_end, first_start)
    slope2 = _safe_pct(second_end, second_start)
    # Accelerating if magnitude of slope2 > magnitude of slope1 in same direction
    if abs(slope2) > abs(slope1) * 1.3 and (slope1 * slope2 >= 0):
        return "accelerating"
    if abs(slope2) < abs(slope1) * 0.7 and (slope1 * slope2 >= 0):
        return "decelerating"
    return "steady"


async def detect_regime(league: str, category: str, item_id: str, hours: float = 24,
                        _history=None) -> dict:
    """Classify one item's market regime from recent price history."""
    hist = _history if _history is not None else await market_data.get_price_history(
        league, category, item_id, hours
    )
    stats = market_data.rolling_stats(hist)

    n = stats["count"]
    # Sparse data → Stable with low confidence
    if n == 0:
        return {
            "item_id": item_id, "category": category,
            "regime": "Unknown", "confidence": 0.0,
            "signals": {}, "explanation": "No data available",
        }
    if n == 1:
        return {
            "item_id": item_id, "category": category,
            "regime": "Stable", "confidence": 0.1,
            "signals": {"price_change_pct": 0.0, "volatility_pct": 0.0,
                        "volume_change": 1.0, "trend": "flat", "trend_acceleration": "steady"},
            "explanation": "Only one data point — no trend detectable",
        }

    prices = [p for _, p, _ in hist]
    volumes = [v for _, _, v in hist]
    current = prices[-1]
    start = prices[0]
    median = stats["median"]
    mad = stats["mad"]
    vol_median = stats["volume_median"] or 1.0

    price_change_pct = _safe_pct(current, start)
    price_vs_median_pct = _safe_pct(current, median)

    # Volatility as MAD relative to median
    volatility_pct = (mad / median * 100.0) if median else 0.0

    # Volume change as multiplier
    vol_current = volumes[-1] if volumes else 0
    volume_change = (vol_current / vol_median) if vol_median else 1.0

    trend = _trend_direction(prices)
    acceleration = _trend_acceleration(prices)

    signals = {
        "price_change_pct": round(price_change_pct, 2),
        "volatility_pct": round(volatility_pct, 2),
        "volume_change": round(volume_change, 2),
        "trend": trend,
        "trend_acceleration": acceleration,
    }

    # --- Classification ---
    # Thresholds
    SHARP_DROP = -10.0   # % drop threshold for crashing
    SHARP_RISE = 10.0    # % rise threshold for pumping
    HIGH_VOL_MULT = 2.0  # volume multiplier for "high volume"
    VOLATILE = 8.0       # volatility_pct threshold for "high volatility"

    # Supply Shock: price down + volume up sharply
    if price_change_pct < -SHARP_DROP and volume_change >= HIGH_VOL_MULT:
        regime, conf = "Supply Shock", min(0.95, 0.5 + abs(price_change_pct) / 40 + (volume_change - 1) / 5)
        expl = f"Price down {abs(price_change_pct):.1f}% with {volume_change:.1f}x normal volume — active sell pressure"

    # Demand Shock: price up + volume up sharply
    elif price_change_pct > SHARP_RISE and volume_change >= HIGH_VOL_MULT:
        regime, conf = "Demand Shock", min(0.95, 0.5 + price_change_pct / 40 + (volume_change - 1) / 5)
        expl = f"Price up {price_change_pct:.1f}% with {volume_change:.1f}x normal volume — strong buying pressure"

    # Crashing: sharp recent drop, high volume
    elif price_change_pct < SHARP_DROP and volume_change >= 1.3:
        regime, conf = "Crashing", min(0.9, 0.4 + abs(price_change_pct) / 30)
        expl = f"Price down {abs(price_change_pct):.1f}% — active sell-off"

    # Pumping: sharp recent rise, high volume
    elif price_change_pct > SHARP_RISE and volume_change >= 1.3:
        regime, conf = "Pumping", min(0.9, 0.4 + price_change_pct / 30)
        expl = f"Price up {price_change_pct:.1f}% — strong upward momentum"

    # Volume Spike: volume significantly above normal without dramatic price change
    elif volume_change >= HIGH_VOL_MULT and abs(price_change_pct) < SHARP_DROP:
        regime, conf = "Volume Spike", min(0.85, 0.3 + (volume_change - 1) / 4)
        expl = f"Volume at {volume_change:.1f}x normal — unusual trading activity without major price move"

    # Recovering: price dropped then stabilized or started rising
    elif trend == "rising" and price_change_pct < 0:
        regime, conf = "Recovering", min(0.8, 0.3 + abs(price_change_pct) / 40)
        expl = f"Price was down {abs(price_change_pct):.1f}% but now recovering — trend reversing upward"

    # Mean-Reverting: price deviated then returning to norm
    elif abs(price_vs_median_pct) > 5.0 and trend in ("rising", "falling") and price_vs_median_pct * price_change_pct < 0:
        # Price deviated from median but is moving back toward it
        regime, conf = "Mean-Reverting", min(0.8, 0.3 + abs(price_vs_median_pct) / 30)
        expl = f"Price deviated {abs(price_vs_median_pct):.1f}% from median, now reverting — {'rising' if price_vs_median_pct < 0 else 'falling'} back"

    # Trending Up
    elif trend == "rising" and price_change_pct > 3.0:
        regime, conf = "Trending Up", min(0.85, 0.2 + price_change_pct / 25)
        expl = f"Price consistently rising — up {price_change_pct:.1f}% over the window"

    # Trending Down
    elif trend == "falling" and price_change_pct < -3.0:
        regime, conf = "Trending Down", min(0.85, 0.2 + abs(price_change_pct) / 25)
        expl = f"Price consistently falling — down {abs(price_change_pct):.1f}% over the window"

    # Stable
    else:
        regime = "Stable"
        conf = max(0.1, 0.5 - volatility_pct / 20)
        expl = f"Price stable near median ({median:.2f}), low volatility ({volatility_pct:.1f}%)"

    return {
        "item_id": item_id,
        "category": category,
        "regime": regime,
        "confidence": round(conf, 2),
        "signals": signals,
        "explanation": expl,
    }


async def detect_all_regimes(league: str, category: str, hours: float = 24) -> list[dict]:
    """Classify a category from one bulk history query."""
    histories = await market_data.get_category_histories(league, category, hours)
    if not histories:
        return []
    latest = await market_data.get_latest_prices(league, category)
    results = []
    for item_id, history in histories.items():
        result = await detect_regime(
            league, category, item_id, hours, _history=history
        )
        result["item_name"] = latest.get(item_id, {}).get("item_name", item_id)
        results.append(result)
    results.sort(key=lambda r: (r["confidence"], r["regime"] != "Stable"), reverse=True)
    return results