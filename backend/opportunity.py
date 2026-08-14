"""Opportunity abstraction — unifies regimes, anomalies, and signals into a scored model."""

from datetime import datetime, timezone
import statistics

from pydantic import BaseModel

import anomalies as anomaly_mod
import regimes as regime_mod
import signals as signals_mod
import market_data
import validation
HISTORICAL_OUTCOME_HOURS = 24




class Opportunity(BaseModel):
    type: str               # "regime", "anomaly", "spread", "conversion"
    detector_id: str        # "Supply Shock", "price_drop", etc.
    item_id: str
    item_name: str
    category: str
    league: str
    what_happened: str
    why_it_matters: str
    possible_action: str
    confidence: float       # heuristic composite score, 0-1
    signals: dict           # underlying regime/anomaly data
    historical_context: dict
    timestamp: str          # ISO-UTC when detected
    # Empirical outcome fields are intentionally separate from heuristic
    # confidence and are populated from look-ahead-safe historical events.
    expected_return: float | None = None
    win_probability: float | None = None
    median_return: float | None = None
    downside_percentile: float | None = None
    sample_size: int = 0
    historical_confidence: float | None = None
    # Execution-aware estimates are distinct from both confidence fields.
    theoretical_price: float | None = None
    realistic_entry: float | None = None
    realistic_exit: float | None = None
    capital_required: float | None = None
    realistic_profit: float | None = None
    roi: float | None = None
    estimated_time: float | None = None
    profit_per_hour: float | None = None
    liquidity: dict | None = None
    risk: str | None = None

    def to_investable(self, **kwargs) -> "InvestableOpportunity":
        return normalize_opportunity(self, **kwargs)
 
class InvestableOpportunity(BaseModel):
    """Execution-aware, capacity-bounded view of an empirically filtered opportunity."""

    id: str
    strategy_type: str
    entry_item: str
    exit_item: str | None = None
    category: str = "unknown"
    current_price: float = 0.0
    realistic_entry_price: float
    realistic_exit_price: float | None = None
    expected_return: float
    expected_profit_per_unit: float
    expected_profit_per_divine_hour: float = 0.0
    win_probability: float
    expected_duration: float
    duration_distribution: list[float] = []
    downside_percentile: float = 0.0
    upside_percentile: float | None = None
    historical_sample_size: int = 0
    confidence: float = 0.0
    liquidity: dict = {}
    execution_effort: float = 0.0
    minimum_capital: float
    maximum_reasonable_capital: float
    opportunity_capacity: float
    correlation_group: str = "unknown"
    created_at: str = ""
    last_validated_at: str = ""
    expected_half_life: float = 6.0
    expires_at: str | None = None
    expiration: str | None = None
    historical_returns: list[float] = []
    tier: str = "REJECTED"
    status: str = "ACTIVE"
    rejection_reason: str | None = None
    strategy_status: str = "Validated"
    experimental_allocation_cap: float = 0.02
    metadata: dict | None = None
    def is_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        value = self.expires_at or self.expiration
        if not value:
            return False
        expiry = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return current >= expiry

    def invalidate(self, reason: str = "market_conditions_changed") -> None:
        self.status = "INVALIDATED"
        self.rejection_reason = reason

def normalize_opportunity(
    opportunity: Opportunity,
    *,
    now: datetime | None = None,
    participation_rate: float = 0.05,
    horizon_hours: float | None = None,
    chaos_per_divine: float | None = None,
    paper_only: bool = False,
) -> InvestableOpportunity:
    """Adapt chaos-priced opportunities into Divine-denominated capital fields."""
    if chaos_per_divine is None or chaos_per_divine <= 0:
        raise ValueError("positive chaos_per_divine is required for normalization")
    current = now or datetime.now(timezone.utc)
    created = datetime.fromisoformat(opportunity.timestamp.replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    price = float(opportunity.theoretical_price or opportunity.realistic_entry or 0)
    entry = float(opportunity.realistic_entry or price)
    context = opportunity.historical_context or {}
    feedback = context.get("calibration") or {}
    expected_return = float(
        feedback.get("expected_return")
        if feedback.get("applied") and feedback.get("expected_return") is not None
        else (opportunity.expected_return or 0)
    )
    returns = [float(value) for value in (context.get("return_samples") or context.get("returns") or [])]
    duration_samples = [
        max(0.25, float(value))
        for value in (context.get("duration_samples") or context.get("time_to_peak_samples") or [])
        if float(value) > 0
    ]
    duration = max(
        0.25,
        float(
            horizon_hours
            or context.get("calibrated_duration_hours")
            or (statistics.median(duration_samples) if duration_samples else opportunity.estimated_time or 6)
        ),
    )
    liquidity = dict(opportunity.liquidity or {})
    volume = max(0.0, float(liquidity.get("volume", 0) or 0))
    tier_name = str(liquidity.get("tier", "low")).lower()
    confidence = max(0.0, min(1.0, float(opportunity.historical_confidence or 0)))
    # Volume is treated as units per observation; a 5% participation cap and
    # uncertainty shrink keep thin markets from scaling linearly with bankroll.
    entry_divine = entry / chaos_per_divine
    capacity = volume * participation_rate * max(1.0, duration / 6.0) * entry / chaos_per_divine
    sample_size = int(opportunity.sample_size or 0)
    empirical_returns = bool(returns) and sample_size > 0
    evidence_sources = dict(context.get("evidence_sources") or {})
    reconstructed_size = int(context.get("reconstructed_sample_size") or 0)
    observed_size = sum(
        count for source, count in evidence_sources.items()
        if "reconstructed" not in str(source)
    )
    reconstructed_dependent = reconstructed_size > 0
    tier = (
        "S" if sample_size >= 100 and confidence >= 0.80 and tier_name == "high" and expected_return > 0 and empirical_returns
        else "A" if sample_size >= 20 and confidence >= 0.60 and tier_name in ("medium", "high") and expected_return > 0 and empirical_returns
        else "B" if sample_size >= 5 and expected_return > 0 and empirical_returns else "REJECTED"
    )
    filter_rejection = context.get("filter_rejection")
    paper_reconstructed = (
        paper_only
        and reconstructed_dependent
        and confidence >= 0.30
        and tier_name in ("medium", "high")
        and expected_return > 0
        and opportunity.realistic_profit is not None
        and opportunity.realistic_profit > 0
        and (context.get("data_points") or 0) >= 2
        and tier == "B"
    )
    if paper_reconstructed:
        tier = "B"
    if not empirical_returns:
        tier = "WATCH" if expected_return > 0 else "REJECTED"
    if tier in ("S", "A") and expected_return <= 0:
        tier = "REJECTED"
    if (filter_rejection or (reconstructed_dependent and tier == "B")) and not paper_reconstructed:
        tier = "REJECTED"
    half_life = max(1.0, duration)
    expires = created.timestamp() + half_life * 3600
    expires_at = datetime.fromtimestamp(expires, timezone.utc).isoformat(timespec="seconds")
    profit_per_unit = float(opportunity.realistic_profit or (entry * expected_return / 100)) / chaos_per_divine
    calibration = dict(context.get("calibration") or {})
    duration_distribution = [duration] if calibration.get("applied") else duration_samples
    return InvestableOpportunity(
        id=f"{opportunity.league}:{opportunity.category}:{opportunity.item_id}:{opportunity.detector_id}",
        strategy_type=opportunity.type,
        entry_item=opportunity.item_name or opportunity.item_id,
        category=opportunity.category,
        current_price=price,
        realistic_entry_price=entry,
        realistic_exit_price=opportunity.realistic_exit,
        expected_return=expected_return,
        expected_profit_per_unit=profit_per_unit,
        expected_profit_per_divine_hour=round((expected_return / 100) / duration, 8),
        win_probability=max(0.0, min(1.0, float(opportunity.win_probability or 0))),
        expected_duration=duration,
        duration_distribution=duration_distribution,
        downside_percentile=float(opportunity.downside_percentile or 0),
        upside_percentile=None,
        historical_sample_size=sample_size,
        historical_returns=returns,
        confidence=confidence,
        liquidity=liquidity,
        execution_effort=float(opportunity.signals.get("trade_count", 0) or 0),
        minimum_capital=max(0.0, entry_divine),
        maximum_reasonable_capital=capacity,
        opportunity_capacity=capacity,
        correlation_group=str(opportunity.signals.get("correlation_group") or opportunity.category),
        created_at=opportunity.timestamp,
        last_validated_at=opportunity.timestamp,
        expected_half_life=half_life,
        tier=tier,
        metadata={
            "evidence_sources": evidence_sources,
            "reconstructed_sample_size": reconstructed_size,
            "direct_observation": observed_size > 0,
            "reconstruction_dependent": reconstructed_dependent,
            "return_estimator": context.get("return_estimator", "mean"),
            "paper_only_reconstructed": paper_reconstructed,
            "calibration": calibration,
            "provenance": (
                "poe.ninja sparkline relative changes reconstructed as daily prices; "
                + ("mixed observed/reconstructed evidence; not direct historical observations"
                   if observed_size > 0 else "not direct historical observations")
                if reconstructed_dependent else "direct observed snapshots"
            ),
        },
        rejection_reason=filter_rejection or (
            None if tier in ("S", "A") else "insufficient_empirical_evidence"
        ),
    )


adapt_opportunity = normalize_opportunity


# --- Factory functions ---

async def regime_to_opportunity(regime_data: dict, league: str) -> Opportunity:
    """Convert a regime detection dict into an Opportunity."""
    # Fetch historical context for this item
    stats = await market_data.get_rolling_stats(
        league, regime_data["category"], regime_data["item_id"], 24
    )
    historical_context = {
        "median_price": stats.get("median"),
        "price_range": [stats.get("min"), stats.get("max")] if stats.get("min") is not None else None,
        "percentile_rank": stats.get("percentile_rank"),
        "volume_median": stats.get("volume_median"),
        "data_points": stats.get("count"),
    }
    # Pull guidance from signals module
    from signals import _REGIME_GUIDANCE
    why, action = _REGIME_GUIDANCE.get(
        regime_data["regime"],
        ("Significant market movement detected", "Monitor the situation"),
    )
    opp = Opportunity(
        type="regime",
        detector_id=regime_data["regime"],
        item_id=regime_data["item_id"],
        item_name=regime_data.get("item_id", ""),  # regime data doesn't carry item_name
        category=regime_data["category"],
        league=league,
        what_happened=regime_data.get("explanation", ""),
        why_it_matters=why,
        possible_action=action,
        confidence=regime_data.get("confidence", 0.0),
        signals=regime_data.get("signals", {}),
        historical_context=historical_context,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return await score_opportunity(opp, regime_data)


async def anomaly_to_opportunity(anomaly_data: dict, league: str) -> Opportunity:
    """Convert an anomaly detection dict into an Opportunity."""
    stats = await market_data.get_rolling_stats(
        league, anomaly_data["category"], anomaly_data["item_id"], 24
    )
    historical_context = {
        "median_price": stats.get("median"),
        "price_range": [stats.get("min"), stats.get("max")] if stats.get("min") is not None else None,
        "percentile_rank": stats.get("percentile_rank"),
        "volume_median": stats.get("volume_median"),
        "data_points": stats.get("count"),
        "z_score": anomaly_data.get("z_score"),
        "anomaly_percentile": anomaly_data.get("percentile"),
    }
    from signals import _ANOMALY_GUIDANCE
    why, action = _ANOMALY_GUIDANCE.get(
        anomaly_data["anomaly_type"],
        ("Statistical anomaly detected in price/volume", "Investigate further"),
    )
    opp = Opportunity(
        type="anomaly",
        detector_id=anomaly_data["anomaly_type"],
        item_id=anomaly_data["item_id"],
        item_name=anomaly_data.get("item_name", anomaly_data["item_id"]),
        category=anomaly_data["category"],
        league=league,
        what_happened=anomaly_data.get("explanation", ""),
        why_it_matters=why,
        possible_action=action,
        confidence=anomaly_data.get("severity", 0.0),
        signals={
            "z_score": anomaly_data.get("z_score"),
            "percentile": anomaly_data.get("percentile"),
            "volume_multiplier": anomaly_data.get("volume_multiplier"),
            "price_current": anomaly_data.get("price_current"),
            "price_median": anomaly_data.get("price_median"),
        },
        historical_context=historical_context,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return await score_opportunity(opp, anomaly_data)


async def signal_to_opportunity(signal_data: dict, league: str) -> Opportunity:
    """Convert a signal feed dict into an Opportunity."""
    # Signal source determines the detector type and underlying data
    source = signal_data.get("source", "regime")
    detector_id = signal_data.get("type", "Unknown")
    # Signals don't carry raw stats; fetch a lightweight context
    item_id = signal_data.get("item", "")
    category = signal_data.get("category", "")
    historical_context = {}
    if item_id and category:
        stats = await market_data.get_rolling_stats(league, category, item_id, 24)
        historical_context = {
            "median_price": stats.get("median"),
            "percentile_rank": stats.get("percentile_rank"),
            "volume_median": stats.get("volume_median"),
            "data_points": stats.get("count"),
        }
    opp = Opportunity(
        type=source,
        detector_id=detector_id,
        item_id=item_id,
        item_name=item_id,
        category=category,
        league=league,
        what_happened=signal_data.get("what_happened", ""),
        why_it_matters=signal_data.get("why_it_matters", ""),
        possible_action=signal_data.get("possible_action", ""),
        confidence=signal_data.get("confidence", 0.0),
        signals={"source": source, "raw_type": detector_id},
        historical_context=historical_context,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return await score_opportunity(opp, signal_data)


# --- Scoring engine ---

async def score_opportunity(opportunity: Opportunity, raw_data: dict | None = None) -> Opportunity:
    """Compute a composite confidence score (0-1) blending multiple signals.

    Factors:
      - Detector-specific confidence (regime.confidence / anomaly.severity): 70%
      - Volume multiplier boost: up to +20% (3x+ volume = full boost)
      - Historical rarity (percentile rank distance from 0.5): up to +15%
      - Signal strength (z-score magnitude): up to +15%
    """
    raw = raw_data or {}
    base = opportunity.confidence  # 0-1 from the detector

    # Volume multiplier — from regime signals or anomaly data
    vol_mult = 1.0
    if "signals" in raw and isinstance(raw["signals"], dict):
        vol_mult = raw["signals"].get("volume_change", 1.0)
    if not vol_mult or vol_mult == 1.0:
        vol_mult = raw.get("volume_multiplier", 1.0)
    vol_boost = min(0.20, max(0.0, (vol_mult - 1.0) / 4.0) * 0.20)

    # Historical rarity — percentile rank far from 0.5 = more interesting
    pct_rank = opportunity.historical_context.get("percentile_rank")
    rarity_boost = 0.0
    if pct_rank is not None:
        rarity_boost = min(0.15, abs(pct_rank - 0.5) * 0.30)

    # Signal strength — z-score magnitude (anomalies carry this)
    z = raw.get("z_score") or opportunity.signals.get("z_score")
    z_boost = 0.0
    if z is not None:
        z_boost = min(0.15, abs(z) / 10.0)

    composite = min(1.0, base * 0.70 + vol_boost + rarity_boost + z_boost)
    opportunity.confidence = round(composite, 4)
    return opportunity
MIN_HISTORICAL_EV = 0.0
MIN_EXPECTED_RETURN = 1.0
MIN_HISTORICAL_CONFIDENCE = 0.5
MIN_LIQUIDITY_TIER = "medium"
_LIQUIDITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _attach_execution_fields(opportunities: list[Opportunity], latest: dict) -> None:
    """Estimate one-unit execution with explicit slippage and fee assumptions."""
    slippage_by_tier = {"low": 0.10, "medium": 0.03, "high": 0.01}
    for opp in opportunities:
        row = latest.get((opp.category, opp.item_id), {})
        price = float(row.get("price_chaos", 0) or 0)
        volume = float(row.get("volume", 0) or 0)
        tier = validation.liquidity_tier(volume)
        slippage = slippage_by_tier[tier]
        opp.theoretical_price = round(price, 6) if price > 0 else None
        opp.liquidity = {
            "tier": tier, "volume": round(volume, 2),
            "slippage_pct": round(slippage * 100, 2),
        }
        if price <= 0:
            opp.risk = "high"
            continue
        entry = price * (1 + slippage)
        opp.realistic_entry = round(entry, 6)
        opp.capital_required = round(entry, 6)
        if opp.expected_return is not None:
            exit_price = entry * (1 + opp.expected_return / 100) * (1 - slippage)
            profit = exit_price - entry
            opp.realistic_exit = round(exit_price, 6)
            opp.realistic_profit = round(profit, 6)
            opp.roi = round(profit / entry * 100, 6) if entry else None
            duration = (
                (opp.historical_context or {}).get("calibrated_duration_hours")
                or (statistics.median(opp.historical_context.get("duration_samples") or [])
                    if opp.historical_context.get("duration_samples") else None)
                or opp.estimated_time
                or HISTORICAL_OUTCOME_HOURS
            )
            opp.estimated_time = max(0.25, float(duration))
            opp.profit_per_hour = round(profit / opp.estimated_time, 6)
        downside = opp.downside_percentile
        opp.risk = "high" if tier == "low" or (downside is not None and downside < -10) else (
            "medium" if downside is not None and downside < 0 else "low"
        )


def filter_opportunities(opportunities: list[Opportunity],
                         min_historical_ev: float = MIN_HISTORICAL_EV,
                         min_historical_confidence: float = MIN_HISTORICAL_CONFIDENCE,
                         min_liquidity: str = MIN_LIQUIDITY_TIER,
                         min_expected_return: float = MIN_EXPECTED_RETURN) -> tuple[list[Opportunity], dict]:
    """Apply empirical, execution and thin-market guards without score blending."""
    minimum_rank = _LIQUIDITY_RANK.get(min_liquidity)
    if minimum_rank is None:
        raise ValueError(f"min_liquidity must be one of {sorted(_LIQUIDITY_RANK)}")
    if not 0 <= min_historical_confidence <= 1:
        raise ValueError("min_historical_confidence must be between 0 and 1")
    accepted, rejected = [], {}
    for opp in opportunities:
        tier = (opp.liquidity or {}).get("tier")
        reason = None
        if opp.expected_return is None or opp.sample_size <= 0:
            reason = "missing_historical_outcome"
        elif opp.expected_return < min_historical_ev:
            reason = "historical_ev_below_threshold"
        elif opp.expected_return < min_expected_return:
            reason = "expected_return_below_threshold"
        elif opp.historical_confidence is None or opp.historical_confidence < min_historical_confidence:
            reason = "wilson_confidence_below_threshold"
        elif _LIQUIDITY_RANK.get(tier, -1) < minimum_rank:
            reason = "liquidity_below_threshold"
        elif (opp.historical_context.get("data_points") or 0) < 2:
            reason = "isolated_price"
        elif opp.realistic_profit is None or opp.realistic_profit <= 0:
            reason = "execution_not_profitable"
        if reason:
            opp.historical_context["filter_rejection"] = reason
            rejected[reason] = rejected.get(reason, 0) + 1
        else:
            opp.historical_context.pop("filter_rejection", None)
            accepted.append(opp)
    return accepted, rejected


async def _attach_historical_outcomes(
    opportunities: list[Opportunity],
    *,
    include_feedback: bool = True,
) -> None:
    """Attach historical outcomes and exact-opportunity paper feedback."""
    if not opportunities:
        return
    result = await validation.backtest(
        opportunities[0].league, horizons=(HISTORICAL_OUTCOME_HOURS,)
    )
    horizon = str(HISTORICAL_OUTCOME_HOURS)
    outcomes = {}
    for group in result["groups"]:
        key = (group["category"], group["source"], group["signal_type"])
        outcome = group["horizons"].get(horizon, {})
        # Backtests also partition by liquidity tier. Do not let an empty
        # later tier overwrite a populated historical cohort.
        if int(outcome.get("sample_size") or 0) <= 0:
            continue
        previous = outcomes.get(key)
        if previous is None or int(outcome["sample_size"]) > int(previous.get("sample_size") or 0):
            outcomes[key] = outcome
    from portfolio import calibrate_opportunity

    for opp in opportunities:
        outcome = outcomes.get((opp.category, opp.type, opp.detector_id), {})
        if outcome.get("sample_size"):
            evidence_sources = dict(outcome.get("evidence_sources") or {})
            reconstructed_size = int(outcome.get("reconstructed_sample_size") or 0)
            estimator = "median" if reconstructed_size > 0 else "mean"
            opp.expected_return = outcome.get(f"{estimator}_return")
            opp.win_probability = outcome.get("win_probability")
            opp.median_return = outcome.get("median_return")
            opp.downside_percentile = outcome.get("p10_return")
            opp.sample_size = outcome["sample_size"]
            opp.historical_confidence = outcome.get("historical_confidence")
            opp.historical_context["return_samples"] = list(outcome.get("return_samples") or [])
            opp.historical_context["duration_samples"] = list(outcome.get("duration_samples") or [])
            opp.historical_context["time_to_peak_samples"] = list(outcome.get("time_to_peak_samples") or [])
            opp.historical_context["evidence_sources"] = evidence_sources
            opp.historical_context["reconstructed_sample_size"] = reconstructed_size
            opp.historical_context["return_estimator"] = estimator
        if not include_feedback:
            continue
        fallback_duration = (
            statistics.median(opp.historical_context.get("duration_samples") or [])
            if opp.historical_context.get("duration_samples")
            else opp.estimated_time or HISTORICAL_OUTCOME_HOURS
        )
        calibration = await calibrate_opportunity(
            f"{opp.league}:{opp.category}:{opp.item_id}:{opp.detector_id}",
            opp.expected_return,
            fallback_duration,
        )
        opp.historical_context["calibration"] = calibration
        if calibration["applied"]:
            opp.expected_return = calibration["expected_return"]
            opp.historical_context["calibrated_duration_hours"] = calibration["expected_duration_hours"]




# --- Aggregator ---

async def get_all_opportunities(
    league: str,
    hours: float = 24,
    *,
    include_feedback: bool = True,
) -> list[Opportunity]:
    """Gather all opportunities across all categories, sorted by confidence."""
    grouped = await market_data.get_all_latest(league)
    if not grouped:
        return []

    opportunities: list[Opportunity] = []

    for category in grouped:
        # Regimes → opportunities (skip Stable/Unknown)
        for regime in await regime_mod.detect_all_regimes(league, category, hours):
            if regime["regime"] in ("Stable", "Unknown"):
                continue
            opportunities.append(await regime_to_opportunity(regime, league))

        # Anomalies → opportunities
        for anom in await anomaly_mod.detect_anomalies(league, category, hours):
            opportunities.append(await anomaly_to_opportunity(anom, league))

    await _attach_historical_outcomes(opportunities, include_feedback=include_feedback)
    latest = {
        (row["category"], row["item_id"]): row
        for rows in grouped.values()
        for row in rows
    }
    _attach_execution_fields(opportunities, latest)
    opportunities.sort(key=lambda o: o.confidence, reverse=True)
    return opportunities


OPPORTUNITY_TYPES = {
    "regime": ["Stable", "Trending Up", "Trending Down", "Recovering", "Crashing",
               "Pumping", "Mean-Reverting", "Volume Spike", "Supply Shock", "Demand Shock"],
    "anomaly": ["price_drop", "price_spike", "volume_spike", "volume_collapse",
                "divergence", "recovery"],
    "spread": [],       # reserved for future spread detector
    "conversion": [],   # reserved for future conversion detector
}
