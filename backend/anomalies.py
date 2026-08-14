"""Anomaly detection — flags items whose current price/volume deviate from their own history."""

import statistics

import market_data


def _modified_zscore(current: float, median: float, mad: float) -> float:
    """Robust z-score using MAD.  0.6745 * (x - median) / MAD."""
    if mad == 0:
        # No spread in data — if current is within rounding tolerance of median,
        # it's the same value (z=0). Otherwise it's a genuine jump.
        if abs(current - median) < 1e-9:
            return 0.0
        return 5.0 if current > median else -5.0
    return 0.6745 * (current - median) / mad


def _percentile_of(current: float, prices: list[float]) -> float:
    """Fraction of `prices` that are <= current, 0..1."""
    if not prices:
        return 0.5
    return sum(1 for p in prices if p <= current) / len(prices)


async def detect_anomalies(league: str, category: str, hours: float = 24) -> list[dict]:
    """Scan all items in a category; return those with significant anomalies."""
    histories = await market_data.get_category_histories(league, category, hours)
    if not histories:
        return []
    latest = await market_data.get_latest_prices(league, category)

    anomalies: list[dict] = []
    for item_id, hist in histories.items():
        row = latest.get(item_id, {})
        item_name = row.get("item_name", item_id)
        stats = market_data.rolling_stats(hist)

        n = stats["count"]
        if n == 0:
            continue

        prices = [p for _, p, _ in hist]
        volumes = [v for _, _, v in hist]
        current_price = prices[-1] if prices else 0.0
        current_vol = volumes[-1] if volumes else 0
        # Use raw median/mad from prices, not rounded stats, to avoid false
        # positives when MAD is 0 and rounding makes current != median.
        raw_median = statistics.median(prices) if prices else current_price
        raw_mad = statistics.median([abs(p - raw_median) for p in prices]) if prices else 0.0
        vol_median = stats["volume_median"] or 1.0

        z = _modified_zscore(current_price, raw_median, raw_mad)
        pct = _percentile_of(current_price, prices)
        vol_mult = (current_vol / vol_median) if vol_median else 1.0

        # --- Classify anomaly type ---
        anomaly_type = None
        severity = 0.0
        explanation = ""

        # Price drop: strong negative z-score + low percentile
        if z <= -2.0 and pct <= 0.1:
            anomaly_type = "price_drop"
            severity = min(1.0, abs(z) / 4.0)
            explanation = f"Price at {pct*100:.0f}th percentile of {hours:.0f}h range, z-score {z:.1f}"

        # Price spike: strong positive z-score + high percentile
        elif z >= 2.0 and pct >= 0.9:
            anomaly_type = "price_spike"
            severity = min(1.0, z / 4.0)
            explanation = f"Price at {pct*100:.0f}th percentile of {hours:.0f}h range, z-score {z:.1f}"

        # Volume spike: current volume >> median
        if vol_mult >= 3.0 and current_vol > 0:
            vol_severity = min(1.0, (vol_mult - 1) / 4.0)
            if vol_severity > severity:
                anomaly_type = "volume_spike"
                severity = vol_severity
                explanation = f"Volume at {vol_mult:.1f}x normal ({current_vol:,.0f} vs {vol_median:,.0f})"

        # Volume collapse: current volume << median
        elif vol_mult <= 0.3 and current_vol > 0 and vol_median > 0:
            vol_sev = min(1.0, (1 - vol_mult) / 0.7)
            if vol_sev > severity:
                anomaly_type = "volume_collapse"
                severity = vol_sev
                explanation = f"Volume at {vol_mult:.1f}x normal — trading dried up ({current_vol:,.0f} vs {vol_median:,.0f})"

        # Price/volume divergence: price moving one way, volume the other
        if n >= 4 and anomaly_type is None:
            mid = n // 2
            first_half_price = statistics.fmean(prices[:mid]) if mid > 0 else prices[0]
            second_half_price = statistics.fmean(prices[mid:])
            first_half_vol = statistics.fmean(volumes[:mid]) if mid > 0 else volumes[0]
            second_half_vol = statistics.fmean(volumes[mid:])
            price_dir = 1 if second_half_price > first_half_price else -1
            vol_dir = 1 if second_half_vol > first_half_vol else -1
            price_pct_change = ((second_half_price - first_half_price) / first_half_price * 100) if first_half_price else 0
            vol_pct_change = ((second_half_vol - first_half_vol) / first_half_vol * 100) if first_half_vol else 0
            if price_dir != vol_dir and (abs(price_pct_change) > 5 or abs(vol_pct_change) > 30):
                anomaly_type = "divergence"
                severity = min(0.8, 0.2 + max(abs(price_pct_change), abs(vol_pct_change)) / 50)
                pword = "up" if price_dir > 0 else "down"
                vword = "up" if vol_dir > 0 else "down"
                explanation = f"Price {pword} {abs(price_pct_change):.1f}% while volume {vword} {abs(vol_pct_change):.1f}% — divergence"

        # Recovery: price was deviated (strong z) but now moving back toward median
        if n >= 4 and anomaly_type is None:
            # Check if the most recent z-scores are shrinking in magnitude
            recent_prices = prices[-min(4, n):]
            recent_zs = [_modified_zscore(p, raw_median, raw_mad) for p in recent_prices]
            if len(recent_zs) >= 2:
                # Was strongly deviated earlier, now closer to zero
                if abs(recent_zs[0]) > 2.0 and abs(recent_zs[-1]) < abs(recent_zs[0]) * 0.6:
                    anomaly_type = "recovery"
                    severity = min(0.7, 0.2 + abs(recent_zs[0]) / 5)
                    direction = "rising" if recent_zs[0] < 0 else "falling"
                    explanation = f"Price was deviated (z={recent_zs[0]:.1f}), now {direction} back toward median (z={recent_zs[-1]:.1f})"

        if anomaly_type is None:
            continue

        anomalies.append({
            "item_id": item_id,
            "item_name": item_name,
            "category": category,
            "anomaly_type": anomaly_type,
            "severity": round(severity, 2),
            "z_score": round(z, 2),
            "percentile": round(pct, 4),
            "price_current": round(current_price, 4),
            "price_median": round(raw_median, 4),
            "volume_current": round(current_vol, 2),
            "volume_median": round(vol_median, 2),
            "volume_multiplier": round(vol_mult, 2),
            "explanation": explanation,
        })

    anomalies.sort(key=lambda a: a["severity"], reverse=True)
    return anomalies


async def detect_all_anomalies(league: str, hours: float = 24) -> list[dict]:
    """Scan all categories for anomalies."""
    grouped = await market_data.get_all_latest(league)
    results: list[dict] = []
    for category in grouped:
        results.extend(await detect_anomalies(league, category, hours))
    results.sort(key=lambda a: a["severity"], reverse=True)
    return results