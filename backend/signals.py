"""Market signals feed — combines regimes and anomalies into actionable alerts."""

import anomalies as anomaly_mod
import regimes as regime_mod
import market_data

# Explanations for why each regime/anomaly matters and possible actions
_REGIME_GUIDANCE = {
    "Supply Shock": (
        "Active sell pressure — potential capitulation or fundamental devaluation",
        "Watch for stabilization before buying; if volume drops and price holds, may be a dip opportunity",
    ),
    "Demand Shock": (
        "Strong buying pressure — possible shortage or speculation surge",
        "Consider selling into strength; if you need the item, buy before it goes higher",
    ),
    "Crashing": (
        "Prices falling fast — market is dumping this item",
        "Wait for the bottom; don't catch a falling knife unless you see volume dry up",
    ),
    "Pumping": (
        "Strong upward momentum — FOMO or real demand driving prices",
        "If holding, consider taking profit; if buying, check if fundamentals justify the move",
    ),
    "Volume Spike": (
        "Unusual trading activity — something is happening, watch closely",
        "Monitor price direction for confirmation; high volume often precedes major moves",
    ),
    "Recovering": (
        "Price may have bottomed — trend reversal in progress",
        "Potential entry point if the recovery holds; good risk/reward if floor is established",
    ),
    "Mean-Reverting": (
        "Price returning to its historical norm — the deviation was temporary",
        "Mean reversion can overshoot; wait for confirmation of the median as support/resistance",
    ),
    "Trending Up": (
        "Steady upward trend — consistent demand over time",
        "Good for swing trading; buy on small dips within the uptrend",
    ),
    "Trending Down": (
        "Steady downward trend — consistent supply or declining demand",
        "Avoid catching the trend early; wait for volume/price signals of a reversal",
    ),
    "Stable": (
        "Price is well-behaved — no significant movement",
        "No action needed; stable items are good for steady-state trading",
    ),
    "Unknown": (
        "Insufficient data to classify",
        "Collect more snapshots before drawing conclusions",
    ),
}

_ANOMALY_GUIDANCE = {
    "price_drop": (
        "Price significantly below its recent range — potential bargain or falling knife",
        "Check if the drop is justified (fundamental change) or an overreaction (buy opportunity)",
    ),
    "price_spike": (
        "Price significantly above its recent range — potential sell opportunity or FOMO",
        "If holding, consider taking profit; if buying, wait for pullback unless fundamentals changed",
    ),
    "volume_spike": (
        "Trading volume is unusually high — major interest or news",
        "Watch price direction; high volume confirms moves and often signals breakouts",
    ),
    "volume_collapse": (
        "Trading volume dried up — interest is fading",
        "Low liquidity means wider spreads; be cautious entering or exiting large positions",
    ),
    "divergence": (
        "Price and volume disagreeing — current trend may be unsustainable",
        "Divergence often signals an imminent reversal; wait for confirmation",
    ),
    "recovery": (
        "Price returning to normal after an anomaly — the deviation is resolving",
        "If the deviation was an overreaction, this is the exit window for counter-trades",
    ),
}


async def get_market_signals(league: str, hours: float = 24) -> list[dict]:
    """Combine regime detections and anomalies into a single ranked signal feed."""
    signals: list[dict] = []

    # Gather all regimes across all categories
    grouped = await _all_categories(league)
    for category in grouped:
        for regime in await regime_mod.detect_all_regimes(league, category, hours):
            if regime["regime"] in ("Stable", "Unknown"):
                continue
            why, action = _REGIME_GUIDANCE.get(
                regime["regime"],
                ("Significant market movement detected", "Monitor the situation"),
            )
            signals.append({
                "type": regime["regime"],
                "item": regime.get("item_id", "Unknown"),
                "category": category,
                "what_happened": regime["explanation"],
                "why_it_matters": why,
                "possible_action": action,
                "confidence": regime["confidence"],
                "source": "regime",
            })

    # Gather all anomalies
    for anom in await anomaly_mod.detect_all_anomalies(league, hours):
        why, action = _ANOMALY_GUIDANCE.get(
            anom["anomaly_type"],
            ("Statistical anomaly detected in price/volume", "Investigate further"),
        )
        signals.append({
            "type": anom["anomaly_type"],
            "item": anom.get("item_name", anom["item_id"]),
            "category": anom["category"],
            "what_happened": anom["explanation"],
            "why_it_matters": why,
            "possible_action": action,
            "confidence": anom["severity"],
            "source": "anomaly",
        })

    # Sort by confidence descending
    signals.sort(key=lambda s: s["confidence"], reverse=True)
    return signals

async def _all_categories(league: str) -> list[str]:
    """Get the list of categories that have data for this league."""
    grouped = await market_data.get_all_latest(league)
    return list(grouped.keys())
